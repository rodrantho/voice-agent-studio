from __future__ import annotations

import hashlib
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .call_engine import PolicyEngine, consent
from .db import Database
from .models import AppConfig, LoginRequest, SecretInput, SetupRequest, SimulationRequest
from .providers import (
    CodexAppServer,
    CodexSubscriptionProvider,
    OpenAICompatibleProvider,
    ProviderError,
)
from .security import Vault
from .sip import render_asterisk

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = Path(os.environ.get("VAS_DATA_DIR", "./data")).resolve()
ASTERISK_CONFIG_DIR = Path(
    os.environ.get("VAS_ASTERISK_CONFIG_DIR", "/tmp/vas-asterisk-disabled")
).resolve()
SESSION_SECONDS = 12 * 60 * 60


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


vault = Vault.from_environment()
db = Database(DATA_DIR / "voice-agent-studio.db", vault)
codex = CodexAppServer(
    os.environ.get("VAS_CODEX_COMMAND", "codex app-server"),
    DATA_DIR / "codex-home",
)
codex_subscription = CodexSubscriptionProvider(DATA_DIR / "codex-home", codex)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await codex.close()


app = FastAPI(title="Voice Agent Studio", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
    )
    return response


def session_user(vas_session: str | None = Cookie(default=None)):
    if not vas_session:
        raise HTTPException(401, "Authentication required")
    row = db.session(token_hash(vas_session))
    if not row:
        raise HTTPException(401, "Session expired")
    return row


def csrf_user(
    user=Depends(session_user),
    x_csrf_token: str | None = Header(default=None),
):
    if not x_csrf_token or not secrets.compare_digest(x_csrf_token, user["csrf_token"]):
        raise HTTPException(403, "Invalid CSRF token")
    return user


def issue_session(response: Response, user_id: int) -> str:
    token = secrets.token_urlsafe(48)
    csrf = secrets.token_urlsafe(32)
    db.create_session(user_id, token_hash(token), csrf, int(time.time()) + SESSION_SECONDS)
    response.set_cookie(
        "vas_session",
        token,
        max_age=SESSION_SECONDS,
        httponly=True,
        samesite="strict",
        secure=os.environ.get("VAS_SECURE_COOKIES", "false").lower() == "true",
    )
    return csrf


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "configured": db.get_config().configured, "setup_required": not db.has_users()}


@app.post("/api/setup")
def setup(payload: SetupRequest, response: Response):
    if db.has_users():
        raise HTTPException(409, "Setup already completed")
    db.create_user(payload.username, payload.password)
    user_id = db.authenticate(payload.username, payload.password)
    assert user_id is not None
    return {"ok": True, "csrf_token": issue_session(response, user_id)}


@app.post("/api/login")
def login(payload: LoginRequest, response: Response):
    user_id = db.authenticate(payload.username, payload.password)
    if user_id is None:
        time.sleep(0.2)
        raise HTTPException(401, "Invalid credentials")
    db.audit(payload.username, "session.login", {})
    return {"ok": True, "csrf_token": issue_session(response, user_id)}


@app.post("/api/logout")
def logout(response: Response, vas_session: str | None = Cookie(default=None), user=Depends(csrf_user)):
    if vas_session:
        db.delete_session(token_hash(vas_session))
    db.audit(user["username"], "session.logout", {})
    response.delete_cookie("vas_session")
    return {"ok": True}


@app.get("/api/session")
def session(user=Depends(session_user)):
    return {"username": user["username"], "csrf_token": user["csrf_token"]}


@app.get("/api/config")
def get_config(user=Depends(session_user)):
    return {"config": db.get_config(), "secrets": db.secret_status(), "actor": user["username"]}


@app.put("/api/config")
def put_config(config: AppConfig, user=Depends(csrf_user)):
    db.save_config(config, user["username"])
    return {"ok": True, "config": config}


@app.put("/api/secrets")
def put_secret(secret: SecretInput, user=Depends(csrf_user)):
    db.set_secret(secret.name, secret.value, user["username"])
    return {"ok": True, "name": secret.name, "configured": True}


@app.get("/api/audit")
def audit(user=Depends(session_user)):
    return {"entries": db.audits(100)}


@app.post("/api/simulate")
def simulate(payload: SimulationRequest, user=Depends(csrf_user)):
    result = PolicyEngine(db.get_config()).simulate(payload.utterance, payload.state)
    db.audit(user["username"], "flow.simulated", {"intent": result["state"]["intent"], "action": result["next"]["action"]})
    return result


@app.post("/api/consent/classify")
def classify_consent(payload: SimulationRequest, user=Depends(csrf_user)):
    return {"classification": consent(payload.utterance)}


@app.get("/api/sip/render")
def sip_render(user=Depends(session_user)):
    rendered = render_asterisk(db.get_config().sip)
    return {"pjsip": rendered.pjsip, "extensions": rendered.extensions, "rtp": rendered.rtp}


