# Discussão — Drivers Modbus: integração + extensibilidade via Odoo

> Documento de handoff para uma **nova sessão de brainstorm/design**. Escrito em
> 2026-07-24 após um incidente em produção. Contém tudo que a nova sessão precisa
> saber sem ter o histórico desta conversa. Ao fim, a lista de decisões a tomar.
>
> **✅ RESOLVIDA em 2026-07-25.** Ver seção "Resolução" no fim do documento.

---

## 0. TL;DR

Adicionar um 2º sensor (Henke, temperatura) derrubou o hub inteiro e congelou o
dashboard. Causa raiz: o sensor foi configurado com `driver: n4aib16` (único
valor que o hub aceita hoje), mas ele **não é** um N4AIB16 — é um **RS-WS-N01-2D**.
O driver errado leu um frame Modbus incompatível → `IndexError` → e como o loop de
leitura **não isola falha por dispositivo**, um sensor ruim matou todo o hub.

Serviço já restaurado (removido o barramento quebrado; telemetria E2E de volta). O
driver correto (`rs_ws_n01_2d.py`) **já existe e já está no GitHub**, mas o hub não
o usa por 4 razões de software. Esta discussão é sobre integrá-lo **e** criar um
mecanismo para registrar/selecionar drivers pela configuração no Odoo, à medida que
novos sensores/coletores forem adquiridos.

---

## 1. O incidente (o que aconteceu)

- O usuário adicionou um sensor "TEMPERATURA HENKE" (`sensor_id: TEMP-HENKE`) num
  2º barramento serial `/dev/ttyUSB1`, dispositivo Modbus no endereço 2, e
  **publicou** a config para o hub (fluxo Odoo → api → SFTP → Pi).
- O hub crashou no boot/reload e **ficou morto**. Dashboard parou de atualizar
  (hub morto → sem publicação MQTT → sem live).
- Traceback (real, do log do hub):
  ```
  hub/leitor.py:50  lidos = disp.driver.read_channels(maps=self._specs(disp.canais))
  hub/vendor/modbus-connector/drivers/n4aib16.py:175  col = [b[i] for b in blocks]
  IndexError: list index out of range
  ```
- Mecânica: `_read_block` do N4 só relê em `RuntimeError`; um frame **curto**
  (device não-N4 respondendo diferente) volta sem exceção → `b[i]` estoura para
  `i` além do tamanho do bloco.

## 2. Causa raiz (confirmada)

1. **Driver errado.** `TEMP-HENKE` foi declarado `driver: n4aib16`. É um
   **RS-WS-N01-2D**. O usuário usou `n4aib16` porque é o **único** valor que
   `hub/modbus_backend.py:criar_driver` aceita hoje (senão `ValueError`).
2. **Sem isolamento por dispositivo.** `hub/leitor.py:ler_todos` (linha ~50)
   itera os dispositivos e **não** captura erro por device. O crash de UM sensor
   propaga e mata o processo inteiro — inclusive os sensores que funcionavam
   (SNR-E2E-CH1, PD-HUB-CH2 no barramento ttyUSB0). **Este é o defeito mais grave**:
   um erro de configuração de um sensor não pode derrubar toda a telemetria.

## 3. Estado atual (o que já foi feito)

- **Serviço restaurado.** No Pi (`fitadigital@192.168.0.211`):
  - Backup da config: `~/sentinela-hub/config.yaml.henke-bak-20260724-152754`
  - Barramento do Henke extraído para `~/sentinela-hub/henke_bus.snippet.yaml`
    (a config do usuário NÃO foi perdida).
  - `config.yaml` agora só tem o barramento bom (`/dev/ttyUSB0`).
  - Hub religado (1 processo, verificado). Telemetria E2E de volta: último ponto
    confirmado via API 15:29:29, ~560 pontos/hora, dashboard atualizando.
- **NADA foi commitado/pushado** neste tópico ainda. O driver já estava no GitHub
  (ver §4). O incidente e o restore são operacionais, não mudaram código versionado.

