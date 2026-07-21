#!/usr/bin/env bash
#
# testar_integracao.sh — sobe o stack Docker e roda a suíte de integração completa.
#
# Uso (a partir da raiz do repo, NO SERVIDOR DE TESTE — não no Raspberry Pi):
#   ./scripts/testar_integracao.sh                # fluxo completo
#   RESET_DB=1 ./scripts/testar_integracao.sh     # recria o volume Timescale (schema limpo)
#   SKIP_STACK=1 ./scripts/testar_integracao.sh   # stack já no ar; só deps + testes
#   SKIP_DEPS=1 ./scripts/testar_integracao.sh    # pula pip install
#
# Passos: (1) sobe db/odoo/timescaledb/sftpgo  (2) cria db Odoo 'sentinela' + addon
#         (3) venv + deps  (4) pytest contrato hub ingestao api  (5) resumo.
# Referência: docs/runbooks/integracao-servidor-teste.md
#
# ⚠ AINDA NÃO EXECUTADO DE PONTA A PONTA. Foi escrito no Raspberry (edge), sem o stack.
#   TESTE ESTE SCRIPT NUM AMBIENTE DE TESTE/STAGING ANTES DE RODAR EM PRODUÇÃO —
#   ele sobe containers, cria banco Odoo e pode remover o volume Timescale (RESET_DB=1).
#   Confirme cada passo na sua primeira execução controlada.
set -uo pipefail

# --- localizar a raiz do repo (onde está o docker-compose.yml) ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT" || exit 1

ODOO_URL="http://localhost:8189"
ODOO_DB="sentinela"
TS_DSN_HOST="localhost"; TS_DSN_PORT="5433"
COMPOSE_PROJECT="$(basename "$REPO_ROOT")"

