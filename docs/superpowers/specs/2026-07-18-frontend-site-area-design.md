# Design — Frontend Sentinela CME: Site → Área

> Spec de implementação. Quarta fatia da Fase 4, reusando dados/componentes
> das fatias anteriores (Overview, Detalhe do Sensor, Roteamento). Tela 2 do
> `frontend_spec.md` §8.

## 1. Objetivo e escopo

Tela por área listando **todos** os sensores daquela área, cada um com valor
ao vivo + indicação de dentro/fora de faixa. Hoje (Overview) cada área só
tem 1 sensor mockado — esta fatia adiciona um 2º sensor por área (Expurgo,
Preparo) pra tornar a tela minimamente útil, e a `AreaCard` da Overview
passa a linkar pra cá em vez de ir direto pro único sensor.

**Fora de escopo**: seletor de site (mock só tem 1 site — rota não leva
`siteId`, decisão consistente com o resto do app hoje). Layout gráfico da
planta física da área (candidato futuro, ver `odoo_modelo_dados_spec.md`
§4.15 — geolocalização/croqui, não implementado ainda em lugar nenhum).

## 2. Mock — 2º sensor por área (pressão diferencial)

`odoo_modelo_dados_spec.md` §7 já documenta os valores reais de referência
RDC15 pra pressão diferencial — reusar, não inventar:

| Área | Sensor novo | Threshold |
|---|---|---|
| Expurgo | `PRESS-EXP-01` | Pressão diferencial **negativa**, mín. 2,5 Pa — modelado como faixa `[-15, -2,5]` (simplificação: a regra real é "mais negativa que -2,5", sem teto rígido documentado; -15 é um piso plausível de mock, não um valor regulatório) |
| Preparo/Esterilização | `PRESS-PRE-01` | Pressão diferencial **positiva**, mín. 2,5 Pa — modelado como `[2,5, 15]`, mesma simplificação espelhada |
| Arsenal | — (continua 1 sensor, sem threshold) | sem mudança |

Novo `measurement_type`: `{ code: 'pressao_diferencial', name: 'Pressão diferencial' }`,
unidade `Pa`. `liveApi`/`historyApi` não mudam de mecanismo — só ganham
entradas de amplitude/threshold pros 2 novos sensores (mesma técnica já
usada pra `TEMP-PRE-01` cruzar a faixa deliberadamente).

## 3. Rota

`/area/:areaCode` → `AreaPage`. Sem `siteId` (mock de site único).

## 4. Navegação

- `AreaCard` (Overview): `to` muda de `/sensor/${sensors[0].sensor_code}`
  para `/area/${area.area_code}`.
- `AreaPage`: link "← Voltar" pra `/` (mesmo padrão do Detalhe do Sensor).
- Cada linha de sensor na `AreaPage` linka pra `/sensor/${sensor_code}`
  (tela já existente, sem mudança).

## 5. Dados

Nenhuma peça nova de infraestrutura de dados — `useSensors`, `useThresholds`,
`useLiveStatuses`, `groupSensorsByArea` já foram desenhados pra N sensores
por área desde a Overview (o "1 sensor/área" de hoje é só o estado atual do
mock, não uma limitação do código). `AreaPage` busca todos os sensores,
agrupa, encontra o grupo do `areaCode` da URL, renderiza.

## 6. Componentes

```
AreaPage
├── Link "Voltar" (padrao ja existente)
├── header: nome + categoria da area
└── SensorRow × N   — nome do sensor, valor ao vivo (mono) + unidade,
                       status (cor+icone+texto, reusa statusVisuals/LABELS),
                       Link pro Detalhe do Sensor
```

`SensorRow` é novo, mas reusa 100% do vocabulário visual já existente
(`StatusIcon`, `statusTextColor`, `LABELS`, `sensorDisplayState`) — nenhum
elemento visual novo.

## 7. Estados de erro/loading

Mesmo padrão das telas anteriores: skeleton por linha enquanto carrega,
mensagem+retry se `listSensors` falhar. `areaCode` que não bate com nenhuma
área carregada (URL inválida/digitada à mão): mostrar "Área não encontrada"
com link de volta — não crashar.

## 8. Testes

1. Mock: `PRESS-EXP-01`/`PRESS-PRE-01` existem, thresholds corretos,
   `listSensors` devolve 5 sensores.
2. `SensorRow`: mostra nome+valor+status; status sempre com ícone (não só
   cor); linka pro sensor certo.
3. `AreaPage`: renderiza todos os sensores da área certa (filtra por
   `areaCode`); área inexistente mostra mensagem, não crasha.
4. `AreaCard`: link atualizado pra `/area/:code` (não mais direto pro
   sensor).
5. Integração: Overview → clicar área → `AreaPage` → clicar sensor →
   Detalhe do Sensor → Voltar → `AreaPage` (não Overview — cadeia completa).

## 9. Entregáveis

- Mock expandido (2 sensores novos + measurement_type pressão).
- `AreaPage` + `SensorRow`.
- `AreaCard` relinkado.
- Rota `/area/:areaCode` em `App.tsx`.
- Suite verde; verificação visual real (mesma disciplina das fatias
  anteriores — já achou bugs reais 3 vezes).