## 4. Situação do driver `rs_ws_n01_2d` (verificada)

- `hub/vendor/modbus-connector` no repo `odoo_sentinela` é um **submódulo git** →
  `https://github.com/afonsorcarvalho/modbus-connector.git`, **pinado em `c5be581`**
  (commit ANTIGO, só tem `n4aib16.py`).
- O driver `drivers/rs_ws_n01_2d.py` **JÁ EXISTE e JÁ ESTÁ no GitHub** (branch
  `main`, commits `85e86dd` → `fce26de` → `a82f232` → `1301d20`), com
  `MANUAL_RS_WS_N01_2D.md`. Confirmado por `git cat-file -e origin/main:...`.
  **Não há nada a commitar/pushar do driver.**
- No Pi há um clone standalone `~/modbus-connector` (branch `main`) com:
  - 1 commit **não-pushado** `3184813` ("chore: mover watchdog…") — **não toca o
    driver**, é ops/infra. Decisão do usuário se quer pushar (não é deste tópico).
  - Uma mudança não-commitada trivial: bit de executável do `rs_ws_n01_2d.py`
    (mode 100644→100755). Ruído; sem conteúdo.
- **Especificação do device (do próprio driver, hardware-confirmada):**
  - Classe `RSWSN012D`. `NUM_REGISTERS = 2`: umidade em `0x0000`, **temperatura em
    `0x0001`** (signed). Endereço do device em `0x07D0`, baud em `0x07D1`
    (código: {2400:0, 4800:1, 9600:2}).
  - No hardware do usuário: `port=/dev/ttyUSB1, address=2, baud=9600` — **bate
    exatamente** com a config que ele publicou. A parte elétrica/Modbus está certa;
    só o software não estava pronto.

## 5. Por que o hub não roda o Henke hoje — 4 lacunas de software

1. **Submódulo velho.** `hub/vendor/modbus-connector` @ `c5be581` não contém o
   arquivo `rs_ws_n01_2d.py`. Precisa **bump** para um commit de `main` que o tenha.
2. **Whitelist do factory.** `hub/modbus_backend.py:criar_driver` só conhece
   `"n4aib16"`; qualquer outro nome → `ValueError`. Precisa registrar `rs_ws_n01_2d`.
3. **Mismatch de interface.** `hub/leitor.py:50` chama `driver.read_channels(maps=…)`.
   O driver N4 tem `read_channels`; o **RSWSN012D tem `read_measurements(…)`**, NÃO
   `read_channels`. Precisa de uma interface comum (adapter, ou método unificado, ou
   o `leitor` despachar por capacidade). **Ponto central do design.**
4. **Map placeholder.** No config do usuário o Henke veio com `map.out: [0.0, 0.0]`
   (degenerado) e `unidade: ''`. Precisa do range físico real (o RS-WS-N01-2D já
   entrega temperatura em °C direto do registrador signed ÷10 — talvez nem precise
   do `map` 4-20mA que o N4 usa; decidir).

## 6. O que o usuário pediu (o coração da discussão)

> "temos que ter um modo para colocar no odoo novos drivers para ser selecionados,
> à medida que novos sensores/coletores vão sendo adquiridos."

Hoje o `driver` é um campo de texto na config do coletor (no addon
`afr_sentinela_sensor_monitor`) que é publicado cru para o hub. Não há:
- catálogo de drivers disponíveis (o Odoo não sabe quais existem);
- validação (aceita qualquer string; o hub explode depois);
- associação driver ↔ sensor/coletor com os parâmetros que aquele driver exige
  (registrador, escala, nº de canais, unidade…).

Objetivo: um **registro de drivers** no Odoo, selecionável por dropdown na config
do coletor/dispositivo, extensível quando chega hardware novo — sem editar YAML à mão.

## 7. Decisões a tomar na nova sessão (agenda)

