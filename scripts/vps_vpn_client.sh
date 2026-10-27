#!/usr/bin/env bash
# Root: create an OpenVPN client cert on the fitadigital VPS (angristan
# openvpn-install layout) and write a self-contained .ovpn for a Sentinela hub.
#   sudo bash vps_vpn_client.sh hub-oximed-01
# Output: /home/sentinela/vpn/<name>.ovpn (owner sentinela, 600). Idempotent.
set -euo pipefail

NAME="${1:?usage: $0 <client-name>}"
EASY=/etc/openvpn/easy-rsa
OUT_DIR=/home/sentinela/vpn
OUT="$OUT_DIR/$NAME.ovpn"

[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }

cd "$EASY"
if [[ ! -f "pki/issued/$NAME.crt" ]]; then
  EASYRSA_CERT_EXPIRE=3650 ./easyrsa --batch build-client-full "$NAME" nopass
fi

install -d -o sentinela -g sentinela -m 700 "$OUT_DIR"
{
  cat /etc/openvpn/client-template.txt
  echo "<ca>";        cat "$EASY/pki/ca.crt";                                   echo "</ca>"
  echo "<cert>";      awk '/BEGIN/,/END CERTIFICATE/' "$EASY/pki/issued/$NAME.crt"; echo "</cert>"
  echo "<key>";       cat "$EASY/pki/private/$NAME.key";                        echo "</key>"
  echo "<tls-crypt>"; cat /etc/openvpn/tls-crypt.key;                           echo "</tls-crypt>"
} > "$OUT"
chown sentinela:sentinela "$OUT"
chmod 600 "$OUT"
echo "OK: $OUT"
