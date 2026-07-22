# Runbook — Prova E2E do laço de config em hardware (Hub real + N4AIB16)

Fecha o Plano B da Fase 5: o Odoo publica config → o Hub (Raspberry Pi) baixa por
SFTP, aplica, recarrega o leitor, reporta → drift fecha → o N4AIB16 real é lido com
a config publicada → valor no dashboard.

Hardware confirmado (lido ao vivo): N4AIB16 addr 1 em `/dev/ttyUSB0` do Pi —
**CH1 = 18,4 mA**, CH2 = 11,46 mA (transmissores 4-20mA reais). O E2E mapeia **CH1**.

Pi: `fitadigital@192.168.0.211`, repo `~/odoo_sentinela` (deployado em `master`),
venv `~/odoo_sentinela/.venv`. Também na VPN (`10.8.0.19` → servidor `10.8.0.1`).

---

## ⚠️ Pré-requisito de rede (BLOQUEIA o E2E a partir do ambiente de dev WSL2)

O Hub precisa alcançar **MQTT (1883)** e **SFTP (2022)** do servidor. O stack Fase 5
(Mosquitto, SFTPGo com a conta de config, Odoo com os campos §7, a API com a rota de
publicação) foi construído e validado num ambiente **WSL2**, cujo IP (`172.24.97.65`)
está **atrás do NAT do Windows** — o Pi **não alcança** por LAN. Verificado:
- Pi → `192.168.0.1:1883` (roteador): FAIL.
- Pi → `10.8.0.1:1883` (VPS de produção via VPN): OK (mas é outro Mosquitto, sem o
  nosso stack Fase 5).
- Esta máquina não está na VPN (só IPs `172.x`).

**Para rodar o E2E, escolha um caminho:**

- **(A) Port-forward do Windows → WSL2** (mantém o stack de dev). Num PowerShell
  **como Administrador** no Windows:
  ```powershell
  netsh interface portproxy add v4tov4 listenport=1883 listenaddress=0.0.0.0 connectport=1883 connectaddress=172.24.97.65
  netsh interface portproxy add v4tov4 listenport=2022 listenaddress=0.0.0.0 connectport=2022 connectaddress=172.24.97.65
  # liberar no firewall se preciso; descobrir o IP LAN do Windows: ipconfig
  ```
  O `identity.yaml` do Pi então aponta `mqtt.host`/`sftp.host` = IP LAN do Windows.
  (Rechecar o IP do WSL2 após reboot: `hostname -I` no WSL2 — muda entre boots, salvo
  modo *mirrored* do WSL.)

- **(B) Rodar o E2E contra o VPS** (`10.8.0.1`, que o Pi já alcança e onde roda o
  docker-compose de produção — ver `transporte-sftp-servidor.md`). Requer: `git pull`
  do `master` no VPS, `docker compose up -d mosquitto` + rebuild/refresh da API e do
  addon (campos §7), e criar a conta SFTP de config no SFTPGo do VPS. O `identity.yaml`
  aponta `10.8.0.1`.

Os passos abaixo são **independentes do caminho de rede** — só mudam os hosts no
`identity.yaml`.

---

## 1. Deploy do Hub no Pi  ✅ (feito nesta sessão)
```bash
ssh fitadigital@192.168.0.211
cd ~/odoo_sentinela
git fetch origin && git checkout -B master origin/master
git submodule update --init --recursive
```
O `hub/` novo (`agente_config.py`, `identidade_config.py`, `enviador_sftp.baixar`,
reload no `main.py`) fica presente. O fix `expanduser` já está em master (cherry-pick).

## 2. Provisionar no Odoo (servidor)
Criar (idempotente): site + hub `HUB-E2E-01` (`hub_code=HUB-E2E-01`) + `rs485.bus`
(`serial_port=/dev/ttyUSB0`, `baud_rate=9600`, `parity=none`, `stop_bits=1`,
`data_bits=8`) + `modbus.profile` (`driver=n4aib16`) + `modbus.profile.register`
(`measurement_type=temperatura`, `function_code=04_input`, `register_address=0`,
`data_type=int16`) + `modbus.device` (`slave_address=1`, profile) + `sensor`
`SNR-E2E-CH1` (coletor/área da base demo, `measurement_type=temperatura`,
`protocolo_origem=rs485`, `modbus_register_id`=register, `modbus_channel=1`,
`ma_in_min=4`, `ma_in_max=20`, `eng_out_min=-50`, `eng_out_max=150`,
`filtro_tipo=none`). Script: `scripts/provisionar_e2e_hub.py` (a criar) ou via UI Odoo.

## 3. Conta SFTP do Hub (SFTPGo)
Criar no SFTPGo uma conta para o Pi (pubkey SSH do Hub — `~/sentinela-hub/chaves/ssh_hub.pub`)
com **leitura em `/config/HUB-E2E-01`** e **escrita em `/uploads`**. (Na sessão de dev,
a conta de serviço `sentinela-config-svc` já cobre `/config`; para o Hub, registrar a
pubkey do Pi.)

