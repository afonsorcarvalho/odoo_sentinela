#!/bin/bash
# Run as root on the VPS: lets Apache serve the SPA route /relatorios
# (otherwise it is proxied to Odoo and returns 404).
set -euo pipefail
cd /etc/apache2/sites-available
for f in 015-sentinela.conf 015-sentinela-le-ssl.conf; do
    [ -f "$f" ] || continue
    grep -q 'relatorios' "$f" && { echo "$f: already ok"; continue; }
    cp -a "$f" "$f.bak-$(date +%Y%m%d-%H%M)"
    sed -i 's#|sensor/\.\*)\$" !#|sensor/.*|relatorios)$" !#' "$f"
    grep -n 'ProxyPassMatch' "$f"
done
apachectl configtest
systemctl reload apache2
echo "ok"