@app.post("/api/sip/apply")
def sip_apply(user=Depends(csrf_user)):
    if os.environ.get("VAS_ENABLE_SIP_APPLY", "false").lower() != "true":
        raise HTTPException(409, "SIP apply is disabled on this installation")
    sip = db.get_config().sip
    if not sip.host or not sip.extension:
        raise HTTPException(409, "SIP host and extension must be configured")
    rendered = render_asterisk(sip)
    sip_password = db.get_secret("sip_password")
    if not sip_password:
        raise HTTPException(409, "SIP password is not configured")
    ASTERISK_CONFIG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(ASTERISK_CONFIG_DIR, 0o700)
    files = {
        "pjsip.conf": rendered.pjsip.replace("${ENV(VAS_SIP_PASSWORD)}", sip_password),
        "extensions.conf": rendered.extensions,
        "rtp.conf": rendered.rtp,
    }
    for name, content in files.items():
        temporary = ASTERISK_CONFIG_DIR / f".{name}.tmp"
        target = ASTERISK_CONFIG_DIR / name
        temporary.write_text(content)
        os.chmod(temporary, 0o600)
        temporary.replace(target)
    marker = ASTERISK_CONFIG_DIR / ".reload"
    marker.write_text(str(int(time.time())))
    os.chmod(marker, 0o600)
    db.audit(user["username"], "sip.applied", {"files": sorted(files)})
    return {"applied": True, "files": sorted(files)}


@app.post("/api/providers/codex/login/start")
async def codex_login_start(user=Depends(csrf_user)):
    try:
        login = await codex.begin_device_login()
    except (FileNotFoundError, ProviderError, TimeoutError) as exc:
        raise HTTPException(503, f"Codex app-server unavailable: {type(exc).__name__}") from exc
    db.audit(user["username"], "provider.codex_login_started", {"login_id": login.login_id})
    return {"login_id": login.login_id, "verification_url": login.verification_url, "user_code": login.user_code, "expires_in": 900}


@app.post("/api/providers/codex/login/{login_id}/cancel")
async def codex_login_cancel(login_id: str, user=Depends(csrf_user)):
    try:
        result = await codex.cancel_login(login_id)
    except (ProviderError, TimeoutError) as exc:
        raise HTTPException(503, "Unable to cancel Codex login") from exc
    db.audit(user["username"], "provider.codex_login_cancelled", {"login_id": login_id})
    return result


@app.get("/api/providers/codex/status")
async def codex_status(user=Depends(session_user)):
    try:
        result = await codex.account()
        raw_account = result.get("account") if isinstance(result, dict) else None
        if not raw_account:
            return {"available": True, "account": None}
        account = {
            "type": raw_account.get("type"),
            "planType": raw_account.get("planType"),
        }
        return {"available": True, "account": account}
    except (FileNotFoundError, ProviderError, TimeoutError):
        return {"available": False, "account": None}


@app.post("/api/providers/codex/logout")
async def codex_logout(user=Depends(csrf_user)):
    try:
        result = await codex.logout()
    except (FileNotFoundError, ProviderError, TimeoutError) as exc:
        raise HTTPException(503, "Unable to disconnect the ChatGPT account") from exc
    db.audit(user["username"], "provider.codex_logout", {})
    return result


@app.post("/api/providers/test")
async def provider_test(user=Depends(csrf_user)):
    config = db.get_config()
    instructions = "Return exactly: PROVIDER_OK. Do not call tools."
    try:
        if config.provider.kind == "codex_subscription":
            result = await codex_subscription.complete(
                config.provider.model,
                instructions,
                "Connectivity test",
                config.provider.reasoning_effort,
            )
        else:
            key = db.get_secret("provider_api_key")
            if not key:
                raise ProviderError("Provider API key is not configured")
            base_url = config.provider.base_url or "https://api.openai.com/v1"
            result = await OpenAICompatibleProvider(
                base_url, key, config.provider.timeout_seconds
            ).complete(config.provider.model, instructions, "Connectivity test")
    except ProviderError as exc:
        db.audit(user["username"], "provider.test_failed", {"provider": config.provider.kind})
        raise HTTPException(503, str(exc)) from exc
    db.audit(user["username"], "provider.test_ok", {"provider": config.provider.kind})
    return {"ok": result.strip() == "PROVIDER_OK", "response": result[:200]}


@app.get("/api/readiness")
def readiness(user=Depends(session_user)):
    config = db.get_config()
    secrets_status = db.secret_status()
    checks = {
        "admin": db.has_users(),
        "agent": bool(config.agent.display_name and config.agent.organization),
        "sip": bool(config.sip.host and config.sip.extension and secrets_status["sip_password"]),
        "provider": bool(config.provider.model)
        and (
            config.provider.kind == "codex_subscription" or secrets_status["provider_api_key"]
        ),
        "directory": bool(config.directory),
        "routing": bool(config.routing),
        "safe_defaults": config.safety.require_destination_acceptance and not config.safety.allow_model_tools,
    }
    return {"ready": all(checks.values()), "checks": checks}
