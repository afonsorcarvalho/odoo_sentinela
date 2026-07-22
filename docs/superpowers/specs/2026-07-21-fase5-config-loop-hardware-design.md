# Fase 5 — Control plane: laço de configuração Odoo → Hub real (SFTP + MQTT)

**Data:** 2026-07-21
**Status:** design aprovado (brainstorm), aguardando revisão do spec antes do plano
**Marco:** primeira fatia da Fase 5 (control plane, §10.1 das diretrizes). Testada em **hardware real** (Raspberry Pi + N4AIB16), o que aproxima grau M2 (hardware no laço), não só M1.

---

## 1. Contexto e motivação

O sistema tem **duas fontes de verdade complementares** (diretriz §10.1):
- **Dado medido** (leituras/alarmes) → fonte de verdade no **dispositivo** (mede e assina). Já provado ponta-a-ponta no M1.
- **Configuração** (como o dispositivo deve operar) → fonte de verdade no **servidor/Odoo**. É o que esta fatia constrói.

Hoje o Hub lê um `config.yaml` **estático local** (`hub/config.py` → `hub/leitor.py`). Não há como o servidor mudar a operação de um Hub remotamente, nem visibilidade de qual config cada Hub está rodando. Esta fatia fecha o **laço de configuração**: publicar do Odoo, o Hub aplicar, e o Odoo enxergar o estado real (drift).

### Realidade de teste (novo)
Há um **Hub real na rede**: Raspberry Pi `hubsentinela` (`fitadigital@192.168.0.211`), repo em `~/odoo_sentinela` (branch `fix/expanduser-caminho-chave`), venv em `~/odoo_sentinela/.venv`. Conectado por USB-RS485 (`/dev/ttyUSB0`, chip CH340) a um **N4AIB16 real** (coletor analógico 4-20mA). A lib `modbus-connector` (vendored em `hub/vendor/modbus-connector`) tem o driver `n4aib16` que entrega **mA** (raw/100). O `hub/` já tem: `config.py` (parse yaml), `leitor.py` (varredura RS-485), `publicador_mqtt.py`, `enviador_sftp.py` (upload), `assinador.py`, `main.py`.

Consequência: **não simulamos o Hub**. O laço fecha no Pi real lendo o N4AIB16 real.

---

## 2. Escopo

### Dentro (laço fechado completo)
1. **Broker MQTT** (Mosquitto) no stack do servidor.
2. **Presença/liveness** do Hub (LWT + heartbeat retido); Odoo avisa se o Hub está morto/stale antes de publicar.
3. **Publicação**: botão "Publicar configuração" no Odoo → serializa a árvore Modbus do hub → grava arquivo no diretório SFTP do hub → incrementa `config_version_desejada` → publica sinal MQTT **retido** com a versão → registra no chatter.
4. **Aplicação no Hub** (código real `hub/`): config-agent recebe o sinal (ou pega o retido no reconnect), baixa o arquivo por **SFTP**, funde com a identidade local, aplica e recarrega o `leitor`.
5. **Report/handshake**: Hub publica **ack** (recebido) e **applied** (aplicado) no broker; um subscriber no servidor grava `config_version_aplicada` + `reportada_em` no Odoo → **drift fecha**.
6. **Prova em hardware real**: após aplicar, o `leitor` lê o N4AIB16 com a config nova → leitura assinada → chega ao servidor → dashboard. Prova o plano de config E o de dado num hardware só.

### Fora (próximas fatias / v2)
- **Comandos remotos** imperativos (reboot / force-sync / diagnóstico) — 2ª fatia da Fase 5 (tópico não-retido + id/ack/dedup).
- **Assinatura da config** — v1 confia no canal (§10.1); endurecimento é requisito da trilha "tier regulado" (21 CFR Part 11), não desta fatia.
- **Multi-hub em paralelo** e políticas de rollout — a fatia trata 1 hub por publicação; o design não impede N, mas os testes cobrem 1.
- **UI Odoo rica de drift** (dashboards de frota) — a fatia entrega campo/indicador no form do hub, não uma tela dedicada.

