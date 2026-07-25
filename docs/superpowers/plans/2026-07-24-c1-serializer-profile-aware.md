# Serializer profile-aware + validação (Plano C1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O config-publish (Odoo → config.yaml do hub) decide map-vs-nativo por sensor via campo `usa_map`, valida antes de publicar, e o round-trip de HUB-E2E-01 reproduz a config que está no ar.

**Architecture:** Campo booleano `usa_map` no sensor é a fonte de verdade do map. O serializer (`api/config_publisher.py`) para de cravar `4-20ma`/`map`: emite `map` só quando `usa_map=True` e `protocolo_origem` real. Validação levanta erro (HTTP 422) para driver desconhecido ou map degenerado com `usa_map=True`. Correções de dados na instância viva fecham o round-trip.

**Tech Stack:** Odoo 16 (addon `afr_sentinela_sensor_monitor`), FastAPI (`api/`), pytest (integração com Odoo real), YAML.

## Global Constraints

- `usa_map` default **`False`** (valor nativo) — fail-safe: sensor mal-configurado reporta valor cru, não zerado.
- `usa_map` é a ÚNICA fonte de verdade do map. `conversor_tipo` permanece descritivo, NÃO usado pelo serializer.
- Serializer: `usa_map=True` → escreve `map: {in:[ma_in_min,ma_in_max], out:[eng_out_min,eng_out_max]}`; `usa_map=False` → NÃO inclui `map`. `protocolo_origem` vem do campo do sensor (remove o hardcode `'4-20ma'`).
- Validação falha no Odoo/API (HTTP 422), NUNCA no Pi: driver ∈ {`n4aib16`,`rs_ws_n01_2d`}; `usa_map=True` exige `ma_in_min!=ma_in_max` E `eng_out_min!=eng_out_max`.
- Convenção do adapter RS: `channel=i+1` → UMID-HENKE=canal 1, TEMP-HENKE=canal 2.
- Escopo: SÓ `usa_map` + serializer + validação + 1 valor na Selection + correções de dados. NÃO o driver genérico nem o catálogo (C2/C3). NÃO serializar register spec.
- Banco Odoo: `sentinela`; container `odoo_sentinela-odoo-1`; API container `odoo_sentinela-api-1` (ODOO_DB=sentinela).

## Estado atual (referência)

`api/config_publisher.py` linhas ~72 (fields dos sensores) e ~100-121 (construção do canal):
```python
sensores = ex('sensor_monitor.sensor', 'search_read',
              [('modbus_register_id', 'in', regs)],
              fields=['sensor_code', 'modbus_channel', 'ma_in_min', 'ma_in_max',
                      'eng_out_min', 'eng_out_max', 'filtro_tipo', 'filtro_alpha',
                      'unidade', 'protocolo_origem', 'area_id', 'measurement_type_id',
                      'calibracao_vigente_id'])
...
canal = {
    'ch': s['modbus_channel'], 'sensor_id': s['sensor_code'],
    'area_id': ..., 'tipo_medida': ..., 'unidade': s.get('unidade') or '',
    'protocolo_origem': '4-20ma',                      # <- hardcode
    'map': {'in': [s['ma_in_min'], s['ma_in_max']],    # <- sempre
            'out': [s['eng_out_min'], s['eng_out_max']]},
}
```
`driver` vem de `ex('sensor_monitor.modbus.profile','read',[profile_id],fields=['driver'])[0]['driver']`.

`addons/afr_sentinela_sensor_monitor/models/modbus_profile.py`: `driver = fields.Selection([('n4aib16','N4AIB16')], ...)`.

---

## Task 1: Addon — campo `usa_map`, Selection `rs_ws_n01_2d`, form

**Files:**
- Modify: `addons/afr_sentinela_sensor_monitor/models/sensor.py`
- Modify: `addons/afr_sentinela_sensor_monitor/models/modbus_profile.py`
- Modify: `addons/afr_sentinela_sensor_monitor/views/sensor_views.xml`
- Test: `addons/afr_sentinela_sensor_monitor/tests/test_config_fields.py`

