#!/usr/bin/env bash
# ler_n4.sh — leitura de teste do coletor N4AIB16 (Modbus RTU sobre RS-485).
#
# Encapsula porta/baud/endereço, o venv e o caminho do driver, para que a
# leitura seja sempre um comando só. Chame direto no terminal ou pela skill
# "leitura-n4".
#
# Uso:
#   scripts/ler_n4.sh                    # leitura única, addr 1, /dev/ttyUSB0
#   scripts/ler_n4.sh -a 2               # outro endereço no barramento
#   scripts/ler_n4.sh watch              # leitura contínua (Ctrl+C p/ parar)
#   scripts/ler_n4.sh stats              # média/desvio de 20 amostras
#   scripts/ler_n4.sh -a 3 stats -n 50   # 50 amostras no addr 3
#   scripts/ler_n4.sh map 1:4:20:-50:150:C   # CH1 4-20mA -> -50..150 °C
#   scripts/ler_n4.sh -p /dev/serial/by-id/usb-1a86_USB2.0-Ser_-if00-port0
#
# Modos (1º argumento posicional, opcional): read (padrão) | watch | stats | map
# Flags: -p PORTA  -a ENDERECO  -b BAUD  -n AMOSTRAS  --json
# Tudo depois de `--` é repassado cru ao driver n4aib16.py.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRIVER="$RAIZ/hub/vendor/modbus-connector/drivers/n4aib16.py"
PY="$RAIZ/.venv/bin/python"
[[ -x "$PY" ]] || PY="python3"

PORTA="${N4_PORTA:-/dev/ttyUSB0}"
ENDERECO="${N4_ENDERECO:-1}"
BAUD="${N4_BAUD:-9600}"
AMOSTRAS=20
JSON=""
MODO="read"

# 1º posicional = modo, se for um dos modos conhecidos.
if [[ $# -gt 0 ]]; then
  case "$1" in
    read|watch|stats|map) MODO="$1"; shift ;;
  esac
fi

# Coleta flags até `--`; o resto é map-spec (modo map) ou passthrough.
EXTRA=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--port)    PORTA="$2"; shift 2 ;;
    -a|--address) ENDERECO="$2"; shift 2 ;;
    -b|--baud)    BAUD="$2"; shift 2 ;;
    -n|--samples) AMOSTRAS="$2"; shift 2 ;;
    --json)       JSON="--json"; shift ;;
    --)           shift; EXTRA+=("$@"); break ;;
    *)            EXTRA+=("$1"); shift ;;
  esac
done

if [[ ! -e "$PORTA" ]]; then
  echo "erro: porta $PORTA não existe." >&2
  echo "portas disponíveis:" >&2
  DISP="$(ls -1 /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || true)"
  if [[ -n "$DISP" ]]; then echo "$DISP" | sed 's/^/  /' >&2; else echo "  (nenhuma)" >&2; fi
  ls -1 /dev/serial/by-id/ 2>/dev/null | sed 's|^|  by-id: |' >&2 || true
  exit 1
fi
if [[ ! -r "$PORTA" || ! -w "$PORTA" ]]; then
  echo "aviso: sem permissão de leitura/escrita em $PORTA." >&2
  echo "       o usuário precisa estar no grupo dialout: sudo usermod -aG dialout \$USER (relogar)." >&2
fi

BASE=(-p "$PORTA" -a "$ENDERECO" -b "$BAUD")

case "$MODO" in
  read)
    exec "$PY" "$DRIVER" "${BASE[@]}" ${JSON:+$JSON} "${EXTRA[@]}"
    ;;
  watch)
    exec "$PY" "$DRIVER" "${BASE[@]}" --watch ${JSON:+$JSON} "${EXTRA[@]}"
    ;;
  stats)
    exec "$PY" "$DRIVER" "${BASE[@]}" --samples "$AMOSTRAS" --stats ${JSON:+$JSON} "${EXTRA[@]}"
    ;;
  map)
    if [[ ${#EXTRA[@]} -eq 0 ]]; then
      echo "erro: modo map exige uma spec CANAIS:IN_MIN:IN_MAX:OUT_MIN:OUT_MAX[:UNIDADE]" >&2
      echo "ex.: scripts/ler_n4.sh map 1:4:20:-50:150:C" >&2
      exit 1
    fi
    MAPS=()
    for m in "${EXTRA[@]}"; do MAPS+=(--map "$m"); done
    exec "$PY" "$DRIVER" "${BASE[@]}" ${JSON:+$JSON} "${MAPS[@]}"
    ;;
esac
