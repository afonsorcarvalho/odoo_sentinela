# Spec técnica — Modelo de dados no Odoo

> Documento de especificação para implementação. Complementa `diretrizes_projeto.md` (seção 9 — Backend). Escrito para ser entregue a uma sessão de implementação (Claude no WSL2) construir o módulo Odoo diretamente a partir daqui.

**Escopo deste documento**: só a camada cadastral/relacional (Odoo/PostgreSQL). **Não inclui** as leituras brutas de sensor (timestamp + valor), que ficam no TimescaleDB, separado — ver seção 10 (Fora de escopo) para o porquê.

---

## 1. Correção de modelagem em relação à diretriz original

A diretriz (`diretrizes_projeto.md`, seção 9) menciona "multi-tenancy nativa (`res.company`)". Ao desenhar o modelo de dados de verdade, isso merece correção: `res.company` no Odoo representa uma **entidade legal que é dona da própria instância** (sua empresa, ou filiais/subsidiárias que você opera) — é o mecanismo certo para holdings com múltiplas razões sociais internas, não para modelar **clientes externos** de um SaaS.

**Recomendação corrigida**: cada cliente (hospital/empresa contratante) é um `res.partner` (contato do tipo cliente), padrão do Odoo para isso. O isolamento multi-tenant entre clientes é feito por **regras de registro (`ir.rule`)** filtrando pela cadeia `site_id → cliente_id (partner_id)`, não pela troca de `res.company`. Isso escala melhor para centenas de clientes externos e é o padrão idiomático do Odoo para esse cenário (multi-company é para outra coisa).

## 2. Hierarquia geral

```
res.partner (Cliente)
    │
    └── sensor_monitor.site (Site/Unidade)
            │
            ├── sensor_monitor.area (Área/Sala — ex: Expurgo, Preparo)
            │
            └── sensor_monitor.hub (Hub — Raspberry Pi)
                    │
                    └── sensor_monitor.coletor (Coletor — ESP32 ou "embutido no Hub" p/ RS-485)
                            │
                            └── sensor_monitor.sensor (Sensor físico)
                                    │
                                    ├── vínculo atual: sensor_monitor.area (onde está hoje)
                                    └── sensor_monitor.alarm.threshold (limiares configurados)
                                            │
                                            └── sensor_monitor.alarm.event (ocorrências)

sensor_monitor.file.ledger — registro de recebimento de arquivo por coletor/dia (independente da hierarquia acima, referencia coletor_id + hub_id)

Ramo RS-485/Modbus (só quando protocolo_origem = rs485):
sensor_monitor.rs485.bus (barramento, pertence a um hub)
        │
        └── sensor_monitor.modbus.device (dispositivo físico: bus + endereço de escravo + perfil)
                    │  referencia →  sensor_monitor.modbus.profile (catálogo, global)
                    │                        └── .register (linhas do mapa de registradores)
                    └── sensor_monitor.sensor (um por registrador/medição do dispositivo)
```

**Nota importante sobre `area_id` no Sensor**: o campo `area_id` no modelo `sensor.sensor` representa a atribuição **atual/vigente** (usada para configuração de alarme e exibição no frontend). Ele **não** é a fonte de verdade histórica — cada leitura já grava seu próprio `area_id` no momento da medição (arquivo `.txt` assinado, ver diretriz seção 7), justamente para não depender retroativamente do cadastro. Se um sensor for realocado de sala, só a atribuição atual muda aqui; o histórico já registrado permanece intacto onde está (Timescale/arquivo).

## 3. Módulo proposto

