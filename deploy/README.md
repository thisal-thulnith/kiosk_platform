# Going live: OVH server + Cloudflare

Written for: whoever runs the platform's server. Two addresses:
- **`app.<your-domain>`**: restaurants (screens at `/<code>/pos`, owners at `/<code>/owner`, tablets
  sign in at `/<code>`).
- **`admin.<your-domain>`**: our team (Platform console, each restaurant's Setup console). The team
  login works only here.

## 1. Cloudflare (once, about 5 minutes)

In the Cloudflare dashboard, open your domain:

1. **DNS → Records → Add record**, twice:

   | Type | Name | IPv4 address | Proxy status |
   |---|---|---|---|
   | A | `app` | `15.235.207.30` | Proxied (orange cloud) |
   | A | `admin` | `15.235.207.30` | Proxied (orange cloud) |

   Optional, for IPv6 too: the same two names as **AAAA** to `2402:1f00:8000:800::3f7d`.
2. **SSL/TLS → Overview → Full (strict).** Cloudflare encrypts visitors ↔ Cloudflare; the server's
   own certificate (Let's Encrypt, free, made and renewed by itself) encrypts Cloudflare ↔ server.
3. **SSL/TLS → Edge Certificates:** turn on **Always Use HTTPS**, and set **Minimum TLS Version** to
   1.2.
4. **Network:** **WebSockets** on (it is on by default). Screens use it for live updates.
5. Leave **Rocket Loader** off. Caching: nothing to change. The app sends the right cache headers
   itself (its built files are cached for a year; pages and the API are never cached).

If the server can't get its certificate in the first minutes (rare with the orange cloud): set both
records to **DNS only** (grey cloud), wait two minutes, then turn **Proxied** back on.

## 2. The server (done once by setup.sh)

- **Server:** Ubuntu with Docker, a firewall (only SSH 22, HTTP 80, HTTPS 443 open), fail2ban and
  automatic security updates.
- **The app:** in `/opt/kiosk`. Its secrets are in `/opt/kiosk/deploy/.env`, made once and kept
  private. Keep a copy of that file somewhere safe: `DATA_KEY` decrypts stored payment keys.
- **Containers:** `db` (Postgres 16), `app`, `caddy` (HTTPS) and `backup` (a database dump every
  night at 03:00; the last 14 are kept in `/opt/kiosk/deploy/backups`).

```bash
cd /opt/kiosk
sudo DOMAIN=app.<your-domain> ADMIN_DOMAIN=admin.<your-domain> ACME_EMAIL=you@example.com bash deploy/setup.sh
cd deploy && sudo docker compose exec app uv run --no-sync kiosk create-platform-admin --email you@example.com --password '<long password>'
```

## 3. Everyday commands (on the server, in `/opt/kiosk/deploy`)

| What | Command |
|---|---|
| Status | `sudo docker compose ps` |
| Logs | `sudo docker compose logs -f app` |
| Update to a new version | copy the new code to `/opt/kiosk`, then `sudo docker compose up -d --build` (database changes apply by themselves) |
| Restart | `sudo docker compose restart app` |
| Backup now | `sudo docker compose exec backup sh -c 'pg_dump -h db -U kiosk kiosk \| gzip > /backups/manual-$(date +%F).sql.gz'` |
| Restore a backup | `gunzip -c backups/<file>.sql.gz \| sudo docker compose exec -T db psql -U kiosk kiosk` (into an empty database) |
| Turn on the kiosk / status board | set `COMING_SOON=` in `.env`, then `sudo docker compose up -d` |

## 4. Not live yet

QR payments and integrated card readers need a payment provider account and its connection. Test
payments are switched off on the live server. Cash, and card on the bank's own machine (the waiter or
cashier types the approval code), work from day one.
