# Voice Agent Studio

[Español](README.md) | [English](README.en.md) | **Deutsch**

Eine selbst gehostete Webanwendung zur Bereitstellung eines Telefonagenten im selben Netzwerk wie eine vorhandene Telefonanlage. Der Agent registriert sich dort als normale SIP-Nebenstelle.

## Funktionsweise

```text
Vorhandene PBX ← SIP/RTP → Voice Agent Studio
                                  ├─ Headless Linphone
                                  ├─ STT
                                  ├─ Sprachmodell
                                  ├─ TTS
                                  └─ Rückfrage und vermittelte Weiterleitung
```

Die Anwendung **installiert und verwaltet die Telefonanlage nicht**. Der Betreiber erstellt oder stellt lediglich eine dedizierte SIP-Nebenstelle bereit und konfiguriert deren Zugangsdaten im Browser.

## Funktionen

- Direkte SIP-Registrierung über UDP oder TCP.
- Automatische Annahme eingehender Anrufe.
- Rundenbasierte Gespräche mit Sprach- und Stilleerkennung.
- STT über OpenAI, Deepgram oder einen serverseitig verwalteten lokalen Befehl.
- TTS über OpenAI, ElevenLabs oder lokales Piper.
- OpenAI-kompatible Modelle und experimentelle ChatGPT/Codex-Anbindung.
- Deterministische Verzeichnis- und Routingregeln.
- Rückfrage bei einer Nebenstelle, ausdrückliche Annahme und vermittelte Weiterleitung.
- Verschlüsselte Geheimnisse, Administratorsitzungen, CSRF-Schutz und Audit-Protokollierung.
- Prozess- und SIP-Registrierungsdiagnose im Dashboard.

## Installation

Voraussetzungen: Linux, Docker Engine und Docker Compose.

```bash
git clone https://github.com/rodrantho/voice-agent-studio.git
cd voice-agent-studio
./scripts/bootstrap.sh
docker compose up -d --build
```

Öffnen Sie `http://127.0.0.1:8080`. Für den Zugriff von einem anderen Rechner veröffentlichen Sie den Dienst über einen HTTPS-Reverse-Proxy oder konfigurieren `VAS_BIND_HOST` ausdrücklich in `.env`.

## Erstkonfiguration

1. Administratorkonto erstellen.
2. Identität und Wissensbasis des Agenten konfigurieren.
3. SIP-Server, Port, Transport, Nebenstelle, Benutzername und Passwort eingeben.
4. **Speichern und verbinden** auswählen und den Status `Registriert` prüfen.
5. Sprachmodell sowie STT- und TTS-Anbieter konfigurieren.
6. Weiterleitungsziele und Routingregeln hinzufügen.
7. Anbieter- und Sprachtests ausführen.
8. Die Nebenstelle des Agenten anrufen.

Die Telefonanlage kontrolliert Trunks, Berechtigungen, Nummerierung und Routing. Authentifizierungsfehler, Zeitüberschreitungen und Ablehnungen werden als SIP-Status angezeigt; die Anwendung versucht nicht, die Telefonanlage zu verändern.

## Sicherheit

- Das Dashboard ist standardmäßig nur an Loopback gebunden.
- Der Hauptschlüssel bleibt außerhalb des Images und des Repositorys.
- Geheimnisse werden verschlüsselt in SQLite gespeichert.
- Die Laufzeitumgebung arbeitet nach dem Start ohne Root-Rechte.
- Anrufe haben keinen Zugriff auf Docker-Socket, Shell oder Werkzeuge.
- Weiterleitungsziele werden über eine Positivliste eingeschränkt.
- Uneindeutige Zustimmung führt zu einem sicheren Abbruch.
- Externe Anrufe sind standardmäßig deaktiviert.
- Aufzeichnung und Aufbewahrung sind standardmäßig deaktiviert.

## Betrieblicher Umfang

Automatisierte Tests prüfen Konfiguration, Richtlinien, SIP-Steuerung und Sicherheit. Für die Abnahme einer Installation ist ein echter Anruf über die dedizierte Nebenstelle erforderlich: `REGISTER`, eingehender Anruf, bidirektionales Audio, STT, TTS und Weiterleitung. Eine erfolgreiche SIP-Registrierung allein beweist nicht, dass die Audioübertragung funktioniert.

## Entwicklung

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/ruff check .
.venv/bin/pytest -q
```

Lizenz: AGPL-3.0-only.
