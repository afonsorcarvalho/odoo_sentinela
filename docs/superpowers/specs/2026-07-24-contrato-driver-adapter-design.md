# Design — Contrato de driver comum no Hub (Plano B)

> Fatia da discussão `docs/discussao-drivers-extensibilidade.md` (§B + §5.1-5.3).
> Faz o `leitor` consumir dois drivers Modbus de famílias diferentes (N4AIB16 e
> RS-WS-N01-2D) por uma interface única, sem saber de vendor. Cabeia o driver RS
> **já existente** — NÃO constrói o driver genérico register-driven (isso é o Plano C).

## Contexto e problema

Hoje `hub/leitor.py` chama `disp.driver.read_channels(maps=…)` direto e espera
entries com a chave `channel`. Isso casa só com o N4AIB16. O RS-WS-N01-2D expõe
`read_measurements(…)` e devolve entries com `name`+`register` (sem `channel`).
Três diferenças reais entre as famílias:

1. **Nome do método:** `read_channels` (N4) vs `read_measurements` (RS).
2. **Chave de identidade:** N4 entry tem `channel` (int 1..16); RS entry tem
   `name`+`register`, sem `channel`. `leitor` faz `por_canal = {e["channel"]: e}`.
3. **Map vs valor nativo (o que decide se o Henke lê certo):** N4 entrega
   mA/tensão e o map 4-20mA→eng é **obrigatório**. RS entrega °C/%RH **direto** do
   registrador (o ÷10 e o signed já estão dentro do driver — `HUM_SCALE`,
   `TEMP_SCALE`, `to_signed16`); o map é **ausente**. Hoje o `leitor._specs` monta
   uma `MapSpec` pra **todo** canal e a config força `map:{in,out}` — o `map:[0,0]`
   degenerado do incidente mapeia **toda** leitura RS para **0**.

## Objetivo

`leitor` consome uma interface uniforme; a config do RS não precisa (e não deve)
declarar `map`; o valor nativo do driver chega intacto. Provado com um
`config.yaml` escrito à mão e o driver RS existente — zero Odoo.

## Arquitetura — adapter no seam do vendor

`hub/modbus_backend.py` já é, por docstring, o ponto que confina o conhecimento do
vendor. O contrato vive lá.

### Componente 1 — `criar_driver` devolve um adapter por família

`criar_driver(driver_nome, …)` passa a devolver um **adapter fino** que embrulha o
driver do vendor e expõe a interface uniforme:

- `driver_nome == "n4aib16"` → `AdaptadorN4(N4AIB16(...))`
- `driver_nome == "rs_ws_n01_2d"` → `AdaptadorRS(RSWSN012D(...))` **(novo ramo)**
- desconhecido → `ValueError` (como hoje)

A construção do driver do vendor (que abre a porta serial) fica dentro de
`criar_driver`, como já é hoje para o N4.

### Componente 2 — interface uniforme do adapter

Todo adapter expõe exatamente:

- `ler(maps)` → `list[dict]`, cada entry com **garantidamente** as chaves
  `channel` (int, 1-based, batendo com `CanalConfig.ch`), `value` e `unit`.
- `close()` → fecha o driver do vendor (o `leitor.fechar` chama isto).

Comportamento por família:

- **`AdaptadorN4.ler(maps)`:** delega a `read_channels(maps=maps)`; as entries já
  têm `channel` → repassa. `close()` → `driver.close()`.
- **`AdaptadorRS.ler(maps)`:** delega a `read_measurements(maps=maps)`; as entries
  têm `name`+`register` mas não `channel` → o adapter injeta `channel = i+1` na
  ordem de retorno (1=umidade, 2=temperatura, coincidindo com a convenção 1-based
  de `maps` que o próprio driver usa). `close()` → `driver.close()`.

O `leitor` deixa de chamar `read_channels` e passa a chamar `disp.driver.ler(maps=…)`
e `disp.driver.close()` — `disp.driver` agora é o adapter.

### Componente 3 — map opcional por canal (correção de dados)

- `CanalConfig.map_in` / `map_out` passam a ter default `None` (canal pode não ter
  map).
- `config._canal`: `mapa = bruto.get("map")`; se presente, parseia `in`/`out` como
  hoje; se ausente, `map_in = map_out = None`.
