# Design — Integração Odoo (resolução de site + `file.ledger`) no serviço de ingestão

> Complementa `docs/superpowers/specs/2026-07-18-ingestao-fatia-fina-design.md` (validação + TimescaleDB, rodada anterior) e `odoo_modelo_dados_spec.md` (seção 8 — integração com o serviço de ingestão). Fecha o ponto em aberto "desenho exato da API Odoo↔ingestão": XML-RPC nativo, sem código Odoo novo.

## Escopo desta rodada

O serviço de ingestão passa a consultar o Odoo (via XML-RPC) para resolver o `site_code` real a partir do `coletor_id` do arquivo (substituindo o `site_id` fixo `SITE-SIM-0001` da rodada anterior), e a gravar um registro `sensor_monitor.file.ledger` refletindo o resultado da ingestão — válido ou inválido.

**Fora de escopo**: arquivo de alarmes (`tipo_arquivo=alarmes`), criação de `sensor_monitor.alarm.event`, usuário de serviço dedicado (usa `admin`/`admin` do Odoo, já confirmado funcional via XML-RPC nesta rodada — trocar por um usuário técnico dedicado fica para quando isso for pra produção), controle de drift de `config_version`.

## Contexto levantado nesta rodada

- Credenciais `admin`/`admin` confirmadas funcionais via XML-RPC contra o Odoo já rodando (`http://localhost:8189`, banco `sentinela`) — `common.authenticate` retorna `uid=2`.
- Já existe cadastro manual no Odoo (site "CME Oximed" `CMEOX-01`, coletor `COL-01`, sensor `TEMP-01`) — não usado por este fluxo, permanece intocado.
- Não existe ainda cadastro correspondente ao cenário do `coletor_simulado` (`COL-SIM-0001` etc.) — precisa ser provisionado.

## 1. Cliente Odoo (`ingestao/odoo_cliente.py`)

- `ClienteOdoo`: classe simples guardando `db`, `senha`, `uid` (retornado por `common.authenticate`), e o proxy `models` (`{url}/xmlrpc/2/object`).
- `conectar(url, db, usuario, senha) -> ClienteOdoo`: autentica via `{url}/xmlrpc/2/common`, levanta `RuntimeError` se a autenticação falhar (uid falso/None).
- `executar(cliente, model, metodo, *args, **kwargs)`: wrapper fino sobre `models.execute_kw(db, uid, senha, model, metodo, list(args), kwargs)` — usado por todas as chamadas subsequentes.
- `resolver_coletor(cliente, coletor_code) -> dict`: três chamadas (`search_read` no coletor por `coletor_code` → `read` no hub pelo `hub_id` → `read` no site pelo `site_id`), retorna `{'id', 'hub_id', 'site_id', 'site_code'}`. Levanta `ValueError` se o `coletor_code` não existir no Odoo.

## 2. Provisionamento do cenário simulado (`ingestao/provisionar_odoo_sim.py`)

Script único, idempotente (busca por código antes de criar — nunca duplica), usando `odoo_cliente` para criar, se ainda não existirem:
- `res.partner` "Cliente Simulado" (novo, não usa o partner do CMEOX-01).
- `sensor_monitor.site` — `site_code=SITE-SIM-0001`, `vertical=cme_hospitalar`.
- `sensor_monitor.hub` — `hub_code=HUB-SIM-0001`, vinculado ao site acima.
- `sensor_monitor.area` — `area_code=AREA-SIM-EXPURGO`, categoria `EXPURGO` (dado de referência já existente da Fase 1), vinculada ao site acima.
- `sensor_monitor.coletor` — `coletor_code=COL-SIM-0001`, `tipo=esp32_wifi`, vinculado ao hub acima.
- Dois `sensor_monitor.sensor` — `SNR-SIM-TEMP-01` (`measurement_type=temperatura`) e `SNR-SIM-PRES-01` (`measurement_type=pressao_diferencial`), ambos `protocolo_origem=4-20mA`, vinculados ao coletor e à área acima.

