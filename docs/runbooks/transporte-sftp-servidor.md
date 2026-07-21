# Runbook — Transporte SFTP (lado-servidor) e teste cross-machine

Passos executados **no VPS de produção `191.252.113.190` (`sistema.fitadigital.com.br`)**,
onde roda o `docker-compose`. O Hub (Raspberry Pi) **já está na VPN** (`tun0=10.8.0.19`)
e alcança o servidor em **`10.8.0.1`** — o SFTPGo deve escutar na interface da VPN, não
publicamente. O cliente OpenVPN do Pi já é mantido pelo projeto `openvpn-config-updater`.

## 1. Subir o SFTPGo
```bash
docker compose up -d sftpgo
# WebAdmin em http://<servidor>:8190 (criar admin no primeiro acesso)
```

## 2. Provisionar o Hub no servidor
No Pi, obter as duas chaves públicas do Hub:
```bash
# pubkey SSH (para o SFTPGo autenticar o upload)
cat ~/sentinela-hub/chaves/ssh_hub.pub

# pubkey EC de assinatura (para a ingestão validar o arquivo)
python - <<'PY'
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from contrato import identidade
k = identidade.carregar_ou_criar_chave(Path("~/sentinela-hub/chaves/coletor.pem").expanduser())
print(k.public_key().public_bytes(serialization.Encoding.PEM,
      serialization.PublicFormat.SubjectPublicKeyInfo).decode())
PY
```
No servidor:
- **SFTPGo**: criar um usuário (ex. `hub-0001A2F3`), home isolado, método de login
  **Public key**, colando a `ssh_hub.pub`. Diretório `/uploads` com escrita.
- **Registro de coletores**: registrar a pubkey EC de assinatura (para validar o
  arquivo). Com a pubkey PEM em mãos:
  ```python
  from ingestao import registro_coletores
  registro_coletores.registrar_coletor(
      "ingestao/coletores_conhecidos.json", "COL-RS485-BUS0", PEM_DA_PUBKEY_EC)
  ```

## 3. Ligar o Event Manager (pós-upload → ingestão)
No WebAdmin do SFTPGo → **Event Manager** → nova regra:
- **Trigger:** Filesystem event `upload`.
- **Action:** Run command → `python3 -m ingestao.receber_upload {{VirtualPath}}`
  (ajustar working dir/PYTHONPATH conforme o volume `/opt/ingestao` montado).
- **Env:** `SENTINELA_REGISTRO`, `SENTINELA_DSN`, `SENTINELA_ODOO_URL`,
  `SENTINELA_ODOO_DB`, `SENTINELA_ODOO_USER`, `SENTINELA_ODOO_SENHA`.

## 4. Teste cross-machine
No Pi, editar `~/sentinela-hub/config.yaml` com o bloco `sftp` apontando pra
`host: 10.8.0.1` (o servidor pela VPN) e rodar:
```bash
python -m hub.main --config ~/sentinela-hub/config.yaml   # Ctrl+C sela + envia
```
Verificar no servidor:
- arquivo em `/uploads` no home do hub;
- linha nova no TimescaleDB (`SELECT count(*) FROM leituras WHERE coletor_id='COL-RS485-BUS0';`);
- entrada no `file.ledger` do Odoo, status `valido`.

## Pendências para fatias seguintes
- **T2:** ack de validação de volta ao Hub via MQTT; bridge MQTT local→central.
- **T3:** OpenVPN — restringir o binding do SFTPGo à interface da VPN (remover a
  exposição `2022` no LAN).
