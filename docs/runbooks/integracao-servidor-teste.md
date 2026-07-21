# Runbook — Rodar a suíte de integração no servidor de teste

> **Para o Claude do servidor local de teste.** Este documento é auto-contido: siga na
> ordem. O objetivo é subir o stack Docker e ter **verde real** nos testes de integração
> (`ingestao/` e `api/`), que dependem de TimescaleDB e Odoo vivos — algo que **não** pode
> ser feito no Raspberry Pi (edge), só aqui no servidor.

## Contexto rápido (o que já está provado e o que falta)

| Camada | Testes | Onde roda | Estado |
|--------|--------|-----------|--------|
| `contrato/` (fronteiras/formatos) | 9 | qualquer lugar (puro) | ✅ verde |
| `hub/` (leitor RS-485 → arquivo assinado + MQTT + SFTP) | 76 | qualquer lugar (puro) | ✅ verde |
| `ingestao/` (SFTP→valida→Timescale→Odoo→alarmes) | ~22 | **precisa Timescale + Odoo** | ⏳ rodar aqui |
| `api/` (auth, histórico, live/SSE, alarmes, config) | ~13 arquivos | parte pura, parte **precisa Timescale/Odoo** | ⏳ rodar aqui |

**Objetivo deste runbook:** fechar a validação de integração servidor — o último passo
prático rumo ao **Marco M1** (piloto ponta a ponta no servidor, sem hardware).

---

## Atalho — script automatizado

> ⚠️ **O script ainda não foi executado de ponta a ponta** (foi escrito no Raspberry, sem o
> stack). **Teste-o num ambiente de teste/staging antes de rodar em produção** — ele sobe
> containers, cria o banco Odoo e, com `RESET_DB=1`, remove o volume Timescale. Valide cada
> passo na primeira execução controlada.

Os passos 1–4 estão encadeados em `scripts/testar_integracao.sh` (idempotente):
```bash
./scripts/testar_integracao.sh                # fluxo completo (stack + db + deps + testes)
RESET_DB=1 ./scripts/testar_integracao.sh     # recria o volume Timescale (schema limpo)
SKIP_STACK=1 ./scripts/testar_integracao.sh   # stack já no ar; só deps + testes
```
Ele sobe o stack, espera Timescale/Odoo ficarem prontos, cria o db `sentinela` com o addon,
instala as deps no `.venv` e roda `pytest contrato hub ingestao api`, imprimindo um resumo
com diagnóstico por tipo de falha. Os passos manuais abaixo servem de referência/depuração.

## 0. Pré-requisitos
- Docker + Docker Compose plugin.
- Python 3.11+ com `venv`.
- Portas livres no host: **5433** (Timescale), **8189** (Odoo), **2022/8190** (SFTPGo), 5432 interno.
- Repositório `odoo_sentinela` clonado/atualizado neste servidor.

## 1. Subir o stack Docker
Na raiz do repo:
```bash
docker compose up -d db odoo timescaledb sftpgo
docker compose ps        # confirmar todos "running"/"healthy"
```
- **timescaledb**: o `timescale/init.sql` roda **automaticamente no primeiro boot** e cria
  `sensor_reading` (hypertable), índices, compressão e os continuous aggregates. Se o volume
  `timescale-data` já existir de antes, o init **não** roda de novo — nesse caso, para começar
  limpo: `docker compose down && docker volume rm odoo_sentinela_timescale-data && docker compose up -d timescaledb`.
- Verificar Timescale:
  ```bash
  docker compose exec timescaledb psql -U sentinela -d sentinela -c "\dt"
  # deve listar sensor_reading
  ```

## 2. Criar o banco Odoo `sentinela` com o addon instalado
Os testes de `ingestao/` conectam via XML-RPC em `http://localhost:8189`, db **`sentinela`**,
login **`admin`** / senha **`admin`**. É preciso criar esse db com o módulo instalado.

Via CLI (idempotente, recomendado):
```bash
docker compose exec odoo odoo \
  -d sentinela \
  -i afr_sentinela_sensor_monitor \
  --db_host=db --db_user=odoo --db_password=odoo \
  --stop-after-init
```
Isso cria o db `sentinela`, instala o addon e cria o usuário `admin` com senha `admin`
(padrão do Odoo em init). Depois garanta que o servidor está servindo:
```bash
docker compose restart odoo
```
Verificar login/addon:
```bash
curl -s http://localhost:8189/web/database/list -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"call","params":{}}' | head
# 'sentinela' deve aparecer na lista
```
> Se preferir a UI: `http://localhost:8189` → Create Database → master pwd `admin_dev_only`
> (de `conf/odoo.conf`), Database name `sentinela`, email/login `admin`, senha `admin` →
> depois Apps → instalar **afr_sentinela_sensor_monitor** (remover filtro "Apps").
>
> Os **dados de referência** (categorias de área tipo `EXPURGO`, `measurement.type` como
> `temperatura`/`pressao_diferencial`, RDC 15) vêm nos data files do addon — o
> `provisionar_odoo_sim` depende deles (`_buscar_id(...'EXPURGO'...)`). Se um teste falhar
> com "registro não encontrado em sensor_monitor.area.category", o addon não instalou os
> dados de referência: reinstale com `-i` (não `-u`) num db limpo.

