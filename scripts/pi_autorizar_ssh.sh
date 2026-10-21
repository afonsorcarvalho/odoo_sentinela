#!/usr/bin/env bash
# Autoriza a chave SSH desta máquina num Pi novo (pede a senha UMA vez, no
# terminal — ela não passa pelo chat nem fica gravada em lugar nenhum).
#
# Uso: ./scripts/pi_autorizar_ssh.sh USUARIO [IP]      (IP padrão: 192.168.0.221)
set -euo pipefail

USUARIO=${1:?uso: $0 USUARIO [IP]}
IP=${2:-192.168.0.221}
CHAVE=$HOME/.ssh/id_ed25519_sentinela_pi

[ -f "$CHAVE" ] || ssh-keygen -t ed25519 -N '' -C "sentinela-pi-$(hostname)" -f "$CHAVE"

ssh-copy-id -i "$CHAVE.pub" -o StrictHostKeyChecking=accept-new "$USUARIO@$IP"

# Alias para os próximos comandos: `ssh sentinela-pi`
if ! grep -q '^Host sentinela-pi$' "$HOME/.ssh/config" 2>/dev/null; then
    cat >> "$HOME/.ssh/config" <<CFG

Host sentinela-pi
    HostName $IP
    User $USUARIO
    IdentityFile $CHAVE
    IdentitiesOnly yes
CFG
fi

echo "---"
ssh -o BatchMode=yes sentinela-pi 'echo "OK sem senha em $(hostname)"; uname -m; cat /etc/os-release | head -2; cat /proc/device-tree/model 2>/dev/null; echo'
