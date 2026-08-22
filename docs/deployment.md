# Despliegue

## Requisitos

- Host Linux dentro de la red de la PBX.
- Docker Engine con Compose.
- Un interno SIP dedicado.
- Conectividad SIP y RTP entre el host y la PBX.
- Proveedor STT/TTS y modelo, o alternativas locales configuradas.

## Instalación

```bash
./scripts/bootstrap.sh
docker compose up -d --build
docker compose ps
curl -fsS http://127.0.0.1:8080/api/health
```

`bootstrap.sh` crea `.env` y `secrets/master_key` con permisos restrictivos. No los copies al repositorio.

## Acceso web

Por defecto escucha en `127.0.0.1:8080`. Para operación remota, preferí un proxy HTTPS o túnel autenticado. Si necesitás escuchar en la LAN, definí explícitamente:

```dotenv
VAS_BIND_HOST=0.0.0.0
VAS_HTTP_PORT=8080
VAS_SECURE_COOKIES=false
```

Aplicá firewall y HTTPS antes de exponerlo fuera de una red confiable.

## Datos requeridos de la PBX

- servidor o dominio;
- puerto SIP;
- UDP o TCP;
- interno;
- usuario de autenticación si difiere del interno;
- contraseña;
- codecs habilitados;
- permisos de llamada a los internos de transferencia.

No se requiere instalar software en la PBX ni cambiar su dialplan, salvo dirigir llamadas al interno asignado según la operación habitual de esa PBX.

## Criterio de aceptación

1. El dashboard informa proceso SIP activo.
2. La PBX confirma `REGISTER` y el dashboard informa registrado.
3. Una llamada nueva llega y se autoatiende.
4. Saludo y respuesta TTS se oyen completos.
5. STT reconoce una frase representativa.
6. Se validan silencio, timeout y corte remoto.
7. Se prueba una transferencia aceptada, una rechazada y una sin respuesta.
8. Se confirma limpieza de ambas piernas y ausencia de procesos duplicados.

## Respaldo

Respaldar juntos:

- volumen `studio-data`;
- `secrets/master_key`.

Sin la clave maestra no pueden recuperarse los secretos cifrados. Verificá restauración en una instancia aislada.