---

## 3. Arquitetura e fluxo

```
SERVIDOR (Docker)                               HUB REAL (Pi 192.168.0.211, código hub/)
┌───────────────────────────┐                   ┌─────────────────────────────────────────┐
│ Odoo  (hub form)          │                   │ config-agent  (NOVO)                      │
│  botão "Publicar config"  │                   │  presença: LWT + heartbeat (publicador_mqtt)│
│   0. checa presença ──────┼──(API lê broker)──│                                           │
│      morto/stale→avisa     │                   │                                           │
│   1. version++ (desejada)  │      sinal MQTT   │  escuta notify (retido → nada perde       │
│   2. chama API ───────────┐│  ┌──notify(N)────▶│  offline)                                 │
│   3. chatter "v<N>"        ││  │                │   ack(N) ─────────┐                       │
└───────────────────────────┘│  │                │   SFTP download ◄──┼── config-v<N>.yaml   │
                             ▼│  │                │   funde c/ identidade local              │
┌───────────────────────────┐│  │                │   aplica + recarrega leitor.py           │
│ API FastAPI (NOVO)        ││  │                │   applied(N) ──────┐                      │
│  POST /internal/.../publ. ◄┘  │                └────────────────────┼──────────────────────┘
│   serializa Odoo→yaml       │ │                                     │
│   grava SFTP + publica ─────┘ │                                     │
│  subscriber: ack/applied/status ◄───────────────────────────────────┘
│   grava aplicada + reportada_em no Odoo → drift zera                 │
└───────────────────────────┘
        ▲                                                              │
        │ SFTPGo (já existe)  ── /config/<hub_code>/config-v<N>.yaml ──┘
        │
[BÔNUS real] leitor lê N4AIB16 (ttyUSB0) com a config nova → leitura assinada → servidor → dashboard
```

**Princípios:**
- **Fonte da versão = Odoo** (`config_version_desejada`). API e Hub só carimbam/reportam.
- **Contrato do arquivo = `config.yaml` que o `hub/config.py` já parseia** — subconjunto operacional (ver §5.3). Não se inventa formato novo.
- **Notify MQTT retido com a versão** → Hub offline pega no reconnect; a checagem de presença é **aviso de UX**, não requisito de correção.
- **Identidade/conectividade nunca trafega** (§6): o servidor empurra só o operacional; o Hub funde com seu `identity` local.

---

## 4. Componentes e interfaces

### 4.1 Servidor

**Mosquitto (novo serviço `docker-compose`)**
- Broker interno, não exposto publicamente (rede Docker; em produção só via OpenVPN — fora desta fatia).
- Volume para persistir mensagens retidas (status + notify).
- Auth mínima na fatia (usuário/senha simples no broker); TLS/ACL por tópico = endurecimento futuro.

**Serializador (novo módulo na API)**
- `serializar_config_hub(cliente, hub_code) -> dict`: lê a árvore Modbus do hub no Odoo (`sensor_monitor.hub` → `rs485.bus` → `modbus.device` → `modbus.profile.register` + sensores com `modbus_register_id`) e produz o **subconjunto operacional** do contrato `config.yaml` (§5.3).
- Puro/testável: recebe um cliente Odoo, devolve dict; a serialização YAML e o I/O ficam no publisher.

**Publisher/Subscriber MQTT (novo na API)**
- Cliente paho conectado ao Mosquitto.
- Rota interna `POST /internal/hub/{hub_code}/publicar-config` (autenticada por **secret interno**, não o JWT de usuário — é chamada serviço-a-serviço vinda do Odoo): serializa → grava `config-v<N>.yaml` no SFTP do hub → publica `notify` retido `{version:N}` → devolve `{version:N}`.
- **Endpoint de presença** `GET /internal/hub/{hub_code}/status`: devolve o estado corrente do hub a partir do que o subscriber viu no tópico `status` (online/offline + idade do heartbeat). Usado pelo botão do Odoo para a checagem pré-publicação.
- **Subscriber de report**: assina `sentinela/config/ack/#`, `sentinela/config/applied/#`, `sentinela/status/#`; ao receber `applied`, grava `config_version_aplicada` + `config_version_reportada_em` no Odoo via XML-RPC; mantém em memória o mapa de presença/última-versão-vista por hub. Roda como tarefa de startup da API (padrão do `live_listener` já existente).