- **Nome técnico do módulo**: `sensor_monitor` (ajustar se já houver convenção de nomenclatura da organização).
- **Estrutura de pastas sugerida**:
```
sensor_monitor/
├── __manifest__.py
├── models/
│   ├── __init__.py
│   ├── site.py
│   ├── area.py
│   ├── area_category.py
│   ├── hub.py
│   ├── coletor.py
│   ├── sensor.py
│   ├── measurement_type.py
│   ├── alarm_threshold.py
│   ├── alarm_event.py
│   ├── file_ledger.py
│   ├── rs485_bus.py
│   ├── modbus_profile.py        (modbus.profile + modbus.profile.register)
│   └── modbus_device.py
├── security/
│   ├── ir.model.access.csv
│   └── security_rules.xml   (ir.rule multi-tenant + grupos)
├── data/
│   ├── measurement_type_data.xml
│   ├── area_category_data.xml
│   └── rdc15_default_thresholds_data.xml   (dados de referência do vertical CME)
└── views/
    └── (uma view por modelo — form/tree/kanban conforme necessidade de UI administrativa)
```

## 4. Especificação dos modelos

### 4.1 `sensor_monitor.site`
Unidade física de um cliente (ex: "Hospital X — CME Central").

| Campo | Tipo | Descrição |
|---|---|---|
| `name` | Char | Nome do site |
| `partner_id` | Many2one → `res.partner` | Cliente dono do site (obrigatório) |
| `site_code` | Char | Identificador estável usado também no particionamento do TimescaleDB (`site_id`) — único |
| `endereco` | Char/Text | Endereço físico |
| `timezone` | Char | Timezone do site (ex: `America/Sao_Paulo`) — usado para interpretar timestamps dos arquivos |
| `vertical` | Selection (`cme_hospitalar`, `industrial_generico`, ...) | Vertical de negócio do site — mantém a plataforma genérica (seção 1 da diretriz) |
| `ativo` | Boolean | Site ativo/inativo |
| `retention_mode` | Selection (`indefinida`, `expurgar_apos`) | Política pós-5-anos, **configurável por contrato** (ver diretriz 9.3). Herda de um default (do `res.partner`/contrato) se não setado no site. |
| `retention_years` | Integer | Anos a reter quando `retention_mode = expurgar_apos`. **Constraint: ≥ 5** (piso legal RDC 15 — nenhuma config pode ir abaixo). |
| `lifecycle_status` | Selection (`ativo`, `offboarding`, `arquivado`, `expurgado`) | Ciclo de vida para offboarding (ver diretriz 9.3) |
| `offboarding_data` | Date | Data de início do offboarding |
| `export_entregue_em` | Date | Quando o export completo (arquivos assinados + relatórios) foi entregue ao cliente |

**Nota de defesa em profundidade**: o piso de 5 anos é garantido de forma independente pelo **object-lock no object storage** (camada de armazenamento), não só por estas configs de aplicação — mesmo um erro de config aqui não consegue apagar um arquivo antes do prazo legal.

### 4.2 `sensor_monitor.area.category` (referência/lookup)
Catálogo extensível de tipos de área — evita hardcode de "expurgo/preparo/esterilização/arsenal" no código, permitindo novos verticais sem alteração de schema.

| Campo | Tipo | Descrição |
|---|---|---|
| `name` | Char | Ex: "Expurgo", "Preparo/Esterilização", "Arsenal", "Câmara fria" (vertical industrial futuro) |
| `code` | Char | Código técnico estável (ex: `EXPURGO`) |
| `vertical` | Selection | A qual vertical essa categoria pertence |

### 4.3 `sensor_monitor.area`
Sala/área física dentro de um site.

| Campo | Tipo | Descrição |
|---|---|---|
| `name` | Char | Nome da área |
| `site_id` | Many2one → `sensor_monitor.site` | Obrigatório |
| `area_category_id` | Many2one → `sensor_monitor.area.category` | Obrigatório |
| `area_code` | Char | Identificador estável (usado como `area_id` nas leituras) — único por site |

### 4.4 `sensor_monitor.hub`
O dispositivo Raspberry Pi.