## 3. Ambiente Python + dependências
```bash
python -m venv .venv && source .venv/bin/activate
pip install -U pip
pip install -r contrato/requirements.txt 2>/dev/null || true
pip install -r ingestao/requirements.txt
pip install -r api/requirements.txt        # <- traz fastapi, faltava no Pi
pip install -r coletor_simulado/requirements.txt
pip install -r hub/requirements.txt
```
Os testes importam pacotes a partir da **raiz do repo** (`from ingestao import ...`,
`from coletor_simulado import ...`), então **rode o pytest a partir da raiz** para o
`sys.path` incluir o projeto.

## 4. Rodar os testes

### 4a. Sanidade (deve passar independente do stack)
```bash
python -m pytest contrato hub -q         # esperado: 9 + 76 verdes
```

### 4b. Ingestão (precisa Timescale + Odoo dos passos 1–2)
```bash
python -m pytest ingestao -q
```
- Os testes se **auto-provisionam** no Odoo via `provisionar_odoo_sim.provisionar()`
  (cria partner/site/hub/área/coletor/sensores — idempotente) e limpam o Timescale por
  `site_id` antes de cada caso. Não precisa seed manual.
- Cobre: arquivo válido → grava ledger + leituras; arquivo corrompido → ledger inválido;
  coletor desconhecido; arquivo de alarme com par entrada/saída → cria e resolve
  `alarm.event`; backfill + refresh de agregados.

### 4c. API (parte pura + parte que toca Timescale/Odoo)
```bash
python -m pytest api -q
```
- `test_historico.py` e `test_timescale.py` inserem/leem no Timescale (DSN 5433).
- `test_live_*` sobem listener/trigger contra o broker/Timescale.
- `test_auth*`, `test_meta`, `test_main` usam `TestClient` (mais leves), mas o app importa
  as camadas — mantenha o stack de pé para evitar erro de conexão no import.

### 4d. Tudo de uma vez (com stack no ar)
```bash
python -m pytest contrato hub ingestao api -q
```

## 5. Critério de sucesso (o que reportar de volta)
- `contrato` **9/9** e `hub` **76/76** verdes.
- `ingestao` **todos verdes** — nenhum `psycopg2.OperationalError` (Timescale) nem erro
  XML-RPC (Odoo). Se aparecer `Connection refused` em 5433 → Timescale não subiu; em 8189
  → Odoo não subiu ou db `sentinela` não existe.
- `api` **todos verdes**.
- Anote a contagem final (`N passed`) e, se houver falha, cole o traceback do **primeiro**
  caso — não o resumo. A causa quase sempre é: (a) stack não está `running`, (b) db Odoo
  `sentinela` sem o addon/dados de referência, ou (c) volume Timescale antigo sem o schema.

## 6. (Opcional) Demo ao vivo ponta a ponta — prova do M1
Depois do verde, dá pra encenar o fluxo real que o frontend consome:
```bash
# provisiona cenário no Odoo (idempotente)
python -m ingestao.provisionar_odoo_sim
# gera leituras contínuas direto no Timescale (loop) para o dashboard mostrar "ao vivo"
python -m ingestao.simulador_continuo --site-id SITE-SIM-0001 --coletor-id COL-SIM-0001
# backfill de histórico + refresh dos agregados
python -m ingestao.backfill_demo
# sobe a API de leitura/tempo real
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
```
Frontend: ver `frontend/README.md` (Vite dev server; consome as APIs da porta 8000).
Isso fecha o M1: simulador → (arquivo assinado/ingestão) → Timescale/Odoo → API → dashboard.

---

### Referências no repo
- `roadmap_implementacao.md` — fases e marcos (M1 é a meta desta rodada).
- `docs/runbooks/transporte-sftp-servidor.md` — provisionamento do Hub real via SFTP (T1).
- `docker-compose.yml` — serviços e portas.
- `timescale/init.sql` — schema/hypertable/agregados.
- `ingestao/provisionar_odoo_sim.py` — cenário simulado; `simulador_continuo.py`,
  `backfill_demo.py`, `seed_alarmes_demo.py` — dados de demo.
