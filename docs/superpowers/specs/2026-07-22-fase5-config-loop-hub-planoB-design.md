# Fase 5 — Config loop (Plano B: Hub real + hardware) design

**Data:** 2026-07-22
**Status:** design aprovado (brainstorm), aguardando revisão antes do plano
**Depende de:** Plano A (servidor) — já entregue (`f6a1e09..7b1df30`, api 87 verde + Odoo 39).
**Spec-pai (laço completo):** `docs/superpowers/specs/2026-07-21-fase5-config-loop-hardware-design.md`
**Alvo:** fechar o laço de configuração no **Hub real** (Raspberry Pi `hubsentinela`, `fitadigital@192.168.0.211`) lendo o **N4AIB16 real** (`/dev/ttyUSB0`) — grau M2 (hardware no laço).

---

## 1. Contexto e ponto de partida

O Plano A entregou o lado servidor: o Odoo publica a config Modbus de um hub (arquivo no SFTP + notify MQTT retido), rastreia presença, e fecha o drift ao receber `applied`. Falta o lado Hub: **receber o sinal, baixar a config, aplicá-la, recarregar o leitor, e reportar de volta** — em código real que roda no Pi.

### Estado do Hub hoje (código `hub/`, branch `fix/expanduser-caminho-chave` no Pi)
- `hub/main.py::executar(config, leitor, arquivo, publicador, agora_fn, parar, max_ciclos, enviador)` — **loop único single-thread** controlado por um `threading.Event` `parar`: lê (`leitor.ler_todos`), grava (`arquivo.registrar`), publica leitura (`publicador.publicar`), envia SFTP (`enviador.varrer`), dorme `config.intervalo_leitura_s`. `leitor.fechar()` já existe.
- `hub/config.py::carregar_config(caminho)` — parseia um `config.yaml` único (dataclasses `Config`/`Barramento`/`Dispositivo`/`Canal`).
- `hub/publicador_mqtt.py::PublicadorMqtt(mqtt_host, mqtt_port)` — publica **leituras** (data-plane).
- `hub/enviador_sftp.py` — `EnviadorSftp` (lógica) + `TransporteParamiko(host, port, username, ssh_key_path, remote_dir)` com `enviar()` (PUT). Transporte injetado via `Protocol`.
- `hub/leitor.py::Leitor(config)` — varredura RS-485 via `modbus_backend` (driver `n4aib16`).

### Hardware confirmado (lido ao vivo nesta sessão)
`N4AIB16` addr 1 em `/dev/ttyUSB0`: **CH1 = 18,4 mA**, **CH2 = 11,46 mA** (dois transmissores 4-20mA reais), CH3-15 = 0 mA, CH16 = 0 V. A prova E2E usa **CH1** (18,4 mA) como sinal real.

---

## 2. Escopo

### Dentro
1. **Cliente MQTT de control-plane** (novo, separado do `PublicadorMqtt`): presença (LWT + heartbeat retido), assina `notify`, publica `ack`/`applied`.
2. **config-agent**: consome `notify`, baixa por SFTP, funde com identidade local, escreve `config.yaml` efetivo, sinaliza reload, reporta `ack`/`applied`, persiste versão aplicada local.
3. **Reload in-loop** do leitor (mod `main.py::executar`).
4. **`baixar()` (GET)** no cliente SFTP existente (`TransporteParamiko`).
5. **Split identidade/operacional** (`identity.yaml` local + operacional baixado → `config.yaml` efetivo).
6. **Extensão do servidor** (repo Plano A): rastreador de presença lê `config_version_aplicada` do heartbeat retido → fecha o drift (rede de segurança).
7. **Prova E2E em hardware** (§9.3 da spec-pai) com CH1.

### Fora (v2 / fatias futuras)
- Comandos remotos imperativos (reboot/force-sync/diagnóstico).
- Assinatura da config (trilha tier-regulado).
- Config genérica além do N4AIB16 (scale/offset por registrador).
- Presença pré-publicação cabeada ao botão do Odoo (dívida do Plano A, UX; §4.1 passo 0 da spec-pai) — pode entrar aqui como item pequeno, ver §8.

---

## 3. Arquitetura (lado Hub)

