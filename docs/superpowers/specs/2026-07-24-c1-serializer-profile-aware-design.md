# Design — Serializer profile-aware + validação na publicação (Plano C1)

> Primeira fatia do Plano C da discussão `docs/discussao-drivers-extensibilidade.md`.
> Faz o config-publish (Odoo → config.yaml do hub) gerar config correta por
> sensor — map 4-20mA só quando o sensor usa, valor nativo caso contrário — e
> validar antes de publicar. É pré-requisito forçado de C2 (driver genérico) e
> fecha a dívida do map-opcional do Plano B. NÃO constrói o driver genérico nem o
> catálogo de drivers (C2/C3).

## Problema

`api/config_publisher.py:serializar_config_hub` hoje crava, para **todo** canal:
`protocolo_origem: '4-20ma'` e um bloco `map: {in:[ma_in_min,ma_in_max], out:[eng_out_min,eng_out_max]}`.

Isso está errado para sensores que entregam o valor físico direto (ex.: RS-WS-N01-2D
= °C/%RH nativo). No incidente, um sensor nativo com `eng_out=[0,0]` publicado gerou
`map:[…]→[0,0]`, que **zera toda leitura**. Por isso hoje a config do HUB-E2E-01 é
mantida à mão no Pi: republicar pelo Odoo re-geraria a config errada.

Além disso, o Plano B tornou o `map` opcional no hub (`hub/config.py:_canal` aceita
map ausente), abrindo uma dívida: um canal 4-20mA sem map reportaria mA cru como
`ok`. A validação que fecha essa dívida vive aqui.

## Objetivo

O serializer decide, por sensor, entre **map** e **valor nativo**, a partir de um
campo explícito; valida a config e falha **no Odoo/API** (não no Pi) com mensagem
clara; e o round-trip (republicar HUB-E2E-01) reproduz a config que está no ar, de
modo que a edição manual deixa de ser caso especial.

## Componente 1 — Campo `usa_map` no sensor

Novo booleano em `sensor_monitor.sensor` (`addons/afr_sentinela_sensor_monitor/models/sensor.py`):
```python
usa_map = fields.Boolean(
    default=False,
    help='Se marcado, o valor cru passa pelo mapeamento (ma_in→eng_out), '
         'ex.: sensor 4-20mA via N4AIB16. Se desmarcado, o sensor entrega o '
         'valor físico direto (ex.: RS-WS-N01-2D em °C/%RH) e nenhum map é aplicado.')
```
- Default **`false`** (valor nativo) — fail-safe: sensor mal-configurado reporta o
  valor cru (visivelmente errado) em vez de ser zerado por um map ruim.
- É a **única fonte de verdade** para a decisão do map. O `conversor_tipo` existente
  permanece como metadado descritivo, **não** é usado pelo serializer.
- Exposto no form do sensor (`views/*.xml`) para ser editável.

## Componente 2 — Serializer lê os dados em vez de cravar

Em `serializar_config_hub`, na construção de cada `canal`:
- Ler o campo `usa_map` do sensor (adicionar à lista de `fields` do `search_read`).
- **`usa_map = True`** → escreve `map: {in:[ma_in_min,ma_in_max], out:[eng_out_min,eng_out_max]}` (como hoje).
- **`usa_map = False`** → **não** inclui a chave `map` no canal.
- **`protocolo_origem`** → emitir o valor real do campo do sensor (hoje `rs485` em
  todos), removendo o hardcode `'4-20ma'`. (Muda o valor no arquivo dos N4 de
  `'4-20ma'`→`'rs485'`; é metadado de telemetria, não afeta a leitura.)

O resto do canal (ch, sensor_id, area/tipo/unidade, filtro, calibração) permanece.

## Componente 3 — Validação na publicação

Antes de emitir o arquivo, validar e levantar erro claro que o router traduz em
HTTP 422 (falha no Odoo/API, nunca no Pi):

1. **Driver conhecido:** o `driver` do profile ∈ {`n4aib16`, `rs_ws_n01_2d`}. Senão,
   erro citando o hub/dispositivo e o driver inválido.
2. **`usa_map = True` exige map real:** `ma_in_min != ma_in_max` **e**
   `eng_out_min != eng_out_max`. Um map degenerado (`[0,0]` ou faixa nula) com
   `usa_map=True` é erro — impede "4-20mA sem map de verdade".
3. **`usa_map = False` → sem map:** nenhum `map` é escrito (garantido pelo
   Componente 2). Impede "nativo com map zerado" (a causa do incidente).