**Interfaces:**
- Produces: campo `sensor_monitor.sensor.usa_map` (Boolean, default False) e o valor `rs_ws_n01_2d` na Selection `sensor_monitor.modbus.profile.driver`.

- [ ] **Step 1: Escrever o teste que falha**

Adicionar em `addons/afr_sentinela_sensor_monitor/tests/test_config_fields.py` (classe `TestConfigFields`, `TransactionCase`):
```python
    def test_usa_map_existe_default_false(self):
        campos = self.env['sensor_monitor.sensor'].fields_get(['usa_map'])
        assert campos['usa_map']['type'] == 'boolean'
        s = self.env['sensor_monitor.sensor'].new({})
        assert s.usa_map is False

    def test_driver_aceita_rs_ws_n01_2d(self):
        campos = self.env['sensor_monitor.modbus.profile'].fields_get(['driver'])
        valores = dict(campos['driver']['selection'])
        assert 'rs_ws_n01_2d' in valores
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker exec odoo_sentinela-odoo-1 odoo -d sentinela -u afr_sentinela_sensor_monitor --test-enable --test-tags /afr_sentinela_sensor_monitor --no-http --stop-after-init 2>&1 | grep -iE "FAIL|ERROR|usa_map|rs_ws"`
Expected: FAIL — `usa_map` não existe / `rs_ws_n01_2d` não está na Selection.

- [ ] **Step 3: Adicionar o campo e o valor da Selection**

Em `addons/afr_sentinela_sensor_monitor/models/sensor.py`, após `conversor_tipo`:
```python
    usa_map = fields.Boolean(
        default=False,
        help='Se marcado, o valor cru passa pelo mapeamento (ma_in→eng_out), '
             'ex.: sensor 4-20mA via N4AIB16. Se desmarcado, o sensor entrega o '
             'valor físico direto (ex.: RS-WS-N01-2D em °C/%RH) e nenhum map é aplicado.')
```
Em `addons/afr_sentinela_sensor_monitor/models/modbus_profile.py`:
```python
    driver = fields.Selection(
        [('n4aib16', 'N4AIB16'), ('rs_ws_n01_2d', 'RS-WS-N01-2D')],
        default='n4aib16', required=True,
        help='Driver que o Hub usa para ler este perfil (define a família do dispositivo).')
```

- [ ] **Step 4: Expor `usa_map` no form do sensor**

Em `addons/afr_sentinela_sensor_monitor/views/sensor_views.xml`, após a linha `<field name="conversor_tipo"/>` (≈linha 31), adicionar:
```xml
                        <field name="usa_map" invisible="protocolo_origem != 'rs485'"/>
```

- [ ] **Step 5: Rodar o teste do addon e ver passar (aplica o upgrade)**

Run: `docker exec odoo_sentinela-odoo-1 odoo -d sentinela -u afr_sentinela_sensor_monitor --test-enable --test-tags /afr_sentinela_sensor_monitor --no-http --stop-after-init 2>&1 | tail -20`
Expected: os dois testes novos PASSAM; sem regressão em `TestConfigFields`. Este comando também faz o upgrade do módulo no banco `sentinela` (cria a coluna `usa_map`).

- [ ] **Step 6: Reiniciar o Odoo em execução (registry vê o campo novo)**

Run: `docker restart odoo_sentinela-odoo-1 && sleep 8 && docker exec odoo_sentinela-odoo-1 sh -c 'true' && echo "odoo reiniciado"`
Motivo: o servidor em execução mantém o registry antigo em memória; sem restart, chamadas XML-RPC com `fields=['usa_map']` (Task 2) dariam "Invalid field usa_map".

- [ ] **Step 7: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela
git add addons/afr_sentinela_sensor_monitor/models/sensor.py \
        addons/afr_sentinela_sensor_monitor/models/modbus_profile.py \
        addons/afr_sentinela_sensor_monitor/views/sensor_views.xml \
        addons/afr_sentinela_sensor_monitor/tests/test_config_fields.py