| Campo | Tipo | Descrição |
|---|---|---|
| `name` | Char | Nome/apelido do hub |
| `site_id` | Many2one → `sensor_monitor.site` | Obrigatório |
| `hub_code` | Char | Identificador estável (`hub_id` usado nos arquivos) — único |
| `modelo_hardware` | Selection | `raspberry_pi_3b` (único valor hoje, ver diretriz seção 6) |
| `openvpn_cert_fingerprint` | Char | Fingerprint do certificado OpenVPN do hub |
| `possui_secure_element` | Boolean | Verdadeiro (ATECC608, usado para assinar arquivos RS-485 gerados pelo próprio hub) |
| `secure_element_pubkey_fingerprint` | Char | Chave pública do secure element do hub — usada para validar arquivos RS-485 que o hub mesmo assina |
| `firmware_version` | Char | Versão do software rodando no hub |
| `status` | Selection (`online`, `offline`, `manutencao`) | Calculado/atualizado por heartbeat (via MQTT ou última sincronização recebida) |
| `ultimo_contato` | Datetime | Último heartbeat/sincronização recebida |
| `config_version_desejada` | Integer | Versão de config atual publicada pelo servidor (control plane, ver diretriz 10.1) |
| `config_version_aplicada` | Integer | Última versão que o hub confirmou estar rodando (reportada via MQTT) — se diverge da desejada, há *drift* |
| `config_version_reportada_em` | Datetime | Quando o hub reportou a versão aplicada |

### 4.5 `sensor_monitor.coletor`
ESP32 físico OU o "coletor lógico embutido" representando a função de leitura RS-485 do próprio Hub (ver diretriz seções 5/6).

| Campo | Tipo | Descrição |
|---|---|---|
| `name` | Char | Nome/apelido |
| `hub_id` | Many2one → `sensor_monitor.hub` | Obrigatório — hub sob o qual opera atualmente |
| `coletor_code` | Char | Identificador estável (`coletor_id` usado nos arquivos) — único |
| `tipo` | Selection (`esp32_wifi`, `esp32_ethernet`, `esp32_rs485_externo`, `hub_rs485_embutido`) | Distingue coletor físico externo de coletor lógico rodando no próprio hub |
| `is_hub_embutido` | Boolean | Verdadeiro quando `tipo = hub_rs485_embutido` — nesse caso, a chave de assinatura é a do secure element do próprio `hub_id` |
| `hardware_modelo` | Char | Ex: `ESP32-WROOM-32SE` (quando aplicável) |
| `pubkey_fingerprint` | Char | Chave pública do coletor (ATECC608A do ESP32, ou do hub quando embutido) — usada pelo serviço de ingestão para validar assinatura dos arquivos |
| `firmware_version` | Char | — |
| `status` | Selection (`online`, `offline`) | — |
| `ultimo_arquivo_recebido` | Datetime | Última data com arquivo validado no ledger |
| `config_version_desejada` | Integer | Versão de config publicada pelo servidor (control plane, ver diretriz 10.1) |
| `config_version_aplicada` | Integer | Última versão que o coletor confirmou rodar (drift se diverge da desejada) |
| `config_version_reportada_em` | Datetime | Quando o coletor reportou a versão aplicada |

### 4.6 `sensor_monitor.measurement.type` (referência/lookup)
Catálogo extensível de tipos de medição — evita hardcode de "temperatura/umidade/pressão" (plataforma genérica).

| Campo | Tipo | Descrição |
|---|---|---|
| `name` | Char | Ex: "Temperatura", "Umidade relativa", "Pressão diferencial" |
| `code` | Char | Código técnico estável (ex: `temperatura`, usado como `tipo_medida` nas leituras) |
| `unidade_padrao` | Char | Ex: `C`, `%UR`, `Pa` |

### 4.7 `sensor_monitor.sensor`
Sensor físico individual.

| Campo | Tipo | Descrição |
|---|---|---|
| `name` | Char | Nome/apelido |
| `sensor_code` | Char | Identificador estável (`sensor_id` usado nas leituras) — único |
| `coletor_id` | Many2one → `sensor_monitor.coletor` | Quem lê esse sensor — obrigatório |
| `area_id` | Many2one → `sensor_monitor.area` | Atribuição **atual** (ver nota na seção 2) — obrigatório |
| `measurement_type_id` | Many2one → `sensor_monitor.measurement.type` | Obrigatório |
| `protocolo_origem` | Selection (`4-20ma`, `rs485`, `i2c`) | Protocolo físico de leitura |
| `unidade` | Char | Pode divergir do padrão do measurement_type se necessário |
| `ativo` | Boolean | — |
| `modbus_register_id` | Many2one → `sensor_monitor.modbus.profile.register` | **Só quando `protocolo_origem = rs485`** — qual registrador (dentro do perfil do dispositivo) este sensor lê. Ver 4.11–4.14. |