## 4. `identity.yaml` no Pi
`~/sentinela-hub/identity.yaml` (só identidade/conectividade — o operacional vem do
servidor):
```yaml
hub_id: HUB-0001A2F3
hub_code: HUB-E2E-01          # DEVE == hub.hub_code do Odoo (senão tópicos não batem)
coletor_id: COL-RS485-BUS0
firmware_version: 0.1.0
timezone_offset: "-03:00"
caminho_chave: ~/sentinela-hub/chaves/coletor.pem
caminho_dados: ~/sentinela-hub/dados
mqtt: { host: <IP-do-servidor>, port: 1883 }
sftp: { host: <IP-do-servidor>, port: 2022, username: <conta-hub>,
        ssh_key_path: ~/sentinela-hub/chaves/ssh_hub, remote_dir: /uploads }
```
`<IP-do-servidor>` = IP LAN do Windows (caminho A) ou `10.8.0.1` (caminho B).

## 5. Publicar + rodar
- Odoo: botão **"Publicar configuração"** no hub `HUB-E2E-01`. Anotar a versão desejada N.
- Pi: `python -m hub.main --config ~/sentinela-hub/config.yaml --identity ~/sentinela-hub/identity.yaml`
  (o `config.yaml` é **gerado** pelo agente ao receber o 1º notify; até lá o leitor não
  lê — comportamento de boot-sem-config).

## 6. Verificar (critério de sucesso)
- **Odoo:** drift fecha (`config_version_desejada == config_version_aplicada`), via
  `applied` e/ou heartbeat retido.
- **Pi:** `~/sentinela-hub/config.yaml` efetivo escrito com a versão N;
  `~/sentinela-hub/dados/estado_config.json` = N.
- **Timescale/Odoo:** leitura nova de `SNR-E2E-CH1` (valor de engenharia derivado de
  ~18,4mA pela `map` [4,20]→[-50,150] ≈ **133,75**).
- **Dashboard:** valor real de CH1 ao vivo.
- **Sucesso = drift fechado E valor real de CH1 no dashboard.**

---

## Execução (2026-07-22) — ✅ SUCESSO

Rede destravada pelo caminho (A): `netsh portproxy` no Windows (`192.168.0.204`) →
WSL2 (`172.24.97.65`) para 1883/2022. Pi confirmou alcance às duas portas.

- ✅ **Deploy:** Pi em `master` (`da8a838`), submodule ok, `hub/` novo. Fix `expanduser`
  em master.
- ✅ **Provisionamento:** `scripts/provisionar_e2e_hub.py` → hub `HUB-E2E-01` + bus
  `/dev/ttyUSB0` + device N4AIB16 addr 1 + sensor `SNR-E2E-CH1` (ch1, map [4,20]→[-50,150]).
- ✅ **Conta SFTP do Pi:** pubkey `ssh_hub` do Pi adicionada à conta `sentinela-config-svc`
  (home compartilhado, lê `/config`).
- ✅ **`identity.yaml`** no Pi (`hub_code=HUB-E2E-01`, hosts `192.168.0.204`).
- ✅ **Publicar:** `POST /internal/hub/HUB-E2E-01/publicar-config` → `config-v1.yaml` no
  SFTP + notify retido v1.
- ✅ **Rodar:** `python -m hub.main --config config.yaml --identity identity.yaml` no Pi.
  (Gap descoberto: `main()` faz `carregar_config` no boot antes do 1º notify → precisou de
  um `config.yaml` bootstrap com `barramentos: []`; o agente sobrescreveu no 1º notify.
  Follow-up: `main()` deveria bootstrapar da identidade quando `config.yaml` ausente.)
- ✅ **Laço fechou:** Odoo `HUB-E2E-01` → `config_version_desejada=1`,
  `config_version_aplicada=1`, `config_em_drift=False`, `reportada_em=19:20:20`.
- ✅ **Leitura real do CH1:** `config.yaml` efetivo com o barramento real; hub lê o
  N4AIB16 (`/dev/ttyUSB0` CH1 ≈ 18,4 mA) → `SNR-E2E-CH1 | AREA-EXPURGO | temperatura |
  130.6 | 4-20ma | ok | <hash>` — valor de engenharia via `map` [4,20]→[-50,150]
  (18,4mA→130), assinado, 1 leitura a cada 5 s.

**Critério de sucesso atingido: drift fechado E o N4AIB16 real lido com a config
publicada pelo Odoo.** Grau M2 (hardware no laço).

### Não exercitado (stretch, fora do core do Plano B)
- **Leitura → dashboard:** o arquivo diário assinado é gravado localmente no Pi, mas o
  envio SFTP→ingestão→Timescale→dashboard não foi ligado (requer o Event Manager do
  SFTPGo + registro da pubkey EC do coletor em `ingestao/coletores_conhecidos.json` —
  ver `transporte-sftp-servidor.md`). O valor real do CH1 está provado no arquivo
  assinado do Hub; falta só o transporte já especificado na fatia de transporte.

## Referências
- Spec: `docs/superpowers/specs/2026-07-22-fase5-config-loop-hub-planoB-design.md`
- Plano: `docs/superpowers/plans/2026-07-22-fase5-config-loop-hub-planoB.md`
- Transporte SFTP (VPS): `docs/runbooks/transporte-sftp-servidor.md`