git commit -m "feat(sensor): campo usa_map + driver rs_ws_n01_2d na Selection

usa_map (default False) e a fonte de verdade do map no config-publish;
rs_ws_n01_2d destrava o driver RS no perfil (fronteira com C3: so a Selection).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Serializer — map opcional + protocolo_origem + validação

**Files:**
- Modify: `api/config_publisher.py`
- Modify: `api/config_publish_router.py`
- Test: `api/tests/test_config_serializer.py`

**Interfaces:**
- Consumes: campo `usa_map` (Task 1), no Odoo em execução.
- Produces: `serializar_config_hub` emite `map` só quando `usa_map=True`, `protocolo_origem` do campo do sensor; levanta `ConfigInvalida` (nova exceção, subclasse de `ValueError`) para driver desconhecido ou map degenerado com `usa_map=True`. O router traduz em HTTP 422.

- [ ] **Step 1: Escrever os testes que falham (integração com Odoo real)**

Adicionar em `api/tests/test_config_serializer.py`. Seguir o padrão do arquivo: cada teste chama `get_cliente_servico()` direto (não há fixture), usa `_prov_hub_modbus` e `provisionar_demo.HUB_CODE`. Importar `pytest` e `ConfigInvalida` no topo do arquivo.
```python
def test_usa_map_true_emite_map():
    cliente = get_cliente_servico()
    _prov_hub_modbus(cliente)
    ex = lambda *a, **k: odoo_cliente.executar(cliente, *a, **k)
    sid = ex('sensor_monitor.sensor', 'search', [('sensor_code', '=', SENSOR_CODE)])[0]
    ex('sensor_monitor.sensor', 'write', [sid], {'usa_map': True})
    cfg = serializar_config_hub(cliente, provisionar_demo.HUB_CODE)
    canal = cfg['barramentos'][0]['dispositivos'][0]['canais'][0]
    assert 'map' in canal
    assert canal['protocolo_origem'] == 'rs485'   # vem do campo, não hardcode

def test_usa_map_false_omite_map():
    cliente = get_cliente_servico()
    _prov_hub_modbus(cliente)
    ex = lambda *a, **k: odoo_cliente.executar(cliente, *a, **k)
    sid = ex('sensor_monitor.sensor', 'search', [('sensor_code', '=', SENSOR_CODE)])[0]
    ex('sensor_monitor.sensor', 'write', [sid], {'usa_map': False,
        'eng_out_min': 0.0, 'eng_out_max': 0.0})   # map degenerado, mas nativo → OK
    cfg = serializar_config_hub(cliente, provisionar_demo.HUB_CODE)
    canal = cfg['barramentos'][0]['dispositivos'][0]['canais'][0]
    assert 'map' not in canal

def test_usa_map_true_map_degenerado_levanta():
    from api.config_publisher import ConfigInvalida
    cliente = get_cliente_servico()
    _prov_hub_modbus(cliente)
    ex = lambda *a, **k: odoo_cliente.executar(cliente, *a, **k)
    sid = ex('sensor_monitor.sensor', 'search', [('sensor_code', '=', SENSOR_CODE)])[0]
    ex('sensor_monitor.sensor', 'write', [sid], {'usa_map': True,
        'eng_out_min': 0.0, 'eng_out_max': 0.0})
    with pytest.raises(ConfigInvalida):
        serializar_config_hub(cliente, provisionar_demo.HUB_CODE)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `cd /home/afonso/docker/odoo_sentinela && PYTHONPATH=. .venv/bin/python -m pytest api/tests/test_config_serializer.py -q`
(Os testes conectam ao Odoo em `localhost:8189` / db `sentinela` / admin-admin pelos defaults de `api/odoo.py` — o Odoo já deve estar reiniciado com `usa_map` pela Task 1 Step 6.)
Expected: FAIL — `ConfigInvalida` não existe; `map` sempre presente; `protocolo_origem` == '4-20ma'.

- [ ] **Step 3: Implementar no serializer**

Em `api/config_publisher.py`, no topo:
```python
class ConfigInvalida(ValueError):
    """Config rejeitada na publicação (falha no Odoo/API, não no Pi)."""