**Nota de multiplicidade (Modbus)**: um dispositivo Modbus físico (um endereço de escravo) pode expor **várias medições** (ex: um transmissor combinado temp+umidade tem temperatura no registrador 0 e umidade no registrador 2). Cada medição vira um `sensor` distinto, todos apontando para o mesmo `modbus.device` mas para `modbus_register_id` diferentes. Para sensores RS-485, o `coletor_id` é o coletor lógico "embutido no Hub" (`hub_rs485_embutido`, ver 4.5).

### 4.8 `sensor_monitor.alarm.threshold`
Configuração de limiar de alarme por sensor. **Usar mixin `mail.thread`** (herdar `mail.thread`) para aproveitar o chatter/tracking nativo do Odoo como trilha de auditoria — evita construir um modelo de log de alteração à parte, e cobre o requisito de "log de auditoria dos dois lados" da diretriz (seção 10), desde que toda alteração — vinda do Hub ou da nuvem — resulte numa chamada de `write()` neste registro.

| Campo | Tipo | Descrição |
|---|---|---|
| `sensor_id` | Many2one → `sensor_monitor.sensor` | Obrigatório, único (um threshold ativo por sensor) |
| `limite_min` | Float | — |
| `limite_max` | Float | — |
| `is_valor_padrao_regulatorio` | Boolean | Verdadeiro quando corresponde ao default do vertical (ex: RDC 15) |
| `origem_ultima_alteracao` | Selection (`hub`, `nuvem`) | De onde veio a última mudança |
| `justificativa_desvio` | Text | Obrigatório preencher quando o valor diverge do padrão regulatório — **constraint a implementar** |
| Campos com `tracking=True`: `limite_min`, `limite_max` | — | Para aparecerem automaticamente no chatter quando alterados |

**Constraint de negócio a implementar**: se `is_valor_padrao_regulatorio = False` e o vertical do site for `cme_hospitalar`, exigir `justificativa_desvio` preenchida e usuário pertencente a um grupo com permissão elevada (ver seção 6).

### 4.9 `sensor_monitor.alarm.event`
Ocorrência real de alarme (violação de limiar).

**Revisão desta rodada — fonte de dados**: o coletor agora gera e assina seu próprio arquivo diário de eventos de alarme (ver `esp32_coletor_spec.md`, seção 5) — esse arquivo é a **fonte primária** para popular este modelo (o serviço de ingestão faz parsing do arquivo de alarme, valida a assinatura, e cria um `alarm.event` por linha de transição), não mais um cálculo feito do zero pelo servidor a partir das leituras brutas. Opcional, recomendado como checagem de integridade adicional: o servidor pode reconstruir independentemente o estado de alarme a partir do arquivo de leituras (que também tem os valores) e comparar com o que o coletor reportou no arquivo de alarme — uma divergência entre os dois é, em si, um evento a investigar.

| Campo | Tipo | Descrição |
|---|---|---|
| `sensor_id` | Many2one → `sensor_monitor.sensor` | — |
| `area_id` | Many2one → `sensor_monitor.area` | Snapshot no momento do evento (não recalcular depois) |
| `coletor_id` | Many2one → `sensor_monitor.coletor` | Origem do evento (novo) |
| `timestamp_deteccao` | Datetime | Vem do `timestamp` da linha `entrada_alarme` do arquivo de alarme |
| `timestamp_resolucao_sensor` | Datetime | Vem do `timestamp` da linha `saida_alarme` correspondente, quando existir (novo — distingue da resolução operacional feita por um humano, que é `data_resolucao` abaixo) |
| `valor_lido` | Float | — |
| `tipo_violacao` | Selection (`acima_limite`, `abaixo_limite`, `sensor_offline`, `erro_leitura`) | — |
| `limite_configurado_snapshot` | Float | Cópia do limiar vigente **no momento do evento** — vem direto do `limite_min_vigente`/`limite_max_vigente` do arquivo assinado, não recalculado |
| `origem_arquivo_hash` | Char | Hash do arquivo de alarme de onde este evento veio — rastreabilidade até a fonte assinada (novo) |
| `status` | Selection (`aberto`, `reconhecido`, `resolvido`) | Workflow operacional (humano) — independente de `timestamp_resolucao_sensor` |
| `usuario_responsavel_id` | Many2one → `res.users` | — |
| `data_resolucao` | Datetime | Quando um humano marcou como resolvido (pode ser diferente de quando o sensor voltou ao normal) |
| `observacoes` | Text | — |