**Odoo (novo)**
- Botão de ação **"Publicar configuração"** no form do `sensor_monitor.hub`: (1) `config_version_desejada += 1`; (2) `requests.post` no endpoint interno da API (com o secret); se a presença indicar hub morto/stale, exibe **aviso** (notificação Odoo) mas permite prosseguir; (3) `message_post` no chatter ("config v<N> publicada"). URL da API e secret via parâmetros de sistema (`ir.config_parameter`).
- Campo computado **`config_em_drift`** (`config_version_desejada != config_version_aplicada`) + exibição de `config_version_aplicada` e `config_version_reportada_em` no form → visibilidade do drift.

### 4.2 Hub (Pi, código real `hub/`, reusa muito)

**config-agent (novo módulo `hub/config_agent.py` + entrada no `main.py`)**
- **Presença**: conecta ao broker com **LWT** retido em `sentinela/status/hub/<code>` = `{estado:"offline"}`; ao conectar publica `{estado:"online", heartbeat_ts, fw}` retido; heartbeat periódico atualiza `heartbeat_ts`. Reusa `publicador_mqtt.py`.
- **Escuta** `sentinela/config/notify/hub/<code>` (retido): ao ver `version > versão_local_aplicada`, dispara o ciclo de aplicação.
- **SFTP download (novo, `hub/receptor_sftp.py`)**: espelha `enviador_sftp.py` mas baixa `/config/<hub_code>/config-v<N>.yaml`. Reusa `identidade_ssh.py` (chave já existente).
- **Aplicação**: funde o operacional recebido com o `identity` local (§6) → grava o `config.yaml` efetivo → recarrega o `leitor` (novo ciclo de leitura passa a usar a config nova). Idempotente: reaplicar a mesma versão não faz nada.
- **Report**: publica `ack` ao receber o notify e `applied` ao concluir a aplicação (§5.1).

---

## 5. Contratos

### 5.1 Tópicos MQTT
| Tópico | Retido | Publicador | Payload |
|---|---|---|---|
| `sentinela/status/hub/<code>` | sim (+ LWT) | Hub | `{estado: "online"\|"offline", heartbeat_ts, fw}` |
| `sentinela/config/notify/hub/<code>` | **sim** | Servidor | `{version: N, publicado_em}` |
| `sentinela/config/ack/hub/<code>` | não | Hub | `{version: N, recebido_em}` |
| `sentinela/config/applied/hub/<code>` | não | Hub | `{version: N, aplicado_em, status: "ok"\|"erro", detalhe?}` |

- `<code>` = `hub.hub_code` do Odoo (identificador estável do hub).
- `applied` com `status:"erro"` (ex.: yaml inválido, SFTP falhou) **não** fecha o drift e é registrado no chatter para diagnóstico.

### 5.2 Arquivo SFTP
- Caminho: `/config/<hub_code>/config-v<N>.yaml` no SFTPGo. Diretório por hub, com acesso de leitura para o usuário SFTP daquele hub (config do SFTPGo).
- Mantém as N versões (auditoria/rollback manual); o Hub sempre busca a versão que o notify indicou.