log()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[0;32m  ✔ %s\033[0m\n' "$*"; }
warn() { printf '\033[0;33m  ! %s\033[0m\n' "$*"; }
die()  { printf '\033[0;31m  ✗ %s\033[0m\n' "$*" >&2; exit 1; }

command -v docker >/dev/null || die "docker não encontrado"
docker compose version >/dev/null 2>&1 || die "plugin 'docker compose' não encontrado"

# ---------------------------------------------------------------------------
# 1. Stack Docker
# ---------------------------------------------------------------------------
if [[ "${SKIP_STACK:-0}" != "1" ]]; then
  if [[ "${RESET_DB:-0}" == "1" ]]; then
    log "RESET_DB=1 — derrubando stack e removendo volume Timescale"
    docker compose down
    docker volume rm "${COMPOSE_PROJECT}_timescale-data" 2>/dev/null && ok "volume timescale removido" || warn "volume timescale não existia"
  fi
  log "Subindo serviços: db odoo timescaledb sftpgo"
  docker compose up -d db odoo timescaledb sftpgo || die "falha no docker compose up"
  docker compose ps
else
  warn "SKIP_STACK=1 — assumindo stack já no ar"
fi

# ---------------------------------------------------------------------------
# 2. Esperar Timescale e criar db Odoo + addon
# ---------------------------------------------------------------------------
log "Aguardando TimescaleDB ($TS_DSN_HOST:$TS_DSN_PORT)"
for i in $(seq 1 30); do
  if docker compose exec -T timescaledb pg_isready -U sentinela -d sentinela >/dev/null 2>&1; then
    ok "Timescale pronto"; break
  fi
  [[ $i -eq 30 ]] && die "Timescale não respondeu (30s). Veja 'docker compose logs timescaledb'"
  sleep 1
done

# valida schema (init.sql roda só no 1º boot do volume)
if docker compose exec -T timescaledb psql -U sentinela -d sentinela -tAc \
      "SELECT to_regclass('public.sensor_reading')" 2>/dev/null | grep -q sensor_reading; then
  ok "schema Timescale presente (sensor_reading)"
else
  die "tabela sensor_reading ausente — volume antigo sem schema. Rode: RESET_DB=1 $0"
fi

log "Aguardando Odoo ($ODOO_URL)"
for i in $(seq 1 60); do
  if curl -sf -o /dev/null "$ODOO_URL/web/database/selector" 2>/dev/null; then
    ok "Odoo respondendo"; break
  fi
  [[ $i -eq 60 ]] && die "Odoo não respondeu (60s). Veja 'docker compose logs odoo'"
  sleep 1
done

# db 'sentinela' existe? se não, cria + instala addon
db_existe() {
  curl -s "$ODOO_URL/web/database/list" -H 'Content-Type: application/json' \
    -d '{"jsonrpc":"2.0","method":"call","params":{}}' 2>/dev/null | grep -q "\"$ODOO_DB\""
}
if db_existe; then
  ok "db Odoo '$ODOO_DB' já existe"
else
  log "Criando db Odoo '$ODOO_DB' e instalando addon afr_sentinela_sensor_monitor"
  docker compose exec -T odoo odoo \
    -d "$ODOO_DB" -i afr_sentinela_sensor_monitor \
    --db_host=db --db_user=odoo --db_password=odoo \
    --stop-after-init \
    || die "falha ao criar/instalar db Odoo. Veja 'docker compose logs odoo'"
  docker compose restart odoo
  # reesperar após restart
  for i in $(seq 1 60); do
    curl -sf -o /dev/null "$ODOO_URL/web/database/selector" 2>/dev/null && break
    [[ $i -eq 60 ]] && die "Odoo não voltou após restart"
    sleep 1
  done
  db_existe && ok "db '$ODOO_DB' criado com addon" || die "db '$ODOO_DB' não apareceu após criação"
fi

# ---------------------------------------------------------------------------
# 3. Python venv + dependências
# ---------------------------------------------------------------------------
if [[ ! -d .venv ]]; then
  log "Criando .venv"
  python3 -m venv .venv || die "falha ao criar venv"
fi
# shellcheck disable=SC1091
source .venv/bin/activate || die "falha ao ativar venv"

if [[ "${SKIP_DEPS:-0}" != "1" ]]; then
  log "Instalando dependências (pip)"
  pip install -q -U pip
  for req in ingestao/requirements.txt api/requirements.txt \
             coletor_simulado/requirements.txt hub/requirements.txt; do
    [[ -f "$req" ]] && { pip install -q -r "$req" && ok "$req" || die "falha em $req"; }
  done
else
  warn "SKIP_DEPS=1 — pulando pip install"
fi

# ---------------------------------------------------------------------------
# 4. Testes — rodar da raiz para os imports (from ingestao import ...) resolverem
# ---------------------------------------------------------------------------
declare -A RESULT
run_suite() {  # $1 = rótulo, $2... = alvos pytest
  local label="$1"; shift
  log "pytest $label"
  if python -m pytest "$@" -q; then RESULT[$label]="PASS"; else RESULT[$label]="FAIL"; fi
}

run_suite "sanidade (contrato+hub)" contrato hub
run_suite "ingestao"                ingestao
run_suite "api"                     api

# ---------------------------------------------------------------------------
# 5. Resumo
# ---------------------------------------------------------------------------
log "RESUMO"
overall=0
for label in "sanidade (contrato+hub)" "ingestao" "api"; do
  if [[ "${RESULT[$label]:-FAIL}" == "PASS" ]]; then
    ok "$label"
  else
    printf '\033[0;31m  ✗ %s\033[0m\n' "$label"; overall=1
  fi
done
echo
if [[ $overall -eq 0 ]]; then
  ok "TODAS as suítes verdes — integração de servidor validada (rumo ao M1)."
else
  warn "Há falhas. Diagnóstico rápido:"
  echo "    • 'Connection refused' :5433  → Timescale fora    (docker compose logs timescaledb)"
  echo "    • erro XML-RPC / :8189        → Odoo/db 'sentinela' (docker compose logs odoo)"
  echo "    • 'registro não encontrado'   → addon sem dados de referência (recriar db: RESET_DB=1)"
  echo "    • 'No module named fastapi'   → rode sem SKIP_DEPS"
  echo "    Cole o traceback do PRIMEIRO caso que falhou, não só o resumo."
fi
exit $overall
