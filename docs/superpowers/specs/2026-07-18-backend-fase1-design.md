# Design — Backend Fase 1 (módulo Odoo + schema TimescaleDB)

> Complementa `odoo_modelo_dados_spec.md` (modelo de dados completo, autoridade sobre os 14 modelos) e `diretrizes_projeto.md` (arquitetura geral). Este documento resolve os pontos em aberto necessários para começar a implementação e descreve o esqueleto Docker que não existia ainda no repo.

## Escopo desta rodada

Fase 1 do `roadmap_implementacao.md`, as duas trilhas em paralelo:
- **1A** — módulo Odoo `afr_sentinela_sensor_monitor`.
- **1B** — schema TimescaleDB (hypertable de leituras + agregados contínuos).

**Fora de escopo** (fases posteriores, não tocar agora): serviço de ingestão, Mosquitto, SFTPGo, OpenVPN, APIs de leitura/tempo real/auth, control plane. O Docker Compose desta rodada só sobe `odoo` + `postgres-odoo` + `timescaledb`.

## Decisões fechadas nesta rodada

| Ponto em aberto (spec, seção 10) | Decisão |
|---|---|
| Versão do Odoo | **18** |
| Nome técnico do módulo | **`afr_sentinela_sensor_monitor`** (segue convenção `afr_*` já usada em outros projetos do autor) |
| Localização do docker-compose | Novo, neste repo (`odoo_sentinela`), independente de outros projetos Odoo do autor |
| Timescale guarda eventos de alarme? | **Não.** A diretriz geral (seção 9) menciona isso de passagem, mas o spec de dados (mais detalhado, seção 4.9) já modela `alarm.event` inteiramente no Odoo, com `mail.thread` para chatter/auditoria — não faz sentido duplicar em duas fontes de verdade. Timescale fica só com leitura bruta + agregados. |

## 1. Docker skeleton

`docker-compose.yml` na raiz do repo:
- `odoo`: build local (`Dockerfile`, `FROM odoo:18.0`), volume `./addons:/mnt/extra-addons`, volume `./conf:/etc/odoo`.
- `postgres-odoo`: Postgres padrão (imagem oficial), volume próprio, é o banco do Odoo.
- `timescaledb`: imagem `timescale/timescaledb:latest-pg16` (ou versão compatível mais recente na implementação), volume próprio, schema aplicado via script de init montado (seção 3 abaixo).

Sem Traefik/reverse-proxy nesta rodada (não há necessidade de expor nada publicamente ainda — dev local).

## 2. Módulo Odoo `afr_sentinela_sensor_monitor`

Segue **integralmente** a especificação já escrita em `odoo_modelo_dados_spec.md` seções 3–7:
- Estrutura de pastas da seção 3 (models/, security/, data/, views/).
- Os 14 modelos da seção 4 (`site`, `area.category`, `area`, `hub`, `coletor`, `measurement.type`, `sensor`, `alarm.threshold`, `alarm.event`, `file.ledger`, `rs485.bus`, `modbus.profile`, `modbus.profile.register`, `modbus.device`), com todos os campos, tipos e notas de multiplicidade descritas ali.
- Todas as regras de negócio/constraints da seção 5 (isolamento multi-tenant via `ir.rule`, justificativa obrigatória em desvio de threshold, unicidade do ledger por coletor+dia+tipo_arquivo, sensor nunca órfão, cron de detecção de lacuna, `retention_years >= 5`).
- Grupos de acesso da seção 6 (Visualização, Operação, Configuração Avançada, Admin interno).
- Dados de referência da seção 7 (`area.category` + `alarm.threshold` padrão RDC15, `is_valor_padrao_regulatorio = True`).

Views administrativas: uma form/tree básica por modelo (o suficiente para cadastro manual durante testes/dev — nada de dashboard custom aqui, isso é Fase 4/frontend).

**Não incluído nesta rodada** (pertence a fases posteriores, mas os campos já existem no modelo para não exigir migration depois): lógica de `config_version_desejada`/`aplicada` (control plane, Fase 5) e o modelo opcional `sensor_monitor.device.command` — campos ficam no modelo, mas sem lógica de publicação MQTT associada ainda.

## 3. Schema TimescaleDB

Um script de init SQL (`timescale/init.sql`, montado em `/docker-entrypoint-initdb.d/` no container `timescaledb`):

- **Hypertable `sensor_reading`**: colunas `time` (timestamptz, chunk key), `site_id` (Char, denormalizado — segunda dimensão de particionamento junto com `time`, via `add_dimension`), `coletor_id`, `sensor_id`, `area_id`, `tipo_medida`, `valor` (double precision), `unidade`, `protocolo_origem`, `status_leitura`. Identificadores (`site_id`, `sensor_id`, etc.) guardados como os `*_code` estáveis do Odoo (Char), não FK — Timescale não tem FK cross-database com o Postgres do Odoo.
- **Continuous aggregates**: `sensor_reading_hourly` e `sensor_reading_daily` — `min(valor)`, `max(valor)`, `avg(valor)` agrupados por `sensor_id` + bucket de tempo.
- **Política de compressão**: habilitada na hypertable crua, comprimindo chunks mais antigos que ~7 dias (parâmetro exato é decisão de implementação, não trava aqui).
- **Sem política de retenção automática** (drop de dado antigo) nesta rodada — isso é Fase 8, decisão operacional a amadurecer depois; o schema só precisa *suportar* isso no futuro, não executá-lo agora.

Índices: `(sensor_id, time DESC)` para leitura por sensor — é o padrão de acesso do dashboard (Fase 4) e o único índice adicional necessário além do próprio particionamento por `time`.

## 4. Testes

- Módulo Odoo: testes Python padrão do Odoo (`odoo.tests.common.TransactionCase`) cobrindo as constraints de negócio da seção 5 do spec (isolamento multi-tenant, justificativa obrigatória, unicidade do ledger, `retention_years >= 5`, sensor órfão rejeitado).
- TimescaleDB: verificação manual/script simples que insere linhas de exemplo e confere os continuous aggregates — sem framework de teste formal para SQL nesta rodada (volume pequeno, risco baixo).

## 5. Sequência sugerida de implementação

1. Docker skeleton (compose + Dockerfile + volumes vazios) sobe e o Odoo inicia limpo.
2. Modelos de referência/lookup primeiro (`area.category`, `measurement.type`) — sem dependência de outros.
3. Hierarquia principal (`site` → `area` → `hub` → `coletor` → `sensor`).
4. `alarm.threshold` + `alarm.event` + `file.ledger`.
5. Ramo RS-485/Modbus (`rs485.bus`, `modbus.profile`, `modbus.profile.register`, `modbus.device`).
6. Segurança (`ir.model.access.csv`, `ir.rule`, grupos) + dados de referência RDC15.
7. Schema TimescaleDB (script init + verificação manual).
8. Testes Python das constraints de negócio.

## Pontos que seguem em aberto (não bloqueiam esta rodada)

- Desenho exato da API Odoo↔serviço de ingestão (Fase 2/3) — spec seção 8, ainda não decidido.
- Se o cliente final terá portal Odoo próprio ou só a SPA (spec seção 10, item 3) — não afeta os modelos desta rodada, só a config de grupos de portal.
