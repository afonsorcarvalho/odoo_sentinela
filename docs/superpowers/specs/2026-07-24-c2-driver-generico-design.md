# Design — Driver genérico register-driven (Plano C2)

> Segunda fatia do Plano C da discussão `docs/discussao-drivers-extensibilidade.md`.
> Constrói um driver Modbus **data-driven**: lê registradores arbitrários a partir
> de um spec (endereço, função, tipo, escala, offset) vindo do Odoo, em vez de um
> driver de código por família. Realiza o núcleo do fork (a): "adicionar sensor
> simples = preencher dados no Odoo, sem escrever código". Depende de C1 (serializer
> profile-aware). NÃO constrói o catálogo extensível de drivers (C3).

## Contexto

N4AIB16 e RS-WS-N01-2D são drivers de **código** no submódulo `modbus-connector`,
com o layout de registradores hardcoded. Adicionar um sensor simples novo hoje exige
escrever um driver. O modelo Odoo `sensor_monitor.modbus.profile.register` já
descreve registradores por dados (`register_address`, `function_code`,
`register_count`, `data_type`, `scale`, `offset`, `unidade`), mas esse spec **não é
serializado** para o hub — só serve para linkar sensores (§C1).

O driver genérico consome esse spec e lê qualquer dispositivo Modbus "simples"
(registradores → valor físico via escala/offset), sem código novo por dispositivo.

## Escopo v1 (decisão do usuário)

- `data_type`: **`int16` (signed) e `uint16` (unsigned)** — 1 registrador cada. O
  decode é **estruturado** para `int32/uint32/float32` + `byte_order` (2
  registradores) serem um acréscimo delimitado depois. Fora do C2.
- Um `probe` por registrador (o `function_code` varia por registrador — ex.: perfil
  N4 tem CH1 input / CH2 holding). Sem otimização de block-read: o genérico é para
  sensores de baixa taxa (≥1min), eficiência não é o gargalo. Simplificação
  deliberada da v1.

## Bloco 1 — Driver genérico no submódulo (`drivers/generico.py`)

Novo driver no repo `modbus-connector`. Data-driven: recebe no construtor a lista de
registradores do dispositivo. Por registrador, em `read_measurements(maps=None)`
(mesma interface dos outros drivers, para reuso do adapter):

1. `probe(self._ser, self.address, funcao, address, count)` → words crus (int
   16-bit big-endian). `funcao` é int (3=holding, 4=input).
2. **Decode `data_type`** (código novo, isolado numa função pura testável):
   - `int16` → `to_signed16(word)` (raw≥0x8000 → raw−0x10000).
   - `uint16` → `word` (sem conversão).
   - `count` deve ser 1 na v1; `int32/float32` (count 2) → `NotImplementedError`
     claro (delimita o acréscimo futuro).
3. `valor_físico = raw_decodificado * scale + offset`.
4. Pipeline de amostras (reuso de `common/filters`: reduce/EWMA/reject) igual N4/RS.
5. Se `maps` tiver spec para o canal, aplica `spec.apply` por cima (igual N4/RS) —
   permite um sensor 4-20mA lido pelo genérico ter map; nativo (Henke) não tem.
6. Retorna entries `{channel, value, unit, ...}` na forma do adapter (`channel` =
   índice 1-based ou o `ch` do registrador — ver Bloco 2).

Reusa `modbus_scanner.probe/open_serial`, `common/filters`, `common/scaling`.
Testável 100% no submódulo com `probe` mockado (padrão `unittest`+`mock` já usado em
`tests/test_rs_ws_n01_2d.py`). Nome do driver: **`generico`**.

**Construtor:** `Generico(port, baud, address, parity, stopbits, registros)` onde
`registros` é a lista `[{ch, address, function, data_type, scale, offset, count}]`.

## Bloco 2 — Encanamento (config → leitor → driver)

- `hub/modbus_backend.py:criar_driver` ganha param aditivo:
  `criar_driver(driver_nome, porta, baud, paridade, stopbits, endereco, registros=None)`.
  Ramo `generico` → `AdaptadorGenerico(Generico(..., registros=registros))`. N4/RS
  ignoram `registros` (default None), inalterados.
- `AdaptadorGenerico` expõe `ler(maps)`/`close()` (como os outros). O `Generico`
  já produz entries com `channel` (o `ch` de cada registrador), então o adapter
  repassa (não precisa injetar como o RS).
- `hub/leitor.py:__init__` passa `disp.registros` (novo) a `criar_driver` — só
  presente para dispositivos genéricos; None para N4/RS. `_DispositivoLigado` e o
  loop de leitura inalterados no resto.

## Bloco 3 — Schema da config no hub (`hub/config.py`)

- `CanalConfig` ganha campo opcional `registro: dict = None` com
  `{address, function, data_type, scale, offset, count}`.
- `DispositivoConfig` continua com `canais`; `criar_driver` recebe a lista de
  `registros` derivada dos canais que têm `registro` (o backend monta a lista
  `[{ch, **canal.registro}]`). Canal sem `registro` (N4/RS) → dispositivo não é
  genérico.
- Validação de entrada: se `driver == 'generico'`, todo canal precisa de `registro`
  com `data_type ∈ {int16,uint16}` e `count == 1` na v1; senão erro no boot
  (fail-fast, padrão do `config.py`).

