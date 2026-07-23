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
  **Public key**, colando a `ssh_hub.pub`. Diretório `/uploads` com **escrita e
  `create_dirs`** — o Hub cria a árvore por cliente/data antes do upload (ver
  "Layout de `/uploads`" abaixo). Sem `create_dirs`, o `mkdir` é negado, o upload
  falha e o Hub apenas registra a falha e tenta de novo no ciclo seguinte
  (`[hub] falha ao enviar ...`); nenhum arquivo sobe.
- **Registro de coletores**: registrar a pubkey EC de assinatura (para validar o
  arquivo). Com a pubkey PEM em mãos:
  ```python
  from ingestao import registro_coletores
  registro_coletores.registrar_coletor(
      "ingestao/coletores_conhecidos.json", "COL-RS485-BUS0", PEM_DA_PUBKEY_EC)
  ```

## 2b. Layout de `/uploads`

O Hub envia para uma árvore por cliente/data:

```
/uploads/{cliente_id}/AAAA/MM/DD/{site_id}/{hub_id}/{coletor_id}/AAAA-MM-DD_{hub_id}-{coletor_id}_leituras.txt
```

`cliente_id`/`site_id` vêm da config do Hub (obrigatórios quando há bloco `sftp`;
o Hub falha no boot se faltarem ou tiverem `/`). O segmento `{hub}-{coletor}` do
nome do arquivo é redundância legível — a verdade é o cabeçalho assinado dentro
do arquivo; não escreva parser reverso em cima do nome.

**O acervo é misto, por decisão explícita: os arquivos antigos NÃO foram migrados.**
Eles continuam planos na raiz (`/uploads/AAAA-MM-DD_leituras.txt`), e tanto o
watcher de ingestão quanto o confronto de veracidade cobrem os dois formatos.
Consequência operacional: **`rm -rf /uploads/{cliente}/AAAA/` não alcança os
legados** — qualquer limpeza/retenção precisa tratar a raiz plana separadamente.

## 3. Gatilho da ingestão (pós-upload)

**Neste deployment o gatilho real é o `scripts/watcher_ingestao.py`, rodando no
host** — ele varre `/uploads` recursivamente por SFTP e chama
`ingestor.ingerir_arquivo`. O container do SFTPGo não tem Python, e o Event
Manager está sem nenhuma regra configurada (`events_rules`/`events_actions`
vazias): a receita abaixo é a alternativa, ainda **não** em uso.

<details>
<summary>Alternativa (não configurada): Event Manager do SFTPGo</summary>

No WebAdmin do SFTPGo → **Event Manager** → nova regra:
- **Trigger:** Filesystem event `upload`.
- **Action:** Run command → `python3 -m ingestao.receber_upload {{VirtualPath}}`
  (ajustar working dir/PYTHONPATH conforme o volume `/opt/ingestao` montado).
- **Env:** `SENTINELA_REGISTRO`, `SENTINELA_DSN`, `SENTINELA_ODOO_URL`,
  `SENTINELA_ODOO_DB`, `SENTINELA_ODOO_USER`, `SENTINELA_ODOO_SENHA`.

</details>

## 4. Teste cross-machine
No Pi, editar `~/sentinela-hub/config.yaml` com o bloco `sftp` apontando pra
`host: 10.8.0.1` (o servidor pela VPN) e rodar:
```bash
python -m hub.main --config ~/sentinela-hub/config.yaml   # Ctrl+C sela + envia
```
Verificar no servidor:
- arquivo em `/uploads/{cliente_id}/AAAA/MM/DD/{site_id}/{hub_id}/{coletor_id}/`
  no home do hub (`find /uploads -name '*_leituras.txt'`);
- linha nova no TimescaleDB (`SELECT count(*) FROM leituras WHERE coletor_id='COL-RS485-BUS0';`);
- entrada no `file.ledger` do Odoo, status `valido`.

## Pendências para fatias seguintes
- **T2:** ack de validação de volta ao Hub via MQTT; bridge MQTT local→central.
- **T3:** OpenVPN — restringir o binding do SFTPGo à interface da VPN (remover a
  exposição `2022` no LAN).
