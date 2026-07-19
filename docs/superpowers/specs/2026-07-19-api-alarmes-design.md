# API de Alarmes — Design

## Contexto

`sensor_monitor.alarm.event` já existe no Odoo e já é populado pela ingestão
(Fase 2, feita): cada linha `entrada_alarme`/`saida_alarme` de um arquivo de
alarme assinado vira um registro, com o limiar vigente no momento (snapshot),
área vigente no momento (snapshot), status operacional (`aberto`,
`reconhecido`, `resolvido`) e campos de resolução humana
(`usuario_responsavel_id`, `data_resolucao`, `observacoes`).

Não existe hoje nenhum endpoint expondo isso pro frontend. O `frontend_spec.md`
original (§3, §8) já previa um "painel de alarmes" na SPA e listava
"lista e ciclo de alarme" como um dos três tipos de dado que o frontend
consome — mas a arquitetura original pressupunha o SPA chamando a API nativa
do Odoo direto, algo que não bate mais com o fluxo de auth que construímos
(login emite um JWT nosso, o frontend nunca guarda sessão Odoo crua depois
disso).

O roadmap chama de **MARCO M1** justamente "simulador → ingestão →
Timescale/Odoo → dashboard mostra ao vivo + histórico + **alarmes**" — essa
fatia fecha a peça que falta desse marco.

## Objetivo

`GET /alarmes` no serviço `api/` (mesmo padrão de `auth`/`meta`/`historico`/
`live` já em produção), somente leitura, com filtros, servindo o histórico e
o estado atual de `alarm.event` pro frontend.

## Decisões já validadas

- **Arquitetura**: endpoint FastAPI próprio (`api/alarmes.py`), não chamada
  direta do frontend à API nativa do Odoo — consistente com o resto do
  serviço, reaproveita `verificar_token`/`get_cliente_servico` já existentes.
- **Escopo**: só leitura. Reconhecer/resolver alarme continua no Odoo nativo
  (OWL) por enquanto — expor essas ações no SPA fica pra uma fatia futura,
  se/quando fizer sentido de produto. Essa decisão resolve a tensão que
  existia no `frontend_spec.md` original entre §1 (ciclo de vida fica no
  Odoo nativo) e §8 (painel do SPA teria botão de ação).
- **Shape**: um endpoint só, `GET /alarmes`, com filtros opcionais — não um
  endpoint por sensor. A Overview precisa de contagem agregada por
  site/área (que exigiria N chamadas se fosse por-sensor); o painel de
  alarmes precisa da lista completa filtrável. Um endpoint com filtros
  serve os dois casos.
- **Paginação**: nenhuma por agora — `limit` fixo no código (200 linhas,
  ordenado por `timestamp_deteccao desc`, mais recente primeiro). Volume
  esperado é baixo (o próprio `odoo_modelo_dados_spec.md` já caracteriza
  isso como "poucas linhas por coletor por dia" pro ledger, e alarme é
  ainda mais raro que leitura). Paginação de verdade (offset/limit,
  contrato com total/next) vira fatia futura se o volume um dia justificar.

## Endpoint

```
GET /alarmes?status=&sensor_code=&area_code=&desde=&ate=
Authorization: Bearer <jwt>
```

Todos os filtros são opcionais e combináveis (AND):

- `status`: um de `aberto` / `reconhecido` / `resolvido`.
- `sensor_code`: código do sensor. Se informado e o sensor não existe no
  Odoo, **404** (mesmo padrão de `historico.py`/`meta.py`) — distinto de
  "sensor existe mas não tem alarme nenhum", que é 200 com lista vazia.
- `area_code`: código de área. Filtra pelo snapshot de área **gravado no
  evento**, não pela área atual do sensor (um sensor pode ter sido
  realocado depois do alarme — o snapshot é o que aconteceu de fato,
  igual já vale pra `area_id` em `alarm.event` por design). Sem validação
  de existência — código desconhecido só retorna lista vazia.
- `desde` / `ate`: datetime ISO 8601, filtram por `timestamp_deteccao`
  (`>= desde`, `<= ate`).

Resposta: `200` com uma lista (nunca 404 pela ausência de resultado — só
`sensor_code` inexistente causa 404).

## Shape da resposta