**A. Resiliência (prioridade, provavelmente separável e urgente)**
- `ler_todos` deve capturar erro por dispositivo, pular o device ruim, seguir com os
  demais, e sinalizar (log + status do sensor "erro"/offline no dashboard?).
- Um driver que falha ao instanciar (`criar_driver` ValueError, porta inexistente)
  deve degradar, não matar o boot. Como reportar isso ao operador/Odoo?

**B. Contrato de driver (a interface comum)**
- N4 = N canais por transação (`read_channels(maps)`), map 4-20mA. RS-WS-N01-2D = 2
  registradores (umidade+temp), valor físico direto. São modelos diferentes.
- Definir a interface que o `leitor` consome: método único? adapter por driver?
  como o driver declara seus canais/medidas e unidades nativas?

**C. Registro de drivers no Odoo**
- Modelo novo (ex. `sensor_monitor.driver`) com: código (`n4aib16`,
  `rs_ws_n01_2d`), nome, parâmetros/schema que exige, nº de canais/medidas.
- Dropdown na config do dispositivo do coletor referenciando esse modelo.
- Validação na publicação (config-publish) para o hub nunca receber um driver que
  não existe/não bate — falhar no Odoo, não no campo.
- Como um driver novo entra no catálogo? Seed/data no addon? UI? E o **código** do
  driver (que vive no submódulo `modbus-connector`) — como versão do submódulo e
  catálogo do Odoo ficam em sincronia? (o Odoo listar um driver que o hub daquela
  versão não tem = mesmo tipo de bug do incidente).

**D. Integração concreta do RS-WS-N01-2D (o caso de teste real)**
- Bump do submódulo `hub/vendor/modbus-connector` para `main` (com o driver).
- Registrar `rs_ws_n01_2d` no `criar_driver` + resolver o mismatch de interface (B).
- Config correta do Henke (reaproveitar `henke_bus.snippet.yaml`, corrigir `map`/
  `unidade`) e re-publicar; validar leitura real no ttyUSB1/endereço 2/9600.
- **REGRA DE PROJETO:** esta instância é produção persistente; testar sem derrubar
  a telemetria E2E que está no ar. Ver memória `sentinela-prod-persistente`.

## 8. Referência rápida (paths, comandos, acessos)

- Repo servidor: `/home/afonso/docker/odoo_sentinela` (branch master @ 930483c).
- Submódulo driver: `hub/vendor/modbus-connector` (@ c5be581, precisa bump).
- Factory de driver: `hub/modbus_backend.py` (`criar_driver`, linha ~18).
- Loop de leitura: `hub/leitor.py` (`ler_todos`, linha ~50 — sem isolamento).
- Addon Odoo: `addons/afr_sentinela_sensor_monitor` (config do coletor/sensor).
- Pi: `fitadigital@192.168.0.211`; hub em `~/odoo_sentinela`, config em
  `~/sentinela-hub/config.yaml`; snippet do Henke salvo em
  `~/sentinela-hub/henke_bus.snippet.yaml`; backup `config.yaml.henke-bak-*`.
- Driver standalone (fonte que o usuário edita): `~/modbus-connector` (Pi), repo
  GitHub `afonsorcarvalho/modbus-connector` branch `main`.
- Acessos das interfaces: `ACESSOS.local.md` na raiz do repo (fora do git).
- Processos vivos da produção: hub no Pi; no servidor `scripts/watcher_ingestao.py`
  + `scripts/bridge_telemetria.py`. GOTCHA watcher: precisa
  `PYTHONPATH=/home/afonso/docker/odoo_sentinela .venv/bin/python -u`.

## 9. Como começar a nova sessão

Abrir a skill de **brainstorming** (superpowers) com este documento como contexto.
Sugestão de ordem: decidir **A (resiliência)** primeiro e possivelmente
implementá-la já (é um hardening independente e urgente), depois desenhar
**B → C** (contrato de driver + registro no Odoo) e validar com **D** (o Henke real).

---

## Resolução (2026-07-25)