Mensagem de erro nomeia o `sensor_code` e o motivo.

`api/config_publish_router.py`: envolver `serializar_config_hub` para traduzir o erro
de validação em `HTTPException(status_code=422, detail=…)`.

## Componente 4 — `rs_ws_n01_2d` na Selection do driver

Em `addons/afr_sentinela_sensor_monitor/models/modbus_profile.py`, a Selection
`driver` ganha o valor `rs_ws_n01_2d` (espelha o que `hub/modbus_backend.criar_driver`
já conhece):
```python
driver = fields.Selection(
    [('n4aib16', 'N4AIB16'), ('rs_ws_n01_2d', 'RS-WS-N01-2D')],
    default='n4aib16', required=True, ...)
```
**Fronteira com C3:** só um valor a mais na Selection. NÃO é o catálogo de drivers
como modelo/UI (isso é C3).

## Componente 5 — Correções de dados no Odoo (precondições do round-trip)

Registros específicos da instância viva, corrigidos por escrita direta (não são seed
do addon). Necessários para o round-trip de HUB-E2E-01 reproduzir a config no ar:
- Profile 9 (`SENSOR-485-HENKE`): `driver` `n4aib16` → `rs_ws_n01_2d`.
- Sensor `TEMP-HENKE`: `modbus_channel` 1 → **2**; `usa_map` = False.
- Sensor `UMID-HENKE`: `modbus_channel` 0 → **1**; linkar `modbus_register_id` ao
  register "Umidade" (id 53) do profile 9; `usa_map` = False.
- Sensores N4 `SNR-E2E-CH1`, `PD-HUB-CH2`: `usa_map` = **True**.

(No RS, a convenção do adapter é `channel=i+1`: 1=umidade, 2=temperatura — por isso
UMID=1, TEMP=2.)

## Componente 6 — Teste de aceitação (seguro, sem quebrar produção)

1. Gerar o config de HUB-E2E-01 pelo serializer novo em memória/arquivo, **sem publicar**.
2. **Diff** contra a config hand-edited que está no Pi (`~/sentinela-hub/config.yaml`):
   devem bater no essencial — Henke com canais nativos (sem map, ch1=UMID/ch2=TEMP),
   N4 com map. Diferenças aceitáveis: ordem de chaves, `intervalo_leitura_s`.
3. Só após bater, opcionalmente publicar de verdade e confirmar via Timescale que o
   Henke segue lendo (24-25°C / ~54%RH) e o N4 intacto.

## Estratégia de testes

Testes do serializer são **integração com Odoo real** (padrão de
`api/tests/test_config_serializer.py`, via `provisionar_demo` + `odoo_cliente`):
1. Sensor `usa_map=True` → config emite `map`.
2. Sensor `usa_map=False` → config **não** tem `map` no canal; `protocolo_origem`
   vem do campo do sensor.
3. `usa_map=True` com map degenerado (`eng_out_min==eng_out_max`) → validação levanta.
4. Profile com `driver` desconhecido → validação levanta.
5. Regressão: o sensor N4 do demo (`usa_map=True`) continua gerando `map` como antes.

Teste do addon (`addons/afr_sentinela_sensor_monitor/tests/`): campo `usa_map` existe
com default `False`; Selection do driver aceita `rs_ws_n01_2d`. Rodar com
`--test-tags /afr_sentinela_sensor_monitor`.

## Arquivos

- `addons/afr_sentinela_sensor_monitor/models/sensor.py` — campo `usa_map`.
- `addons/afr_sentinela_sensor_monitor/models/modbus_profile.py` — Selection `+rs_ws_n01_2d`.
- `addons/afr_sentinela_sensor_monitor/views/…xml` — expõe `usa_map` no form do sensor.
- `api/config_publisher.py` — serializer map-opcional + protocolo_origem + validação.
- `api/config_publish_router.py` — traduz erro de validação em HTTP 422.
- `api/tests/test_config_serializer.py`, `addons/afr_sentinela_sensor_monitor/tests/` — testes.
- Correções de dados no Odoo vivo (Componente 5) — passo de execução, não código.

## Fora do C1 (C2/C3)

- Serializar o register spec (address/data_type/scale/offset) — só o driver genérico
  precisa (C2). O modelo já tem o schema (`modbus.profile.register`), mas com dados a
  corrigir para o RS (endereços invertidos, scale=1 em vez de 0.1) — tratado no C2.
- Driver genérico register-driven no submódulo (C2).
- Catálogo de drivers como modelo + dropdown + sync submódulo↔catálogo (C3).