CLI: `python -m ingestao.provisionar_odoo_sim --odoo-url http://localhost:8189 --odoo-db sentinela --odoo-usuario admin --odoo-senha admin`.

## 3. Extensão do `ResultadoValidacao` (`validador.py`)

Três campos novos, já disponíveis no parsing (`parse_arquivo` lê cabeçalho e rodapé numa passada só, antes mesmo de validar a cadeia) mas não expostos até agora: `data_referencia` (do cabeçalho), `hash_final`, `assinatura` (do rodapé, o que foi *declarado* pelo arquivo — não necessariamente o recalculado, importante para auditoria mesmo em caso de rejeição). Populados em **todos** os caminhos de retorno de `validar_arquivo` (válido ou não), já que o parsing acontece antes de qualquer verificação.

## 4. Gravação do ledger (`odoo_cliente.py`)

- `escrever_ledger(cliente, coletor_odoo_id, tipo_arquivo, data_referencia, status_validacao, motivo_rejeicao, total_linhas, hash_final, assinatura) -> int`: busca um `file.ledger` existente por (`coletor_id`, `data_referencia`, `tipo_arquivo`) — se existir, `write()`; senão, `create()`. Preenche também `horario_recebimento` (agora). Reflete a constraint de unicidade já existente no modelo (Fase 1) — reingestão do mesmo arquivo atualiza o registro em vez de duplicar (não é proteção contra reingestão, é só idempotência da escrita do ledger em si).

## 5. Orquestração (`ingestor.py`)

`ingerir_arquivo(caminho, registro_path, dsn, cliente_odoo)` — assinatura muda: `site_id` fixo sai, `cliente_odoo` (já conectado) entra.

Fluxo:
1. `validar_arquivo` (como antes).
2. `resolver_coletor(cliente_odoo, resultado.coletor_id)` — se o coletor não existir no Odoo, retorna resultado `invalido` com o motivo, **sem gravar ledger** (nada a que anexar).
3. Se `status_validacao == 'valido'`: grava no Timescale usando o `site_code` resolvido (em vez do fixo).
4. Grava `file.ledger` via `escrever_ledger` — sempre que o coletor foi resolvido, válido ou não.

CLI ganha `--odoo-url`, `--odoo-db`, `--odoo-usuario`, `--odoo-senha` (defaults: `http://localhost:8189`, `sentinela`, `admin`, `admin`); perde `--site-id` (resolvido automaticamente agora).

## 6. Testes

- `test_odoo_cliente.py`: `resolver_coletor` contra o coletor manual já existente (`COL-01`) prova a integração básica sem depender do provisionamento novo; `ValueError` para código inexistente.
- `test_provisionar_odoo_sim.py`: roda o provisionamento duas vezes, confirma que não duplica (mesmo `id` retornado); confirma que `resolver_coletor` consegue resolver `COL-SIM-0001` depois.
- `test_validador.py` (extensão): a suíte já existente ganha asserts para os 3 campos novos no caminho feliz.
- `test_odoo_cliente.py` (extensão): `escrever_ledger` cria na primeira chamada, atualiza (não duplica) na segunda para o mesmo (coletor, data, tipo).
- `test_ingestor.py` (extensão): fluxo real ponta a ponta com `cliente_odoo` de verdade — confirma leituras no Timescale **e** o `file.ledger` criado no Odoo com os campos certos.

## Pontos que seguem em aberto (não bloqueiam esta rodada)

- Arquivo de alarmes + `alarm.event` — próxima rodada.
- Usuário de serviço dedicado (hoje usa `admin`/`admin`).
- Proteção contra reingestão duplicada de um arquivo já processado (o `file.ledger` agora existe e registra o estado, mas o `ingestor.py` ainda não *consulta* o ledger antes de reingerir — só grava o resultado).
