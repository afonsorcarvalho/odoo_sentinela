# Runbook de deploy — detecção de leitura implausível + self-healing serial

Branch `feat/deteccao-implausivel-selfhealing`. Instância de **produção persistente**
(dashboard ao vivo, hub em campo). O código foi aprovado no review final; este
runbook é o **gate operacional** — a ordem errada quebra o config-publish de todos
os hubs OU faz a ingestão rejeitar todo arquivo do hub.

## O que a branch muda (impacto de deploy)

1. **Cabeçalho do arquivo de leituras sobe para schema v3** (ganha uma linha
   `# colunas:`). O validador/ingestor/confronto desta branch aceitam v2 **e** v3.
   Um validador **v2 antigo REJEITA v3** (rejeição dura — provado no review).
2. **config-publisher** (`api/config_publisher.py`) passa a pedir
   `usa_faixa/faixa_min/faixa_max` e `reconexao_n/m/k` no `search_read`
   **incondicionalmente**. Se o DB Odoo não tiver esses campos → `Invalid field`
   → quebra o config-publish de **todos** os hubs.
3. **Hub** passa a emitir v3, aplicar o gate de faixa e o self-healing serial.

## DOIS gates de deploy

- **Gate A — Odoo antes da API.** Migrar o addon no DB de produção antes de subir
  a API nova.
- **Gate B — ingestão v3-aware antes do hub v3.** O gatilho de ingestão é o
  processo **host-side** `scripts/watcher_ingestao.py`, **não** o container `api`.
  Reiniciar o container `api` **NÃO** reinicia o watcher (Python não hot-reloada).
  O watcher/validador precisa estar nesta branch **antes** de qualquer hub começar
  a emitir v3, senão todo arquivo v3 vira `invalido`.

## Ordem segura (3 passos)

### 1. Migrar o Odoo (destrava Gate A)
```bash
# (1a) upgrade in-place do addon no DB de produção — adiciona os campos novos
#      (aditivo, não-destrutivo). Roda como PROCESSO SEPARADO (--stop-after-init).
docker exec odoo_sentinela-odoo-1 odoo -u afr_sentinela_sensor_monitor \
    -d sentinela --stop-after-init --http-port=8169

# (1b) OBRIGATÓRIO: reiniciar o container Odoo pra recarregar o registry.
docker compose restart odoo
```
**Por que (1b) é obrigatório (aprendido em campo 2026-07-25):** o `--stop-after-init`
migra o SCHEMA do DB, mas o processo do servidor Odoo **em execução** continua com o
registry ANTIGO em memória (carregado no boot, horas antes). O "Registry changed,
signaling through the database" que aparece no log **NÃO** faz o servidor vivo
recarregar de forma confiável — o resultado observado foi `ValueError: Invalid field
'usa_faixa'` em toda chamada XML-RPC (MCP, e o próprio config-publish). Sem o restart
do container, o Gate A parece migrado (colunas existem no DB via `psql`) mas o Odoo
vivo não enxerga os campos. `docker compose restart odoo` força um registry fresco.

Depois confirme o Odoo vivo (aguarde subir):
`curl -s -o /dev/null -w "%{http_code}" http://localhost:8189/web/login` → `200`.
E confirme que o campo aparece no runtime (não só no schema):
```bash
docker exec odoo_sentinela-db-1 psql -U odoo -d sentinela -tAc \
  "SELECT column_name FROM information_schema.columns \
   WHERE table_name='sensor_monitor_sensor' AND column_name='usa_faixa';"
# → usa_faixa   (schema OK; o restart em 1b garante o runtime também)
```
Nota: `--http-port=8169` porque a 8069 do servidor vivo está ocupada no mesmo
container; `--no-http` sozinho não basta em modo upgrade.

### 2. Servidor — DUAS ações de restart (destrava Gate B)
No working tree do servidor já nesta branch (código atualizado):

**(a) Container `api`** (config-publisher com os campos novos):
```bash
docker compose up -d --build api        # ou o fluxo de build/deploy da api
```
**(b) Processo host-side `watcher_ingestao`** — restart do `api` NÃO faz isto:
```bash
# parar o watcher antigo e subir o novo (código desta branch)
pkill -f watcher_ingestao
PYTHONPATH=/home/afonso/docker/odoo_sentinela \
  nohup .venv/bin/python -u scripts/watcher_ingestao.py >> /tmp/watcher.log 2>&1 &
```
(GOTCHA já conhecido: o watcher precisa de `PYTHONPATH=<repo>` + `.venv/bin/python`
e `-u`, senão `ModuleNotFoundError: ingestao` / log cego.)

Após (a)+(b), a ingestão aceita v2 e v3, e o config-publish enxerga os campos novos.

### 3. Bump do submódulo + deploy do hub
Só depois de 1 e 2. O hub passa a emitir v3, aplicar o gate e o self-healing.
No Pi: `git pull` no repo do hub + `~/sentinela-hub/restart_hub.sh`.

## Por que a janela é segura

- O hub **antigo** ignora chaves de config desconhecidas (`hub/config.py` constrói
  por kwargs explícitos, não `**d`) → a API nova pode republicar config com
  `faixa`/`reconexao` para hubs velhos **sem derrubá-los**. Não há gate quebrável
  entre API e hub — só os dois acima.
- Arquivos v2 legados no acervo continuam válidos (o validador desta branch aceita
  os dois; provado com teste de v2 montado à mão).
- `sensor_reading.status_leitura` é `TEXT` no Timescale — `suspeito` insere sem
  migração de enum/CHECK.

## Guidance operacional (importante)

- **`faixa_min`/`faixa_max` = limite FÍSICO verdadeiro e FOLGADO, nunca o limite de
  conforto.** Motivo: uma leitura fora da faixa conta como "ciclo ruim"; N
  consecutivas disparam reconexão, e após o teto M o dispositivo entra em cooldown
  de K ciclos em que **não é lido** (grava `sensor_offline`, valor real perdido
  nessas janelas). Faixa apertada demais num sensor saudável = perda intermitente
  de dado real. Oscilar dentro/fora é seguro (um ciclo `ok` zera os contadores);
  só o fora-da-faixa **sustentado** cai no cooldown.
- O gate é **opt-in** por sensor (`usa_faixa`). Sensores sem faixa seguem exatamente
  como antes.
- Para o Henke (RS-WS-N01-2D), o caso que originou tudo: definir `usa_faixa=True`
  com faixa física generosa (ex. umidade 0.1–100 %RH, temperatura −40–80 °C) — aí
  o 0.0 do fd zumbi vira `suspeito` e, após N ciclos, o self-healing reabre o fd
  (o que o restart manual fazia).

## Verificação pós-deploy

- Odoo responde 200; config-publish de um hub de teste gera YAML com `faixa`/
  `reconexao` (round-trip HUB-E2E-01).
- Um arquivo v3 do hub é ingerido como `valido` (não `invalido`).
- Um sensor com `usa_faixa=True` forçado fora da faixa grava `status_leitura=suspeito`
  no Timescale; após N ciclos, log `[hub] serial reconectado`.