_DRIVERS_CONHECIDOS = {'n4aib16', 'rs_ws_n01_2d'}
```
Adicionar `'usa_map'` à lista de `fields` do `search_read` dos sensores (linha ~72).

Validar o driver logo após lê-lo:
```python
driver = ex('sensor_monitor.modbus.profile', 'read', [profile_id], fields=['driver'])[0]['driver']
if driver not in _DRIVERS_CONHECIDOS:
    raise ConfigInvalida(f"driver desconhecido {driver!r} no dispositivo addr "
                         f"{dev['slave_address']} (hub {hub_code})")
```
Trocar a construção do canal:
```python
canal = {
    'ch': s['modbus_channel'], 'sensor_id': s['sensor_code'],
    'area_id': areas_por_id.get(s['area_id'][0]) if s.get('area_id') else None,
    'tipo_medida': tipos_por_id.get(s['measurement_type_id'][0]) if s.get('measurement_type_id') else None,
    'unidade': s.get('unidade') or '',
    'protocolo_origem': s.get('protocolo_origem') or 'rs485',
}
if s.get('usa_map'):
    if s['ma_in_min'] == s['ma_in_max'] or s['eng_out_min'] == s['eng_out_max']:
        raise ConfigInvalida(
            f"sensor {s['sensor_code']}: usa_map=True mas o map é degenerado "
            f"(in=[{s['ma_in_min']},{s['ma_in_max']}] out=[{s['eng_out_min']},{s['eng_out_max']}])")
    canal['map'] = {'in': [s['ma_in_min'], s['ma_in_max']],
                    'out': [s['eng_out_min'], s['eng_out_max']]}
```
(O bloco de `filtro` e `calibracao` continua igual, após.)

- [ ] **Step 4: Traduzir o erro no router**

Em `api/config_publish_router.py`, no handler `publicar_config`, envolver a serialização:
```python
    from .config_publisher import ConfigInvalida
    try:
        cfg = serializar_config_hub(cliente, hub_code, version=body.version)
    except ConfigInvalida as e:
        raise HTTPException(status_code=422, detail=str(e))
```

- [ ] **Step 5: Rodar e ver passar**

Run: `cd /home/afonso/docker/odoo_sentinela && PYTHONPATH=. .venv/bin/python -m pytest api/tests/test_config_serializer.py -q`
Expected: PASS — os três testes novos + os existentes do arquivo (regressão: o sensor N4 do demo com `usa_map=True` continua gerando `map`).

- [ ] **Step 6: Commit**

```bash
cd /home/afonso/docker/odoo_sentinela
git add api/config_publisher.py api/config_publish_router.py api/tests/test_config_serializer.py
git commit -m "feat(config-publish): map por usa_map + validacao (HTTP 422)

serializer emite map so quando usa_map=True e protocolo_origem do campo;
ConfigInvalida para driver desconhecido ou map degenerado com usa_map=True;
router traduz em 422. Fecha a divida do map-opcional do plano B.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Correções de dados no Odoo + round-trip de aceitação (operacional)

**Files:**
- Nenhum código. Escritas no Odoo vivo (via MCP odoo ou `ingestao/odoo_cliente`) + geração/diff de config.

**Interfaces:**
- Consumes: serializer novo (Task 2), campo `usa_map` (Task 1).
- Produces: config gerada de HUB-E2E-01 que bate com a config hand-edited no Pi (prova de que o config-publish deixou de ser perigo).

- [ ] **Step 1: Corrigir os registros no Odoo (instância viva)**

