#!/usr/bin/env bash
# Root-side setup for Sentinela on the fitadigital VPS.
# Creates the `sentinela` user, the Apache vhost for sentinela.afrsistemas.com.br
# and the Let's Encrypt certificate. Idempotent: safe to run again.
#
# Layout after this script:
#   /home/sentinela/odoo_sentinela   -> repo + docker compose (done later, as sentinela)
#   /home/sentinela/www              -> built SPA (vite build output)
#   /api/*  -> 127.0.0.1:8197 (FastAPI, prefix stripped, SSE unbuffered)
#   Odoo paths (/web, /odoo, /websocket, ...) -> 127.0.0.1:8196, same domain
set -euo pipefail

DOMAIN="sentinela.afrsistemas.com.br"
APP_USER="sentinela"
API_PORT=8197
ODOO_PORT=8196
VHOST="/etc/apache2/sites-available/015-sentinela.conf"
EMAIL="afonsorcarvalho@gmail.com"

[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }

echo "== 1. user $APP_USER"
if ! id "$APP_USER" &>/dev/null; then
  adduser --disabled-password --gecos "Sentinela" "$APP_USER"
fi
usermod -aG docker "$APP_USER"
install -d -o "$APP_USER" -g "$APP_USER" -m 755 "/home/$APP_USER/www"
chmod 755 "/home/$APP_USER"   # Apache (www-data) must traverse to www/

# Let the fitadigital admin key log in as sentinela too (deploys via ssh).
if [[ -f /home/fitadigital/.ssh/authorized_keys ]]; then
  install -d -o "$APP_USER" -g "$APP_USER" -m 700 "/home/$APP_USER/.ssh"
  touch "/home/$APP_USER/.ssh/authorized_keys"
  cat /home/fitadigital/.ssh/authorized_keys >> "/home/$APP_USER/.ssh/authorized_keys"
  sort -u -o "/home/$APP_USER/.ssh/authorized_keys" "/home/$APP_USER/.ssh/authorized_keys"
  chown "$APP_USER:$APP_USER" "/home/$APP_USER/.ssh/authorized_keys"
  chmod 600 "/home/$APP_USER/.ssh/authorized_keys"
fi

# Placeholder page until the real build is deployed.
[[ -f "/home/$APP_USER/www/index.html" ]] || {
  echo "<h1>Sentinela - em implantacao</h1>" > "/home/$APP_USER/www/index.html"
  chown "$APP_USER:$APP_USER" "/home/$APP_USER/www/index.html"
}

echo "== 2. apache modules"
a2enmod proxy proxy_http proxy_wstunnel headers rewrite ssl >/dev/null

echo "== 3. vhost $VHOST"
cat > "$VHOST" <<EOF
# --- Sentinela (monitoramento CME) ---
<VirtualHost *:80>
    ServerName $DOMAIN
    DocumentRoot /home/$APP_USER/www

    <Directory /home/$APP_USER/www>
        Require all granted
        Options -Indexes
        # SPA: unknown paths fall back to index.html (client-side routing).
        FallbackResource /index.html
    </Directory>

    # Upload of signed files / zips on the authenticity portal.
    LimitRequestBody 52428800

    ProxyPreserveHost On
    ProxyRequests Off
    # flushpackets=on: SSE (/api/stream...) must not be buffered.
    ProxyPass        /api/ http://127.0.0.1:$API_PORT/ flushpackets=on timeout=3600
    ProxyPassReverse /api/ http://127.0.0.1:$API_PORT/
    <Location /api/>
        FallbackResource disabled
    </Location>

    # Odoo on the same domain. SPA only owns /, /login, /area/*, /sensor/*,
    # so these Odoo prefixes don't collide with client-side routes.
    ProxyPass        /websocket ws://127.0.0.1:$ODOO_PORT/websocket
    ProxyPassReverse /websocket ws://127.0.0.1:$ODOO_PORT/websocket
    <LocationMatch "^/(web|odoo|websocket|mail|bus|report|longpolling|sentinela|verificar-autenticidade)(/|$)">
        FallbackResource disabled
    </LocationMatch>
    ProxyPassMatch "^/((web|website|odoo|mail|bus|report|longpolling|sentinela|verificar-autenticidade)(/.*)?)$" http://127.0.0.1:$ODOO_PORT/\$1 timeout=600
    ProxyPassReverse / http://127.0.0.1:$ODOO_PORT/

    RequestHeader set X-Forwarded-Proto "https" env=HTTPS
    RequestHeader set X-Forwarded-Proto "http"  env=!HTTPS
</VirtualHost>
EOF
a2ensite 015-sentinela >/dev/null
apache2ctl configtest
systemctl reload apache2

echo "== 4. certificate"
certbot --apache -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL" --redirect

echo "== 5. check"
curl -fsS -o /dev/null -w "https://$DOMAIN -> %{http_code}\n" "https://$DOMAIN/"
echo "OK. Next: deploy stack as $APP_USER (non-root part)."
