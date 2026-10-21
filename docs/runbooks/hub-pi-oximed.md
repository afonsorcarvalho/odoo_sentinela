# Runbook — Hub HUB-OXIMED-01 (Pi 3B + N4AIB16 direto na serial)

Pi `hubsentinela` (`fitadigital@192.168.0.221`, alias ssh `sentinela-pi`, Debian 13, py3.13).
Acesso por chave: `scripts/pi_autorizar_ssh.sh fitadigital 192.168.0.221` (pede a senha uma vez).

- Código: `rsync -a --delete --exclude __pycache__ --exclude tests hub contrato sentinela-pi:odoo_sentinela/`
  (o Pi não tem credencial do GitHub). venv em `~/odoo_sentinela/.venv`.
- Odoo: `python -m scripts.provisionar_oximed` (cliente OXIMED `ref=OXIMED` → SITE-001
  `industrial_generico` → hub → coletor `COL-OXIMED-BUS0` → bus `/dev/ttyUSB0` 9600 8N1 →
  N4AIB16 addr 1 → sensor `SNR-OXIMED-ETO-01`, CH1, 4-20 mA → 0-100 ppm). Idempotente.
- Chaves no Pi (`~/sentinela-hub/chaves`, 600): `coletor.pem` (assinatura; pubkey em
  `coletor.pubkey_pem` no Odoo **e** em `ingestao/coletores_conhecidos.json`) e `ssh_hub`
  (pubkey no usuário SFTPGo `hub-oximed-01`).
- SFTPGo `hub-oximed-01`: só chave; `/uploads/OXIMED` (list/download/upload/overwrite/create_dirs,
  sem delete) e `/config/HUB-OXIMED-01` (list/download). Home compartilhado com `sentinela-config-svc`.
- `~/sentinela-hub/identity.yaml` aponta MQTT/SFTP para `192.168.0.204` (portproxy do Windows).
- **O hub não sobe sem `config.yaml`** (o runbook da Fase 5 dizia o contrário). Bootstrap: baixar
  `config-vN.yaml` por SFTP e gravar `fundir(identity, operacional)` — ver histórico desta sessão;
  depois o agente mantém sozinho via notify retido.
- Serviço: `sentinela-hub.service` (systemd, `enable`, SIGTERM sela o dia, `Restart=always`).
  Logs: `journalctl -u sentinela-hub -f`. Publicar nova config: botão no hub no Odoo
  (ou `action_publicar_config`); a api precisa estar de pé (`docker compose up -d api`).
- Porta estável: `/dev/serial/by-id/usb-Silicon_Labs_CP2102N_…` (CP2102N). Hoje usa `/dev/ttyUSB0`.