### 5.3 Subconjunto operacional do `config.yaml` (o que o servidor empurra)
Empurra **só o operacional**; o Hub funde com a identidade local (§6). Empurrado:
```yaml
version: 7                     # = config_version_desejada
intervalo_leitura_s: 5
barramentos:
  - porta: /dev/ttyUSB0        # serial_port do rs485.bus
    baud: 9600                 # baud_rate
    paridade: N                # parity
    stop_bits: 1               # stop_bits
    dispositivos:
      - endereco: 1            # modbus.device.slave_address
        driver: n4aib16        # (ver §7 — reconciliação)
        canais:
          - ch: 1              # canal físico (ver §7)
            sensor_id: SNR-EXP-TEMP-01   # sensor.sensor_code
            area_id: AREA-EXPURGO        # área do sensor
            tipo_medida: temperatura     # measurement_type
            unidade: C
            protocolo_origem: 4-20ma
            map: {in: [4, 20], out: [-50, 150]}   # calibração mA→engenharia (ver §7)
            filtro: {tipo: ewma, alpha: 0.3}       # opcional (ver §7)
```
**Não** empurrado (fica no `identity.yaml` local do Hub): `hub_id`, `coletor_id`, `firmware_version`, `caminho_chave`, `caminho_dados`, bloco `sftp:` (host/porta/usuário/chave), `mqtt:` (host/porta). O Hub sobrepõe o operacional sobre o identity para montar o `config.yaml` efetivo que o `hub/config.py` carrega.

---

## 6. Fronteira de configuração (§10.1)

- **Local (semeado uma vez, nunca remoto)**: identidade (`hub_id`, `coletor_id`, chaves ECDSA/SSH) e conectividade (creds SFTP/MQTT, host do broker/servidor). Problema ovo/galinha: precisa de rede para receber config, então a config de rede é semeada localmente. Vive num `identity.yaml` local no Pi.
- **Servidor gerencia**: `intervalo_leitura_s` + toda a árvore `barramentos` (parâmetros de bus, dispositivos, canais, calibração `map`, `filtro`). "Toda a configuração Modbus já precisa descer pro Hub de qualquer forma para ele ler o barramento" (§10.1).

---

## 7. Reconciliação do modelo de dados Odoo ↔ contrato do Hub

**Impedância descoberta:** o `config.yaml`/`hub/config.py` é orientado a **canal analógico 4-20mA do N4AIB16** (`ch`, `map:{in,out}` mA→engenharia, `filtro`, `driver`), enquanto o `sensor_monitor.modbus.profile.register` do Odoo é **Modbus genérico** (`function_code`, `register_address`, `scale`, `offset`, `data_type`, `byte_order`). O driver `n4aib16` já entrega **mA** (raw/100), então a calibração relevante é **mA→engenharia** (nível do sensor), que o modelo genérico de registrador **não** expressa.

**Decisão:** estender o modelo Odoo com o mínimo para o Hub ler de fato, sem quebrar o modelo genérico existente. Campos novos:

| Campo yaml | Onde no Odoo (novo, salvo indicação) | Notas |
|---|---|---|
| `barramentos[].porta` | `rs485.bus.serial_port` (existe) | |
| `barramentos[].baud/paridade/stop_bits` | `rs485.bus.baud_rate/parity/stop_bits` (existem) | |
| `dispositivos[].endereco` | `modbus.device.slave_address` (existe) | |
| `dispositivos[].driver` | **novo** `modbus.profile.driver` (Selection; v1: `n4aib16`) | driver deriva do perfil |
| `canais[].ch` | **novo** `sensor.modbus_channel` (Integer) no `sensor_rs485_ext` | canal físico 1-15 do N4AIB16 |
| `canais[].sensor_id` | `sensor.sensor_code` (existe) | |
| `canais[].area_id` | área do sensor (existe) | |
| `canais[].tipo_medida` | `measurement_type` do sensor/registrador (existe) | |
| `canais[].unidade` | `sensor`/`register.unidade` (existe) | |
| `canais[].protocolo_origem` | `sensor.protocolo_origem` (existe) | fixo `4-20ma` p/ N4AIB16 |
| `canais[].map.in/out` | **novos** `sensor.ma_in_min/ma_in_max` + `sensor.eng_out_min/eng_out_max` (Floats) | calibração 4-20mA→engenharia |
| `canais[].filtro` | **novos** `sensor.filtro_tipo` (Selection: none/ewma) + `sensor.filtro_alpha` (Float) | opcional |

- Os campos genéricos existentes do registrador (`function_code`, `register_address`, `scale`, `offset`, `data_type`, `byte_order`) **permanecem** para dispositivos Modbus genéricos futuros; para o N4AIB16 o driver os dispensa (entrega mA direto). O serializador escolhe o caminho pelo `driver` do perfil.
- Escopo desta fatia: cobrir o **N4AIB16** de ponta a ponta (é o hardware de teste). O caminho genérico (scale/offset por registrador) fica modelado mas não exercido aqui.