Herdar `mail.thread` também aqui, para comentários/notificações nativas do Odoo. Integração opcional futura: vincular a `helpdesk.ticket` ou `maintenance.request` se esses módulos estiverem instalados — **não** modelar como dependência obrigatória.

### 4.10 `sensor_monitor.file.ledger`
Ledger de recebimento de arquivo (ver diretriz seção 11 — detecção de lacunas sem depender da integridade de arquivos antigos). Volume baixo (poucas linhas por coletor por dia), cabe tranquilamente no Odoo/Postgres.

**Revisão desta rodada**: agora existem dois tipos de arquivo por coletor por dia (leituras e alarme, ver `esp32_coletor_spec.md` seção 5) — o ledger precisa distinguir qual é qual, em vez de assumir um único arquivo por dia.

| Campo | Tipo | Descrição |
|---|---|---|
| `coletor_id` | Many2one → `sensor_monitor.coletor` | — |
| `hub_id` | Many2one → `sensor_monitor.hub` | Denormalizado para consulta rápida |
| `tipo_arquivo` | Selection (`leituras`, `alarmes`) | Novo — distingue os dois tipos de arquivo diário |
| `data_referencia` | Date | — |
| `hash_final` | Char | — |
| `assinatura` | Char (ou Binary) | — |
| `horario_recebimento` | Datetime | — |
| `status_validacao` | Selection (`valido`, `invalido`, `pendente`, `faltante`) | `faltante` é gerado por um job periódico que detecta lacunas na sequência, não pela chegada de um arquivo |
| `motivo_rejeicao` | Text | Preenchido quando `status_validacao = invalido` |
| `total_linhas` | Integer | Para arquivo de alarme, corresponde a `total_eventos` |

**Constraint de negócio a implementar**: único por (`coletor_id`, `data_referencia`, `tipo_arquivo`).

### 4.11 `sensor_monitor.rs485.bus` (novo — barramento RS-485)
Um barramento físico RS-485 no Hub. Multi-bus desde a v1 (ver diretriz seção 6.1): um Hub pode ter vários (a UART PL011 nativa + adaptadores USB-RS485).

| Campo | Tipo | Descrição |
|---|---|---|
| `hub_id` | Many2one → `sensor_monitor.hub` | Obrigatório |
| `name` | Char | Apelido do barramento |
| `bus_code` | Char | Identificador estável — único por hub |
| `serial_port` | Char | Porta no Hub (ex: `/dev/ttyAMA0`, `/dev/ttyUSB0`) |
| `baud_rate` | Integer | Ex: 9600, 19200 |
| `parity` | Selection (`none`, `even`, `odd`) | — |
| `stop_bits` | Selection (`1`, `2`) | — |
| `data_bits` | Integer | Normalmente 8 |

**Regra**: todos os dispositivos deste barramento compartilham esses parâmetros seriais (constraint física do RS-485).

### 4.12 `sensor_monitor.modbus.profile` (novo — catálogo de perfil de dispositivo, GLOBAL)
Perfil reutilizável de um modelo de transdutor Modbus. Global (não filtrado por tenant) — é catálogo técnico compartilhado. Adicionar um fabricante novo = criar um perfil aqui, sem alterar código.

