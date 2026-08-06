# MediaHub external access

MediaHub can be used outside Home Assistant without giving the user a Home Assistant account. The app exposes a dedicated authenticated interface on TCP port `8100` while retaining Home Assistant Ingress on internal port `8099`.

## Security boundary

- Publish only MediaHub port `8100` through an HTTPS reverse proxy or tunnel.
- Never publish port `8099`, Home Assistant Ingress, Prowlarr, Radarr, Sonarr, qBittorrent, or their API ports.
- Do not forward port `8100` directly from the internet without HTTPS.
- Public self-registration is intentionally unavailable.

The external listener ignores all `X-Remote-User-*` headers. It cannot be used to impersonate a Home Assistant user. It accepts only a valid MediaHub session created by the password login screen.

## Create the first external account

1. Update and restart the MediaHub app.
2. Open MediaHub from the Home Assistant sidebar while signed in as its administrator.
3. Open **Users**.
4. Enter a display name, username, password of at least 12 characters, and role.
5. Select **Create account**.
6. Give the username and password to the user through a private channel.

Use `requester` for a person who should browse, request, and see only their own history. Use `manager` only when the person should see all household requests and operational status. Do not use `admin` unless they should manage integrations, audit data, and other users.

## Verify local access

After the app restarts, Home Assistant maps container port `8100` to host port `8100`. On the home network, open:

```text
http://HOME_ASSISTANT_IP:8100
```

The MediaHub login screen should appear. Sign in with the MediaHub account, not a Home Assistant, qBittorrent, Prowlarr, or IPTorrents account.

## Publish the HTTPS address

Create one HTTPS route in the chosen reverse proxy or tunnel:

```text
Public hostname: https://media.williams.digital
Origin service:  http://HOME_ASSISTANT_IP:8100
```

The proxy must preserve normal `Host` and `X-Forwarded-Proto` headers. WebSockets are not required by the current interface. MediaHub uses the forwarded HTTPS scheme only to mark its session cookie `Secure`.

Do not configure the public route to the Home Assistant URL, its Ingress path, or port `8099`. The external port is a separate security boundary designed for this purpose.

## User administration

Open the **Users** page as a MediaHub administrator to:

- create another MediaHub account;
- change a role;
- disable or re-enable an account;
- reset a MediaHub password.

Disabling an account or resetting its password signs out every current session for that account. MediaHub prevents the final active administrator from being disabled or demoted.