---

## 8. Segurança e fronteiras

- **Sem assinatura na config (v1)** — confia no canal: SFTP já é seguro (SFTPGo + chave SSH; em produção dentro da OpenVPN), MQTT é interno. **Assimetria consciente** com o caminho do dado (que é assinado): um broker/MITM comprometido poderia, em tese, empurrar config maliciosa (ex.: afrouxar faixa para mascarar violação). Registrado como requisito da trilha "tier regulado", não desta fatia.
- **Secret Odoo→API**: a rota interna da API é autenticada por secret compartilhado (`ir.config_parameter` no Odoo, env na API), separado do JWT de usuário.
- **Trilha de auditoria**: toda publicação e todo `applied` (ok/erro) registrados no chatter do hub no Odoo.

---

## 9. Testes (hardware real, sem simular o Hub)

### 9.1 Unitários (servidor, sem hardware)
- `serializar_config_hub`: de uma árvore Modbus provisionada no Odoo (fixture com 1 bus + 1 N4AIB16 + canais) → dict yaml operacional correto (campos, `map`, `filtro`, `driver`).
- Merge no Hub (`config_agent`): operacional + identity local → `config.yaml` efetivo válido para `hub/config.py`.
- Presença: parsing de status/heartbeat; classificação online/offline/stale por idade do heartbeat.

### 9.2 Integração servidor (Mosquitto no stack de teste)
- Publicar via endpoint → assinante de teste vê `notify` retido com a versão certa; arquivo `config-v<N>.yaml` aparece no SFTP.
- Subscriber de report: publicar `applied{version:N}` → `config_version_aplicada`/`reportada_em` gravados no Odoo; `config_em_drift` zera.

### 9.3 E2E em hardware real (Pi + N4AIB16) — a prova da fatia
Roteiro (documentado em `docs/runbooks/`, executável a partir do servidor):
1. Servidor: publicar config (intervalo=5s, 1 canal do N4AIB16 mapeado).
2. Pi: config-agent baixa por SFTP, aplica, recarrega o leitor; `applied` chega → drift zera no Odoo.
3. Pi: `leitor` lê o N4AIB16 real (`/dev/ttyUSB0`) com a config nova → gera arquivo assinado → transporte → ingestão → Timescale/Odoo.
4. Dashboard mostra a leitura real ao vivo do sensor mapeado.
- Critério de sucesso: drift fecha **e** a leitura real do canal configurado aparece no dashboard, provando que a config publicada tomou efeito no hardware.

---

## 10. Riscos e decisões abertas

- **Extensão do modelo Odoo (§7)** muda o schema do addon (novos campos em `sensor`, `modbus.profile`). Reversível/aditivo, mas é a decisão de maior peso — confirmar na revisão do spec.
- **Recarga do `leitor` no Hub**: aplicar config em runtime exige reabrir portas serial/dispositivos com segurança (fechar o loop anterior antes). Detalhe de implementação do config-agent; o `leitor.fechar()` já existe.
- **`porta` serial no config empurrado**: `/dev/ttyUSB0` é específico do Pi (enumeração USB). Na fatia é estável; a médio prazo pode migrar para `by-id`. Fica como está aqui, anotado.
- **Idade de heartbeat p/ "stale"**: valor a definir no plano (ex.: 3× o intervalo de heartbeat).
- **Rollback**: as N versões ficam no SFTP; rollback = publicar uma versão anterior. Automação de rollback fora de escopo.

---

## 11. Próximas fatias (depois desta)
- Comandos remotos imperativos (reboot/force-sync/diagnóstico) — tópico não-retido + id/ack/dedup.
- Config genérica além do N4AIB16 (exercitar scale/offset/registradores).
- Endurecimento tier-regulado: assinatura da config no servidor + verificação no Hub antes de aplicar.
- UI de frota (drift de múltiplos hubs) e políticas de rollout.