| Campo | Tipo | Descrição |
|---|---|---|
| `name` | Char | Ex: "Fabricante X — Transmissor Temp/Umidade TX-100" |
| `fabricante` | Char | — |
| `modelo` | Char | — |
| `register_ids` | One2many → `sensor_monitor.modbus.profile.register` | Mapa de registradores |

### 4.13 `sensor_monitor.modbus.profile.register` (novo — linha do mapa de registradores)
Um registrador (ou grupo) dentro de um perfil, correspondendo a uma medição.

| Campo | Tipo | Descrição |
|---|---|---|
| `profile_id` | Many2one → `sensor_monitor.modbus.profile` | Obrigatório |
| `name` | Char | Ex: "Temperatura" |
| `measurement_type_id` | Many2one → `sensor_monitor.measurement.type` | O que este registrador representa |
| `function_code` | Selection (`03_holding`, `04_input`) | Função Modbus de leitura |
| `register_address` | Integer | Endereço do registrador inicial |
| `register_count` | Integer | 1 (16-bit) ou 2 (32-bit), etc. |
| `data_type` | Selection (`int16`, `uint16`, `int32`, `uint32`, `float32`, ...) | Codificação |
| `byte_order` | Selection (`big`, `little`, `big_swap`, `little_swap`) | Ordem de bytes/words (o "pesadelo de endianness" do Modbus) |
| `scale` | Float | Fator multiplicativo (ex: 0.1) |
| `offset` | Float | Offset aditivo |
| `unidade` | Char | Unidade de engenharia resultante |

### 4.14 `sensor_monitor.modbus.device` (novo — instância física de dispositivo no barramento)
Um transdutor físico específico ligado a um barramento, com seu endereço de escravo e o perfil que descreve como lê-lo.

| Campo | Tipo | Descrição |
|---|---|---|
| `name` | Char | Apelido |
| `rs485_bus_id` | Many2one → `sensor_monitor.rs485.bus` | Em qual barramento está |
| `slave_address` | Integer (1–247) | Endereço Modbus do escravo |
| `profile_id` | Many2one → `sensor_monitor.modbus.profile` | Mapa de registradores deste modelo |

**Constraint**: único por (`rs485_bus_id`, `slave_address`) — dois dispositivos não podem ter o mesmo endereço no mesmo barramento. Os `sensor` que leem este dispositivo apontam para ele via `modbus_register_id.profile_id` + o próprio device (ver 4.7); a implementação pode adicionar um `modbus_device_id` direto no `sensor` para simplificar a query de leitura do Hub — decisão de implementação.

### 4.15 Geolocalização e croqui de planta (candidato futuro — **não implementado na Fase 1** já concluída)

Registrado aqui para viabilizar, mais adiante, (a) um mapa com todos os sites de todos os clientes (empresas com várias unidades/localidades) e (b) uma planta/croqui por área mostrando onde cada dispositivo está fisicamente instalado. Nenhum campo desta seção existe no módulo `afr_sentinela_sensor_monitor` já implementado — é trabalho a adicionar numa rodada futura (migração simples, campos aditivos, sem impacto no que já está em produção).

**Cliente (`res.partner`)**: não precisa de campo novo — usar a geolocalização nativa do Odoo (`partner_latitude`/`partner_longitude`, módulo `base_geolocalize`) em vez de reinventar. Basta instalar o módulo nativo quando essa feature entrar em pauta.

**`sensor_monitor.site`** — âncora principal de geolocalização (é aqui que mora o "empresa em vários locais"):

| Campo | Tipo | Descrição |
|---|---|---|
| `latitude` | Float | Graus decimais |
| `longitude` | Float | Graus decimais |

**`sensor_monitor.area`** — planta/croqui da sala (não precisa de GPS próprio, já está dentro do site):

| Campo | Tipo | Descrição |
|---|---|---|
| `floor_plan_image` | Image | Planta/croqui da área (upload); Odoo `Image` (não `Binary` puro) para ganhar thumbnail/resize automático |
| `pavimento` | Char | Opcional — andar/pavimento, útil em prédios multi-andar |

**`sensor_monitor.sensor`** — o pino mais valioso (onde o dispositivo está, de fato, marcado na planta):