- `leitor._specs(canais)`: monta `MapSpec` **apenas** para canais com `map_in` e
  `map_out` não-None. Canais sem map ficam **fora** da lista `maps` → no driver,
  `channel_maps.get(ch)` devolve `None` → o `value` **nativo** é preservado.

Assim um canal RS sem map recebe °C/%RH direto; um canal N4 com map recebe eng. O
`map:[0,0]` some do caminho (config do RS nem declara `map`).

### Componente 4 — bump do submódulo

`hub/vendor/modbus-connector` sai de `c5be581` (só tem `n4aib16.py`) para o SHA
**`fc70ffb`** (tip do `main`, contém `drivers/rs_ws_n01_2d.py` + `MANUAL_…`). Pin de
SHA, não branch.

**Verificado:** o diff `c5be581..fc70ffb` **não toca** `drivers/n4aib16.py` nem
`common/` — só adiciona o driver RS, docs, e ops/watchdog. O bump é seguro para o
N4 em produção; sem mudança de comportamento, sem regressão de leitura dos sensores
que já estão no ar.

## Não faz parte do B (vai para C/D)

- Driver genérico register-driven (fork "a"). B usa o `rs_ws_n01_2d.py` existente
  como code driver. O genérico nasce em C, com o register spec vindo do Odoo — e sua
  validação em hardware será ler o **mesmo** Henke pelo genérico e conferir contra o
  driver específico (cross-check).
- `api/config_publisher.py` profile-aware (hoje crava `protocolo_origem:'4-20ma'` e
  `map`) — Plano C.
- Catálogo de drivers no Odoo, validação na publicação — Plano C.
- Deploy no Pi, config real do Henke, leitura em hardware — Plano D.

## Estratégia de testes

Todos sem hardware/serial real (padrão atual: mocks em `hub/tests/`).

1. **Adapter RS normaliza entries** (unit, com um driver-fake do vendor que devolve
   entries no formato `read_measurements` — `name`/`register`/`value`/`unit`, sem
   `channel`): `AdaptadorRS.ler(maps)` devolve entries com `channel = 1,2` na ordem,
   `value`/`unit` preservados.
2. **Adapter N4 repassa** (unit, driver-fake com entries já contendo `channel`):
   `AdaptadorN4.ler(maps)` mantém `channel`/`value`/`unit`.
3. **`criar_driver` despacha o RS** para `AdaptadorRS` sem abrir porta serial —
   mockar/patch o construtor `RSWSN012D` (evita I/O de `/dev/ttyUSB*`); asserir o
   tipo do adapter retornado. Idem regressão: `n4aib16` → `AdaptadorN4`; desconhecido
   → `ValueError`.
4. **Map opcional no `leitor`** (via `_BackendFake`/`_DriverFake`, padrão existente):
   config com um canal **sem** `map` → `_specs` não inclui `MapSpec` para ele → o
   driver-fake recebe `maps` sem esse canal e o valor **nativo** chega em
   `ler_todos` (não é zerado). Um canal **com** `map` no mesmo config continua
   aplicando a `MapSpec`.
5. **`config._canal` aceita map ausente:** YAML sem `map` → `CanalConfig` com
   `map_in=map_out=None`; YAML com `map` → tuplas como hoje. Regressão dos testes de
   config existentes.
6. **Regressão do leitor:** toda a suíte `hub/tests/test_leitor.py` (inclui os testes
   de resiliência do Plano A) continua verde após a troca `read_channels`→`ler`.

Rodar: `cd /home/afonso/docker/odoo_sentinela && python -m pytest hub -q`.

## Arquivos

- `hub/vendor/modbus-connector` — bump para `fc70ffb` (ponteiro do submódulo).
- `hub/modbus_backend.py` — `criar_driver` + `AdaptadorN4` + `AdaptadorRS`.
- `hub/leitor.py` — `read_channels`→`ler`; `_specs` filtra canais sem map.
- `hub/config.py` — `CanalConfig` map default None; `_canal` map opcional.
- `hub/tests/test_leitor.py`, `hub/tests/test_config.py`, e um novo
  `hub/tests/test_modbus_backend.py` (adapter + dispatch) — testes acima.

Nenhuma mudança no addon Odoo, serializer ou frontend nesta fatia.