A agenda §7 foi executada assim:

**A — Resiliência (mergeado, `c2466eb`).** `ler_todos` e o construtor `Leitor.__init__`
isolam falha por dispositivo (`except Exception` + `_degradados`): sensor
mal-configurado vira `sensor_offline` em vez de matar o hub. Fecha o SPOF do
`IndexError` do incidente. Spec/plano em `docs/superpowers/*/2026-07-24-hub-resiliencia-leitor*`.

**B — Contrato de driver (mergeado, `e5e00b6`).** Adapter por família em
`hub/modbus_backend.py`: o `leitor` consome uma interface única (`ler(maps)`/`close()`),
sem saber de vendor. RS-WS-N01-2D cabeado; `map` opcional por canal (valor nativo
quando ausente — mata o `map:[0,0]` que zerava a leitura); submódulo bumpado.
**O Henke passou a ler em hardware real** (24,5 °C / 54 %RH → dashboard).
Spec/plano `2026-07-24-contrato-driver-adapter*`.

**C1 — Serializer profile-aware (mergeado, `27ffbbb`).** Campo `usa_map` no sensor
decide map-vs-nativo; o serializer (`api/config_publisher.py`) para de cravar
`4-20ma`/`map`; validação (`ConfigInvalida` → HTTP 422) rejeita driver desconhecido
ou map degenerado **no Odoo, não no Pi**. Round-trip de HUB-E2E-01 provou que o
config-publish gera a config correta. Spec/plano `2026-07-24-c1-serializer-profile-aware*`.

**C2 — Driver genérico register-driven (mergeado, `2f8feac`).** Driver `generico`
data-driven no submódulo (int16/uint16 v1): lê registradores por um spec do Odoo,
sem código por dispositivo. Realiza o núcleo do §6: **"adicionar sensor Modbus
simples = preencher dados no Odoo, sem escrever driver."** N4/RS/Henke de produção
inalterados (sem cutover). Spec/plano `2026-07-24-c2-driver-generico*`.

**C3 — Catálogo extensível de drivers: DECIDIDO NÃO FAZER (2026-07-25).**
Razão: o C2 já entrega o caso comum (sensor simples sem código). O C3 só trocaria a
`Selection` hardcoded de drivers por um catálogo de dados — mas um driver de
**família nova** sempre exige uma classe Python no submódulo (`criar_driver` importa
por nome; dado no Odoo não substitui a classe). Decisão do usuário: quando chegar um
equipamento que o genérico não cobre, **lançar uma nova versão do addon** (editar a
`Selection` + submódulo em lockstep) — **mais seguro**, mantém Odoo e hub sincronizados
por código, sem o risco de drift ("Odoo listar driver que o hub não tem"). Além disso,
o Plano A já torna esse mismatch **não-catastrófico** (o dispositivo degrada para
`sensor_offline`, o hub sobrevive), então a proteção elaborada (hub reportar
capacidades) defenderia um buraco já tapado.

### Dívidas/observações herdadas (não bloqueiam; backlog)

- **Precondição de publish (C1):** `usa_map` nasce `False` para todos os sensores;
  auditar `usa_map` dos sensores 4-20mA de um hub **antes** de publicá-lo (senão a
  config sai sem map). HUB-E2E-01 já corrigido.
- **`filtro`/EWMA** é parseado (`CanalConfig.filtro`) mas nunca ligado no pipeline de
  leitura (todos os drivers). Ponta solta pré-existente.
- **Validação de boot do genérico** é tudo-ou-nada por hub (um device genérico
  malformado derruba o boot inteiro, diferente da degradação por-device do `leitor`).
  Mitigada pelo gate do serializer; alinhar no futuro se incomodar.
- **Cutover do Henke para o genérico** não foi feito (fica no driver específico
  `rs_ws_n01_2d`, provado). O profile 9 já foi corrigido (registers/scale) para quando
  se quiser validar/migrar via genérico — passo pontual e confirmado à parte.