Escritas (idempotentes) em `sensor_monitor`:
- Profile `SENSOR-485-HENKE` (id 9): `driver` → `rs_ws_n01_2d`.
- Sensor `TEMP-HENKE` (id 275): `modbus_channel` → `2`; `usa_map` → `False`.
- Sensor `UMID-HENKE` (id 520): `modbus_channel` → `1`; `modbus_register_id` → register "Umidade" do profile 9 (id 53); `usa_map` → `False`.
- Sensores `SNR-E2E-CH1` (271), `PD-HUB-CH2` (274): `usa_map` → `True`.

Verificar após: `search_read` desses sensores confirmando os valores.

- [ ] **Step 2: Gerar a config de HUB-E2E-01 SEM publicar**

Rodar o serializer em modo leitura (sem escrever no SFTP nem notificar MQTT). Ex.: um script one-off que chama `serializar_config_hub(get_cliente_servico(), 'HUB-E2E-01')` e imprime `yaml.safe_dump(cfg)`. NÃO chamar `escrever_config_sftp` nem o endpoint de publish.

- [ ] **Step 3: Diff contra a config que está no Pi**

Baixar `~/sentinela-hub/config.yaml` do Pi (`scp fitadigital@192.168.0.211:~/sentinela-hub/config.yaml`) e comparar com a gerada. Devem bater no essencial:
- Barramento Henke: driver `rs_ws_n01_2d`, canal ch1=UMID-HENKE (sem `map`), ch2=TEMP-HENKE (sem `map`).
- Barramento N4: SNR-E2E-CH1 e PD-HUB-CH2 COM `map`.
Diferenças aceitáveis e a ignorar: ordem de chaves, `intervalo_leitura_s`, campos de identidade/tenant que o serializer operacional não emite (hub_id, sftp, etc. — ver docstring de `config_publisher`).

Registrar o resultado do diff. Se bater no essencial: C1 validado — o config-publish agora gera a config correta.

- [ ] **Step 4: (NÃO automatizar) Publicar de verdade — passo confirmado à parte**

**NÃO** publicar nem re-deployar no Pi dentro deste plano. O hub em produção lê a config manual e está estável; republicar sobrescreve. Deixar como passo operacional separado, a ser confirmado com o humano depois que o diff (Step 3) fechar. Registrar no relatório que ficou pendente e por quê.

---

## Self-Review

**Spec coverage:**
- §Componente 1 (usa_map) → Task 1. ✓
- §Componente 2 (serializer lê dados) → Task 2 Step 3. ✓
- §Componente 3 (validação 422) → Task 2 Steps 3-4. ✓
- §Componente 4 (Selection rs_ws_n01_2d) → Task 1 Step 3. ✓
- §Componente 5 (correções de dados) → Task 3 Step 1. ✓
- §Componente 6 (round-trip seguro) → Task 3 Steps 2-3; publish real explicitamente fora (Step 4). ✓
- §Testes 1-5 → Task 2 Step 1 (serializer) + Task 1 Step 1 (addon). ✓

**Placeholder scan:** os comandos de teste da API (Step 2/5 da Task 2) e do addon dependem do modo real de rodar neste projeto — marcados "confirmar ao implementar" com o padrão provável (docker exec / run-api.sh). Não é placeholder de lógica; é ponto de verificação operacional legítimo. O implementador confirma o invocador exato.

**Type consistency:** `ConfigInvalida` definida na Task 2 Step 3 e usada no router (Step 4) e nos testes (Step 1). `usa_map` criado na Task 1, consumido na Task 2 e Task 3. Convenção de canal UMID=1/TEMP=2 consistente entre spec e Task 3.

**Ordem/dependência:** T1 (campo, com upgrade+restart do Odoo) → T2 (serializer, precisa do campo vivo) → T3 (dados + round-trip, precisa de T1+T2). Sequencial obrigatório.

**Nota:** Task 1 Step 6 (restart do Odoo) é essencial — sem ele o XML-RPC da Task 2 não enxerga `usa_map`.