| Campo | Tipo | Descrição |
|---|---|---|
| `pos_x` | Float (0.0–1.0) | Posição horizontal normalizada (fração da largura da imagem de `area_id.floor_plan_image`) — independente da resolução real da imagem |
| `pos_y` | Float (0.0–1.0) | Posição vertical normalizada, mesma lógica |

**`sensor_monitor.hub`** e **`sensor_monitor.coletor`** — pino opcional (o hub/coletor físico nem sempre corresponde 1:1 a uma área monitorada — ex. ESP32 numa antessala lendo sensores de salas adjacentes):

| Campo | Tipo | Descrição |
|---|---|---|
| `area_id` | Many2one → `sensor_monitor.area` (opcional) | Área onde o dispositivo está fisicamente instalado, quando fizer sentido pinar na planta |
| `pos_x`, `pos_y` | Float (0.0–1.0) | Mesma convenção do sensor, relativa à planta de `area_id` (só tem sentido se `area_id` setado) |

**Nota de implementação**: `pos_x`/`pos_y` normalizados (não pixel) evitam que a posição do pino quebre se a imagem for reprocessada/re-comprimida — o frontend só multiplica a fração pela largura/altura renderizada da imagem no momento de desenhar o marcador.

## 5. Regras de negócio e constraints a implementar

1. **Isolamento multi-tenant**: `ir.rule` em todos os modelos acima (exceto os de referência/lookup, que são globais), filtrando pela cadeia até `site_id.partner_id`, restrito ao(s) `partner_id` associado(s) ao usuário logado quando ele for usuário externo/portal do cliente. Usuários internos (equipe operacional do SaaS) têm regra sem esse filtro.
2. **Threshold com desvio do padrão regulatório exige justificativa** (seção 4.8).
3. **`file.ledger` único por (coletor, dia, tipo_arquivo)** (seção 4.10) — cada coletor deve ter, todo dia, um registro `leituras` **e** um registro `alarmes` (este último mesmo se `total_linhas = 0`, ver `esp32_coletor_spec.md` seção 5 — arquivo de alarme vazio ainda é gerado e assinado como atestado positivo).
4. **Sensor sempre pertence a um coletor e uma área** — não permitir sensor órfão.
5. **Job periódico (cron do Odoo)** que varre `file.ledger` por coletor **e por tipo de arquivo** e marca como `faltante` qualquer dia sem registro entre o primeiro e o último dia de operação conhecido do coletor — implementa a detecção de lacuna descrita na diretriz. Um dia com `leituras` presente mas `alarmes` faltante (ou vice-versa) é uma lacuna tão relevante quanto os dois faltando.
6. **Control plane — config remota e comandos** (ver diretriz seção 10.1). Generaliza a sincronização de limiar: **o Odoo é fonte de verdade da configuração operacional** (limiares, intervalo de leitura, enable/disable de sensor, config Modbus) e a propaga aos dispositivos.
   - Qualquer `write()` que altere config relevante de um dispositivo **incrementa `config_version_desejada`** do hub/coletor afetado e faz o serviço de integração **publicar a config corrente num tópico MQTT retido** por dispositivo.
   - O dispositivo aplica e **reporta a versão via MQTT**; o serviço grava em `config_version_aplicada` + `config_version_reportada_em`. Uma view/indicador deve destacar dispositivos com **drift** (desejada ≠ aplicada).
   - **Comandos remotos** (reboot, force-sync, diagnóstico): uma ação no Odoo publica um comando em tópico MQTT **não-retido**, com id único; o dispositivo confirma (ack). Modelo sugerido opcional: `sensor_monitor.device.command` (destino hub/coletor, tipo, payload, status `enviado`/`confirmado`/`falhou`, id, timestamps) para dar rastreabilidade/auditoria às ações. **Sem assinatura na config/comando na v1** — confia no canal (candidato a v2, ver diretriz 10.1).
