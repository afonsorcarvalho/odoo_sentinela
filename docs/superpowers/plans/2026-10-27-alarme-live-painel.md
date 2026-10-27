# Alarme no painel na hora + sem reconexão por falha de laço — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** (1) o hub não reconecta a serial por `falha_sensor`; (2) o alarme aparece no painel (Odoo) assim que chega pelo MQTT, sem duplicar quando o `alarmes.txt` assinado for ingerido depois.

**Architecture:** (1) em `hub/leitor.py`, `falha_sensor` não marca o ciclo como ruim para reconexão. (2) `scripts/bridge_telemetria.py`, ao receber `sentinela/alarme/...`, chama a mesma lógica de `ingestao/odoo_cliente.py` (`resolver_sensor`, `resolver_coletor`, `processar_entrada_alarme`/`processar_saida_alarme`) com `hash_arquivo=None`; a ingestão do arquivo passa a reconciliar pelo evento (sensor + timestamp_deteccao) em vez de criar outro.

**Tech Stack:** Python 3.11, Odoo XML-RPC, pytest.

**Spec:** aprovado em chat pelo Afonso em 2026-10-27 (follow-up de `docs/superpowers/specs/2026-10-27-falha-instrumento-alarme-design.md`, gaps 1 e 2 da verificação em prod).

## Global Constraints
- O arquivo assinado continua sendo a prova: registro criado ao vivo recebe `origem_arquivo_hash` quando o arquivo é ingerido.
- Nunca dois registros para o mesmo evento (mesmo `sensor_id` + mesmo `timestamp` de entrada), em qualquer ordem: ao vivo antes do arquivo, só arquivo, só ao vivo, ou ao vivo entrada+saída antes do arquivo.
- Falha do Odoo no bridge não pode derrubar o bridge nem o NOTIFY ao vivo (o toast continua).
- `sensor_offline` e exceção de comunicação continuam disparando reconexão; `falha_sensor` e `suspeito` não mudam a lógica de alarme, só a de reconexão (`suspeito` fica como está).
- Prod é persistente: nada apaga dados.

## Review Focus
- Ao vivo entrada+saída e depois arquivo com entrada+saída → 1 registro, fechado, com hash → Task 2.
- Bridge sem Odoo acessível → loga e segue, NOTIFY sai → Task 2.
- Laço aberto contínuo → nenhuma linha "serial reconectado" → Task 1.

---

### Task 1: Hub — falha de laço não dispara reconexão
**Files:** Modify `hub/leitor.py` (`_ler_device`); Test `hub/tests/test_leitor.py`.
- [ ] Failing test `test_falha_sensor_continua_nao_reconecta`: driver devolvendo sempre -25.0 (0 mA, canal 4–20), `reconexao_n=2`; após 6 ciclos `backend.criacoes == 1` e todas as leituras `falha_sensor` (nenhuma `sensor_offline`).
- [ ] Run `.venv/bin/python -m pytest hub/tests/test_leitor.py -q` → FAIL.
- [ ] Implement: falha NE43 não seta o flag que alimenta `falhas_seguidas`.
- [ ] Run `hub/tests` → PASS. Commit `fix(hub): open 4-20 loop does not trigger serial reconnect`.

### Task 2: Alarme ao vivo no Odoo + reconciliação na ingestão
**Files:** Modify `scripts/bridge_telemetria.py` (ramo `alarme`), `ingestao/odoo_cliente.py` (`processar_entrada_alarme`, `processar_saida_alarme`); Test `scripts/tests/test_bridge_alarme.py`, `ingestao/tests/` (novo `test_reconcilia_alarme_ao_vivo.py`, fake `executar` no estilo de `test_falha_sensor_alarme.py`).
- [ ] Failing tests:
  - `processar_entrada_alarme` com registro existente do mesmo sensor e mesmo `timestamp_deteccao` (aberto OU fechado) devolve o id existente, não cria, e grava `origem_arquivo_hash` se estiver vazio e um hash foi passado.
  - `processar_saida_alarme` para evento já fechado (mesmo sensor, `timestamp_resolucao_sensor` já preenchido com o mesmo timestamp) não conta como órfão (devolve o id).
  - bridge: mensagem `entrada_alarme` chama `processar_entrada_alarme` com `hash_arquivo=None` e ainda faz o `pg_notify`; exceção do Odoo é logada e o `pg_notify` ainda acontece.
- [ ] Run → FAIL. Implement (cliente Odoo do bridge com as mesmas envs `ODOO_URL/DB/USER/SENHA`, conexão preguiçosa e reconexão em erro). Run `scripts/tests` + `ingestao/tests` (só os que não dependem de Odoo/Timescale vivos) → PASS. Commit `feat(bridge): open/close Odoo alarm live; ingestion reconciles by event`.
