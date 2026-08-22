# Deployment

## Recommended topology

Deploy the control plane beside the PBX or on a server connected through a private routed tunnel. Administer it through SSH port forwarding, VPN, Tailscale or an authenticated reverse proxy.

```bash
ssh -L 8080:127.0.0.1:8080 server
```

Then browse to `http://127.0.0.1:8080`.

## Firewall

The default control plane needs outbound HTTPS and local TCP/8080. The optional gateway needs:

- SIP to the PBX, usually UDP/5060 or the verified PBX port;
- configured UDP RTP range;
- no public ARI/AMI exposure.

## Backup

Back up:

- the named `studio-data` volume;
- the master key from the external secret store;
- the deployment manifests and non-secret configuration.

Do not archive the generated `asterisk-config` volume as ordinary configuration: it contains the rendered SIP credential. Recreate it from the encrypted application store after restoration.

## Applying gateway configuration

1. Save the SIP password in the dashboard.
2. Save the validated SIP settings.
3. Review **Generate preview**; it contains a placeholder, not the password.
4. Select **Apply to gateway**.
5. The control plane atomically replaces only `pjsip.conf`, `extensions.conf` and `rtp.conf` in the private volume.
6. The gateway watcher copies them with mode `0600` and runs `core reload`.

Apply only in a call-free window. A malformed upstream PBX value can still cause registration loss even though the schema blocks arbitrary config injection.

Test restoration on an isolated host. A database backup without the master key cannot recover secrets.

## Upgrade

1. Back up data and the master key.
2. Pull the reviewed release tag.
3. Build without using mutable `latest` dependencies.
4. Run unit and API tests.
5. Recreate only the control-plane service first.
6. Verify health and login.
7. Upgrade the gateway during a call-free window.