7. **Retenção e ciclo de vida** (ver diretriz 9.3): `retention_years` sempre **≥ 5** (constraint — piso legal). A política pós-5-anos (`retention_mode`) e o expurgo efetivo do dado antigo são executados **fora do Odoo**, no serviço de retenção que atua sobre o Timescale (drop de linhas cruas fora da janela quente, mantendo agregados) e sobre o object storage (tiering para arquivo frio; expurgo só após o object-lock expirar). O Odoo guarda a *política* e o *estado de ciclo de vida*, não executa o expurgo de dado bruto.
8. **Offboarding** (ver diretriz 9.3): mudar `lifecycle_status` para `offboarding` dispara: parar coleta nova, gerar export completo (arquivos assinados + relatórios/agregados) para o cliente (`export_entregue_em`), manter o dado pelo piso legal (imposto pelo object-lock), e só então expurgar (`arquivado` → `expurgado`).

## 6. Segurança e grupos de acesso

Grupos sugeridos (`res.groups`):
- **Sensor Monitor / Visualização**: leitura de dashboards e dados do(s) site(s) do próprio cliente (portal).
- **Sensor Monitor / Operação**: acknowledgment de alarmes, resolução de ocorrências.
- **Sensor Monitor / Configuração Avançada**: pode alterar `alarm.threshold` além dos valores padrão regulatórios (exige `justificativa_desvio`).
- **Sensor Monitor / Admin (interno SaaS)**: acesso total, cadastro de sites/hubs/coletores/sensores, sem filtro de `ir.rule` por partner.

## 7. Dados de referência a popular na instalação (vertical CME)

Carregar via `data/rdc15_default_thresholds_data.xml` (ou similar) os `area.category` e `alarm.threshold` padrão do vertical `cme_hospitalar`, direto da diretriz (seção 3):

| Área | Temperatura | Pressão diferencial |
|---|---|---|
| Expurgo | 18–22°C | Negativa, mín. 2,5 Pa |
| Preparo/Esterilização | 20–24°C | Positiva, mín. 2,5 Pa |
| Desinfecção química | — | Negativa |

Esses valores nascem com `is_valor_padrao_regulatorio = True`.

## 8. Integração com o serviço de ingestão (fora do Odoo)

O serviço de ingestão (Python, roda fora do Odoo, recebe arquivos via SFTP — ver diretriz seção 8) precisa:
- **Ler** metadados de `coletor`, `sensor`, `alarm.threshold` para validar e avaliar cada arquivo recebido.
- **Escrever** em `file.ledger` (status de validação) e `alarm.event` (quando um limiar é violado).

**Recomendação**: usuário de serviço dedicado (`res.users` técnico, não humano) com acesso via API externa do Odoo (XML-RPC/JSON-RPC nativo, ou um controller REST customizado sob `/sensor_monitor/api/`) — **desenho exato da API é um ponto em aberto**, não coberto por este documento (candidato a próxima rodada de discussão).

## 9. Fora de escopo deste módulo

- **Leituras brutas de sensor** (timestamp + valor por sensor) — ficam inteiramente no TimescaleDB, não são modeladas como registros Odoo. O volume (bilhões de linhas em 5 anos, ver diretriz seção 9) inviabilizaria o ORM do Odoo para essa finalidade.
- **Frontend** — consome tanto o Odoo (via API, para cadastro/config/alarmes) quanto o TimescaleDB (via SQL, para séries temporais) — desenho ainda não discutido (diretriz seção 12).

## 10. Pontos em aberto para quem for implementar

1. Versão do Odoo a usar (17/18/19) — confirmar antes de gerar o módulo, pois sintaxe de `ir.rule`/mixins pode variar ligeiramente.
2. Desenho exato da API de integração com o serviço de ingestão (seção 8).
3. Se o cliente final (hospital) terá login de portal Odoo próprio, ou se o frontend será 100% separado consumindo API (nesse caso, os grupos de portal descritos na seção 6 podem não ser necessários no Odoo em si).
4. Nomenclatura técnica definitiva do módulo (`sensor_monitor` é sugestão, ajustar se a organização já tiver convenção própria).
5. Geolocalização de site + croqui/planta por área com posição de dispositivo (seção 4.15) — campos aditivos, candidato a próxima rodada; não bloqueia o que já está implementado.