```
                         broker MQTT (VPN → servidor)
   ┌──────────────────────────────────────────────────────────────┐
   │ status/hub/<code> (retido, LWT)   notify/hub/<code> (retido)  │
   │ ack/hub/<code>                    applied/hub/<code>          │
   └───────▲───────────────▲──────────────────┬───────────────────┘
           │ heartbeat      │ ack/applied       │ notify {version:N}
   ┌───────┴────────────────┴───────────────────▼──────────────────┐
   │ AgenteControle (novo cliente MQTT, hub/agente_config.py)       │
   │  - LWT=offline ; publica online+heartbeat retido               │
   │    {estado, heartbeat_ts, fw, config_version_aplicada}         │
   │  - on notify{N}: se N > aplicada_local →                       │
   │      publica ack → SFTP baixar(/config/<code>/config-vN.yaml)  │
   │      → funde c/ identity.yaml → escreve config.yaml efetivo    │
   │      → seta Event reconfigurar(N)                              │
   │      → aplica_local = N ; persiste estado ; publica applied    │
   └───────────────────────────────┬───────────────────────────────┘
                                    │ reconfigurar(N) [threading.Event]
   ┌────────────────────────────────▼──────────────────────────────┐
   │ loop leitor (main.py::executar) — ENTRE ciclos:                │
   │   if reconfigurar.is_set():                                    │
   │     leitor.fechar() ; cfg = carregar_config(config.yaml)       │
   │     leitor = Leitor(cfg) ; intervalo = cfg.intervalo_leitura_s │
   │     reconfigurar.clear()  ; (single owner da serial)           │
   │   ...lê N4AIB16 (CH1=18.4mA) → map → grava/publica/envia...    │
   └────────────────────────────────────────────────────────────────┘
```

**Concorrência:** o callback MQTT (thread do paho) só **sinaliza** (`reconfigurar` Event + guarda a versão). O loop leitor é o **único dono da porta serial** — ele fecha/reabre o `Leitor` entre ciclos. Sem lock, sem acesso concorrente à serial.

---

## 4. Componentes e interfaces (Hub)

### 4.1 `hub/identidade_config.py` (novo) — split + merge
- `carregar_identidade(caminho='identity.yaml') -> dict` — lê a identidade local: `hub_id`, `coletor_id`, `firmware_version`, `timezone_offset`, `caminho_chave`, `caminho_dados`, `mqtt: {host, port}`, `sftp: {host, port, username, ssh_key_path, remote_dir}`. **Nunca vem do servidor.**
- `fundir(identidade: dict, operacional: dict) -> dict` — sobrepõe o operacional (`intervalo_leitura_s`, `barramentos`) sobre a identidade, produzindo o dict completo do contrato `config.yaml`.
- `escrever_config_efetivo(merged: dict, caminho='config.yaml') -> None` — grava o yaml que `hub/config.py::carregar_config` já sabe ler (parser **não muda**).

### 4.2 `hub/receptor_config.py` (novo) — control-plane MQTT + agente
- `class AgenteControle`:
  - `__init__(self, hub_code, identidade, sftp_baixar, reconfigurar_event, estado_path='estado_config.json')`
  - **MQTT (cliente próprio, paho):** `connect_async`; LWT retido `sentinela/status/hub/<code>` = `{estado:'offline'}`; `on_connect` → publica `{estado:'online', heartbeat_ts, fw, config_version_aplicada}` retido **e** re-assina `sentinela/config/notify/hub/<code>` (resubscribe-safe); heartbeat periódico (thread/timer) reatualiza o retido.
  - **on notify** `{version:N}`: se `N > self.aplicada`: publica `ack {version:N, recebido_em}`; `arquivo = sftp_baixar(f'/config/{code}/config-v{N}.yaml')`; `operacional = yaml.safe_load(arquivo)`; `merged = fundir(identidade, operacional)`; `escrever_config_efetivo(merged)`; `self.aplicada = N`; persiste `estado_config.json`; `reconfigurar_event.set()` (com a versão via atributo); publica `applied {version:N, aplicado_em, status:'ok'}`. Em erro (download/parse/yaml inválido): publica `applied {version:N, status:'erro', detalhe}` e **não** avança `self.aplicada`.
  - `aplicado_em` e `recebido_em` em ISO **com `+00:00`** (NÃO `Z` — o subscriber do servidor usa `datetime.fromisoformat` no Python 3.9, que rejeita `Z`).
  - Estado local `estado_config.json`: `{config_version_aplicada}` — carregado no boot (default 0), para comparar com o notify e reportar no heartbeat.