```ts
type TipoViolacao = 'acima_limite' | 'abaixo_limite' | 'sensor_offline' | 'erro_leitura'
type StatusAlarme = 'aberto' | 'reconhecido' | 'resolvido'

type AlarmEvent = {
  id: number
  sensor_code: string
  area_code: string                        // snapshot no momento do evento
  timestamp_deteccao: number               // ms (Unix * 1000)
  timestamp_resolucao_sensor: number | null // ms — quando o sensor voltou a faixa, se ja voltou
  valor_lido: number
  tipo_violacao: TipoViolacao
  limite_configurado_snapshot: number
  status: StatusAlarme
  usuario_responsavel: string | null       // nome, nao id Odoo — display_name
  data_resolucao: number | null            // ms — quando um humano marcou resolvido
  observacoes: string | null
}
```

`sensor_code`/`area_code` são strings planas (não objetos aninhados como em
`SensorMeta`) — o frontend já tem nome/categoria da área em cache (via
`metaApi.listSensors()`), então não faz sentido duplicar esse lookup aqui;
o alarme só precisa entregar os códigos pra correlação e pro que é
específico dele (snapshot no momento do evento).

## Arquitetura da query

`sensor_id`/`area_id` em `alarm.event` são `Many2one` — `search_read` via
XML-RPC devolve `[id, display_name]` automaticamente pra esses campos, mas
`display_name` não é o mesmo que `sensor_code`/`area_code`. Resolver isso
com uma query em lote (não uma leitura por evento — evita N+1 numa lista
de até 200 linhas):

1. `search_read` em `alarm.event` com o domínio montado a partir dos
   filtros, campos incluindo `sensor_id`, `area_id` (como ids).
2. Coletar os `sensor_id`s e `area_id`s **distintos** do resultado.
3. Um `read` em lote de `sensor.sensor` (`[ids], fields=['sensor_code']`) e
   um de `sensor.area` (`[ids], fields=['area_code']`) — dois lookups no
   total, não um por linha.
4. Montar os dicts `sensor_id -> sensor_code` / `area_id -> area_code` e
   mapear pra cada evento.

`usuario_responsavel_id` não precisa de lookup em lote — `display_name` do
próprio `search_read` já serve (`usuario_responsavel_id[1]` quando
presente, `None` quando o campo é `False`).

## Erros / edge cases

- Sem token / token inválido → 401 (mesmo `verificar_token` de sempre).
- `sensor_code` filtrado mas inexistente → 404.
- `status`/`tipo_violacao` fora do enum válido — não se aplica aqui
  (`tipo_violacao` não é filtro; `status` como filtro usa `Literal` do
  FastAPI, que já responde 422 automaticamente pra valor fora do enum).
- Nenhum resultado (com ou sem filtro) → 200, lista vazia.
- Campos nulos no Odoo (`timestamp_resolucao_sensor`, `data_resolucao`,
  `observacoes`, `usuario_responsavel_id` = `False`) → `null` no JSON, não
  omitidos.

## Testes

- Query em lote: teste de integração — cria 2+ `alarm.event` reais (em
  sensores/áreas diferentes) via `odoo_cliente.processar_entrada_alarme`
  (já existe), chama a função de listagem, confere que `sensor_code`/
  `area_code` batem sem depender de quantas chamadas RPC foram feitas
  (ou verifica isso diretamente, contando chamadas).
- Endpoint: `TestClient` — 401 sem token, 404 `sensor_code` inexistente,
  filtro por `status`, filtro por `sensor_code`, filtro por `area_code`,
  filtro por `desde`/`ate`, ordenação (mais recente primeiro), campos
  nulos aparecendo como `null`. Limpeza dos eventos de teste no `finally`
  (mesmo padrão já usado em `test_odoo_cliente.py`/`test_ingestor.py`).

## Fora de escopo

- Reconhecer/resolver alarme via API (escrita) — Odoo nativo por agora.
- Paginação real (offset/limit, total/next).
- Agregações prontas (ex.: contagem por área já computada no servidor) —
  o frontend pode derivar isso client-side a partir da lista filtrada por
  `status=aberto`, é pouco volume.
- Notificação/push de novo alarme — isso já é coberto pelo feed `live`
  (SSE) mostrando o valor fora de faixa; o alarme formal (`alarm.event`)
  é auditoria, não o gatilho de UI em tempo real.
