# Arquitectura

## Componentes

```text
Navegador
   │ HTTPS/HTTP local
   ▼
FastAPI
   ├─ configuración y diagnóstico
   ├─ SQLite + secretos Fernet
   ├─ políticas y directorio
   ├─ proveedores de modelo/STT/TTS
   └─ controlador Linphone
             │ SIP/RTP
             ▼
         PBX existente
```

La aplicación es un endpoint SIP. No contiene una PBX ni un gateway telefónico.

## Runtime de llamadas

1. Linphone registra el interno configurado.
2. Autoatiende una llamada entrante.
3. Cambia a audio por archivos y reproduce el saludo.
4. Captura audio hasta detectar voz seguida del silencio configurado.
5. Finaliza el WAV y ejecuta STT.
6. La máquina de estados determina si debe preguntar un dato, responder o consultar un destino.
7. El modelo genera únicamente texto hablado; no decide ni ejecuta transferencias.
8. TTS genera WAV PCM mono a 8 kHz y Linphone lo reproduce una sola vez.
9. Para transferir, el runtime pide consentimiento al llamante, llama al destino permitido, pide aceptación y ejecuta transferencia atendida.
10. Rechazo, silencio, timeout o ambigüedad fallan cerrado.

## Límites deliberados

- Conversación turn-based, no full-duplex streaming.
- Una conversación activa por instancia; llamadas concurrentes adicionales se rechazan.
- UDP/TCP; TLS SIP no se anuncia hasta implementar certificados y validación completos.
- La PBX sigue siendo responsable de permisos y enrutamiento.

## Límites de confianza

- El navegador nunca recibe secretos descifrados.
- El proceso SIP recibe sólo la cuenta configurada y medios de la llamada.
- El modelo recibe contexto y texto acotados, sin filesystem, shell ni herramientas.
- Los destinos posibles provienen del directorio autorizado.
- El contenedor no accede al socket Docker ni a datos de otros agentes.