### 4.3 `hub/enviador_sftp.py` (modificar) — adicionar GET
- `Transporte` (Protocol) ganha `baixar(nome_remoto: str, caminho_local: str) -> None` junto de `enviar`.
- `TransporteParamiko.baixar(...)` — GET via o **mesmo** cliente/conexão SFTP contra o **mesmo SFTPGo** (put+get, um servidor). Reusa `identidade_ssh.py`. (O caminho `/config/...` é absoluto no SFTPGo; a conta do hub tem leitura em `/config/<code>` e escrita em `/uploads`.)

### 4.4 `hub/main.py` (modificar) — reload in-loop
- `executar(...)` recebe também `reconfigurar` (Event) e uma função `recarregar_fn` (ou o próprio agente). Entre ciclos (após o `parar.wait`, antes do próximo `ler_todos`):
  ```python
  if reconfigurar.is_set():
      leitor.fechar()
      cfg = config_mod.carregar_config(caminho_config)
      leitor = Leitor(cfg)
      intervalo = cfg.intervalo_leitura_s
      reconfigurar.clear()
  ```
- `main()` monta o `AgenteControle` (com `identidade`, `TransporteParamiko.baixar`, o Event), inicia-o (conecta ao broker de control), e passa o Event ao `executar`. O `PublicadorMqtt` das leituras segue intocado.

---

## 5. Extensão no servidor (repo Plano A) — heartbeat fecha o drift

**Motivo:** `applied` é one-shot não-retido; se a API estiver fora quando o Hub publica, perde-se. O heartbeat retido carrega `config_version_aplicada`, então o servidor fecha o drift pela batida seguinte mesmo que o `applied` se perca.

- `api/presenca.py::Rastreador.atualizar` — ao receber status com `config_version_aplicada`, se maior que o gravado no Odoo, escreve `config_version_aplicada` + `config_version_reportada_em=heartbeat_ts` no hub (via XML-RPC, reusando a lógica de datetime de `api/config_report.py`). Idempotente (só grava se avança).
- Alternativa de fatoração: extrair a escrita-no-Odoo de `config_report.py` para uma função compartilhada `registrar_versao_aplicada(cliente, hub_code, versao, quando)` usada pelo report **e** pela presença. Evita duplicar a lógica.
- `applied` one-shot continua (caminho rápido). O heartbeat é a rede de segurança.

---

## 6. Contratos (deltas sobre a spec-pai §5)

- `status/hub/<code>` (retido, LWT) passa a incluir `config_version_aplicada`:
  `{estado:'online'|'offline', heartbeat_ts, fw, config_version_aplicada}`.
- `ack/hub/<code>`: `{version:N, recebido_em}` (`+00:00`).
- `applied/hub/<code>`: `{version:N, aplicado_em, status:'ok'|'erro', detalhe?}` (`+00:00`).
- Arquivo baixado: `/config/<code>/config-v<N>.yaml` (operacional; contrato §5.3 da spec-pai).
- `identity.yaml` (local, novo): identidade+conectividade; nunca trafega.

---

## 7. Prova E2E em hardware (§9.3 concreta)

Roteiro (runbook novo `docs/runbooks/`, disparado do servidor + Pi):
1. **Provisionar no Odoo** o hub `HUB-<real>` + bus (`/dev/ttyUSB0`, 9600, N, 1) + device N4AIB16 (addr 1) + 1 sensor mapeado a **CH1** com `map` [4,20]→[faixa escolhida] (ex. temperatura -50..150 → 18,4mA ≈ 133,75). Publicar (botão Odoo) → versão desejada N.
2. **Pi:** o `AgenteControle` recebe notify → baixa `config-vN.yaml` → funde → escreve `config.yaml` → sinaliza reload → publica `ack` + `applied`.
3. **Servidor:** `applied` (ou o heartbeat) fecha o drift no Odoo (desejada==aplicada).
4. **Pi:** o loop recarrega o `Leitor` e lê o N4AIB16 real (CH1=18,4mA) → aplica `map` → valor de engenharia → arquivo assinado → transporte SFTP → ingestão → Timescale/Odoo.
5. **Dashboard:** mostra o valor real de CH1 ao vivo + histórico.
- **Critério de sucesso:** drift fecha **e** o valor real de CH1 (engenharia) aparece no dashboard, provando que a config publicada tomou efeito no hardware.