## Bloco 4 — Serializer emite o register spec (`api/config_publisher.py`)

Só para dispositivos cujo `profile.driver == 'generico'`: o serializer lê o
`modbus.profile.register` linkado a cada sensor (via `modbus_register_id`) e emite no
canal:
```yaml
registro:
  address: <register_address>
  function: <3 se '03_holding', 4 se '04_input'>
  data_type: <int16|uint16>
  scale: <scale>
  offset: <offset>
  count: <register_count>
```
Config de N4/RS (driver específico) fica **inalterada** (sem `registro`). Reusa a
validação de C1 (`ConfigInvalida`): `data_type` fora de {int16,uint16} ou `count!=1`
→ 422 na publicação (delimita a v1 no ponto de publicação também).

## Bloco 5 — Validação (gate determinístico, sem cutover em produção)

- **Gate = equivalência unitária do decode.** Alimentar a função de decode do genérico
  com os **mesmos words crus** que o RS específico recebe e assertir saída física
  idêntica:
  - temp `int16` scale 0.1: raw `245` → `24.5`; raw `0xFFEC (65516)` → `-2.0` (signed).
  - umid `uint16` scale 0.1: raw `545` → `54.5`.
  Prova o decode sem tocar o barramento nem depender de leitura de hardware oscilante.
- **Testes por camada** (todos sem hardware): serializer emite `registro` correto
  para um perfil genérico de teste (integração Odoo); `config.py` parseia `registro`;
  `criar_driver` constrói o `AdaptadorGenerico` com `registros` (dispatch, sem
  serial); driver genérico lê via `probe` mockado e decodifica.
- **Henke de produção FICA no `rs_ws_n01_2d`.** Sem cutover. Validação em hardware do
  genérico, se desejada, é passo **pontual e confirmado à parte** (config temporária
  ou endereço reserva), NÃO o gate e NÃO na telemetria viva.

## Bloco 6 — Correção de dados do profile 9 (exatidão, não gate)

Os registers do profile 9 (`SENSOR-485-HENKE`) no Odoo estão **errados** para leitura
literal: manual diz `0x0000=umidade`, `0x0001=temperatura`, mas o Odoo tem
"Temperatura" em `address 0` e "Umidade" em `address 1` (invertidos), com `scale=1`
onde o RS divide por 10 (deveria `0.1`). Corrigir:
- Register "Temperatura HANKE" (id 10): `register_address` 0 → **1**; `scale` 1 → **0.1**; `data_type` → `int16`.
- Register "Umidade" (id 53): `register_address` 1 → **0**; `scale` 1 → **0.1**; `data_type` → `uint16`.

O driver específico (`rs_ws_n01_2d`) hardcoda o layout e **ignora** esses campos, então
o Henke de produção NÃO é afetado pela correção. A correção deixa o profile 9 exato
para um futuro uso via genérico. **Não é o gate** (o gate é o teste unitário do Bloco 5).

## Estratégia de testes

- **Submódulo** (`unittest`, `tests/test_generico.py`): decode int16/uint16 (vetores
  do Bloco 5); `read_measurements` com `probe` mockado devolve entries corretas;
  `count==2`/`data_type` não suportado → `NotImplementedError`; aplicação de `maps`.
- **Hub** (`pytest`): `config.py` parseia `registro`; validação boot para genérico
  sem registro/tipo inválido; `modbus_backend.criar_driver` dispatch para
  `AdaptadorGenerico` (probe/serial mockado); `AdaptadorGenerico.ler` repassa entries.
- **API** (`pytest`, integração Odoo): serializer emite `registro` para perfil genérico;
  não emite para N4/RS; `data_type`/`count` inválido → `ConfigInvalida`.

Comandos:
- Submódulo: `cd hub/vendor/modbus-connector && python -m pytest tests/test_generico.py -q` (ou `python -m unittest tests.test_generico`).
- Hub: `cd /home/afonso/docker/odoo_sentinela && python -m pytest hub -q`.
- API: `cd /home/afonso/docker/odoo_sentinela && PYTHONPATH=. .venv/bin/python -m pytest api/tests/test_config_serializer.py -q`.

## Arquivos

- `modbus-connector` (submódulo, repo separado): `drivers/generico.py`, `tests/test_generico.py`. Commit + push origin/main + bump do ponteiro em `hub/vendor/modbus-connector`.
- `hub/modbus_backend.py` — `AdaptadorGenerico` + `criar_driver(registros=...)`.
- `hub/leitor.py` — passa `disp.registros` a `criar_driver`.
- `hub/config.py` — `CanalConfig.registro` + validação genérico.
- `api/config_publisher.py` — emite `registro` para driver genérico + validação v1.
- Correção de dados do profile 9 no Odoo vivo (Bloco 6) — passo de execução.
- `addons/.../modbus_profile.py` — adicionar `generico` à Selection do driver (para o perfil de teste e uso futuro).

## Fora do C2

- `int32/uint32/float32` + `byte_order` (acréscimo delimitado futuro).
- Catálogo extensível de drivers (modelo + dropdown + sync submódulo↔catálogo) — C3.
- Migrar o Henke de produção para o driver genérico (opcional, futuro).
