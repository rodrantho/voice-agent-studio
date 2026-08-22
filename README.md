# Voice Agent Studio

**Español** | [English](README.en.md) | [Deutsch](README.de.md)

Aplicación web autogestionada para instalar un agente telefónico en la misma red que una PBX y registrarlo como un interno SIP normal.

## Funcionamiento

```text
PBX existente ← SIP/RTP → Voice Agent Studio
                              ├─ Linphone headless
                              ├─ STT
                              ├─ modelo de lenguaje
                              ├─ TTS
                              └─ consulta y transferencia atendida
```

La aplicación **no instala ni administra la PBX**. El operador solamente crea o entrega un interno SIP dedicado y configura sus datos desde el navegador.

## Capacidades

- Registro SIP directo por UDP o TCP.
- Autoatención de llamadas entrantes.
- Conversación por turnos con detección de voz y silencio.
- STT: OpenAI, Deepgram o comando local administrado por el servidor.
- TTS: OpenAI, ElevenLabs o Piper local.
- Modelos OpenAI-compatible y conexión experimental ChatGPT/Codex.
- Directorio y rutas determinísticas.
- Consulta a un interno, aceptación explícita y transferencia atendida.
- Secretos cifrados, sesiones administrativas, CSRF y auditoría.
- Diagnóstico de proceso y registro SIP desde el dashboard.

## Instalación

Requisitos: Linux, Docker Engine y Docker Compose.

```bash
git clone https://github.com/rodrantho/voice-agent-studio.git
cd voice-agent-studio
./scripts/bootstrap.sh
docker compose up -d --build
```

Abrí `http://127.0.0.1:8080`. Para acceso desde otra máquina, publicalo mediante un proxy HTTPS o configurá explícitamente `VAS_BIND_HOST` en `.env`.

## Configuración inicial

1. Crear el administrador.
2. Cargar identidad y conocimiento del agente.
3. Cargar servidor, puerto, transporte, interno, usuario y clave SIP.
4. Pulsar **Guardar y conectar** y comprobar `Registrado`.
5. Configurar modelo, STT y TTS.
6. Cargar destinos y reglas de transferencia.
7. Ejecutar las pruebas de proveedor y voz.
8. Llamar al interno del agente.

La PBX controla troncales, permisos, numeración y rutas. Un error de autenticación, timeout o rechazo se muestra como estado SIP; la aplicación no intenta modificar la PBX.

## Seguridad

- Dashboard ligado a loopback por defecto.
- Clave maestra fuera de la imagen y del repositorio.
- Secretos cifrados en SQLite.
- Runtime no privilegiado después del arranque.
- Sin Docker socket, shell ni herramientas disponibles para las llamadas.
- Destinos de transferencia por allowlist.
- Consentimiento ambiguo falla cerrado.
- Llamadas externas deshabilitadas por defecto.
- Grabación y retención deshabilitadas por defecto.

## Alcance operativo

Las pruebas automatizadas validan configuración, políticas, control SIP y seguridad. La aceptación de una instalación requiere una llamada real con el interno dedicado: `REGISTER`, llamada entrante, audio bidireccional, STT, TTS y transferencia. Un registro SIP correcto por sí solo no prueba el audio.

## Desarrollo

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/ruff check .
.venv/bin/pytest -q
```

Licencia: AGPL-3.0-only.