---

## 8. Testes

### 8.1 Unit (Pi, sem hardware — lógica pura/mockável)
- `identidade_config`: `fundir` sobrepõe operacional sem vazar identidade; `escrever_config_efetivo` produz yaml válido p/ `carregar_config`.
- `AgenteControle`: notify N>aplicada → chama `sftp_baixar` + funde + seta Event + publica `applied`; N≤aplicada → no-op; erro de download/parse → `applied status:'erro'` sem avançar; heartbeat inclui `config_version_aplicada`; `aplicado_em` sem `Z`. (SFTP e MQTT injetados/mockados.)
- `estado_config.json`: persistência e reload da versão aplicada.
- `TransporteParamiko.baixar`: GET real contra o SFTPGo (como o teste da Task 5, com conta de serviço).
- Reload in-loop (`executar`): com um Event pré-setado e config trocada, o loop fecha/reabre o `Leitor` (mock de `Leitor` conta fechar/reconstruir).
- Servidor (§5): heartbeat com `config_version_aplicada` maior → fecha drift no Odoo (teste MQTT publicando status retido).

### 8.2 E2E real (Pi + N4AIB16)
- O roteiro §7 completo, executável, com CH1. Critério de sucesso do §7.

---

## 9. Deploy e coordenação

- **Deploy no Pi:** o Pi está na branch `fix/expanduser-caminho-chave`, sem o código novo do `hub/`. Antes do E2E, sincronizar o `hub/` (merge/rebase da branch de trabalho do Plano B, ou cherry-pick). Documentar no runbook. O Pi só precisa do `hub/` (não do lado servidor).
- **`identity.yaml` no Pi:** criar a partir do `config.example.yaml` atual, mantendo só identidade+conectividade (remover `intervalo_leitura_s`/`barramentos`, que passam a vir do servidor).
- **Broker/SFTP na VPN:** em produção o Pi alcança o servidor por `10.8.0.1` (OpenVPN); em teste local, pela rede LAN (192.168.0.x). O `identity.yaml` aponta o host certo por ambiente.
- **Datetime `+00:00`:** obrigatório em `ack`/`applied` (subscriber py3.9). Se um dia o servidor subir p/ py3.11+, `Z` passa a ser aceito, mas o Hub segue emitindo `+00:00` por compatibilidade.

---

## 10. Riscos e decisões abertas

- **Reabertura da serial no reload:** `leitor.fechar()` deve liberar `/dev/ttyUSB0` antes do novo `Leitor` abrir; se o driver não fechar limpo, o reabrir falha. Testar o ciclo fechar→reabrir explicitamente (§8.1).
- **Sensor/área do CH1 no Odoo:** o E2E precisa de um sensor provisionado mapeado a CH1 com `map` plausível. A faixa de engenharia é arbitrária p/ a prova (não há transmissor calibrado documentado); o valor exibido é derivado de 18,4mA pela `map` escolhida — prova o caminho, não uma grandeza física validada.
- **Heartbeat vs applied (ordem):** se o heartbeat retido chegar ANTES do `applied` no boot do servidor, o drift já fecha pelo heartbeat — comportamento desejado, sem corrida nociva (ambos idempotentes, só avançam).
- **Extensão do servidor (§5) precisa ir junto:** sem ela, o heartbeat-safety-net não é consumido e a robustez prometida não existe — não é opcional dentro do Plano B.

---

## 11. Ordem sugerida de implementação (para o plano)
1. `TransporteParamiko.baixar()` (GET) + teste SFTP.
2. `identidade_config` (split/merge/escrever) + testes.
3. `AgenteControle` (MQTT control + notify→download→apply→report + estado local) + testes mockados.
4. Reload in-loop no `main.py::executar` + teste.
5. Extensão do servidor (§5, heartbeat fecha drift) + teste.
6. Deploy no Pi + `identity.yaml` + runbook E2E; rodar a prova §7 com CH1.
