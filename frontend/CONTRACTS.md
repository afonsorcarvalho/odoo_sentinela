# Data Contracts — Sentinela Sensor Detail

Este documento define os contratos de dados (shapes) utilizados na tela "Detalhe do Sensor" (Fase 2) e seu mapeamento aos campos reais no Odoo (Fase 3).

**Status:** Contrato de-facto — Fase 3 real deve respeitar estes shapes.

---

## 1. SensorMeta

Metadados estáticos de um sensor (identificação, localização, tipo de medição).

### Definição TypeScript
```ts
type SensorMeta = {
  sensor_code: string           // Código único do sensor (ex: "TEMP-SALA-01")
  name: string                  // Nome legível (ex: "Temperatura Sala Principal")
  unidade: string               // Unidade de medida (ex: "°C", "Pa", "%RH")
  protocolo_origem: '4-20ma' | 'rs485' | 'i2c'  // Protocolo de comunicação
  measurement_type: { code: string; name: string }  // Tipo de medição
  area: { area_code: string; name: string; category: string }  // Localização
}
```

### Mapeamento Odoo (Fase 3)
- `sensor_code` ← `sensor_monitor.sensor.code`
- `name` ← `sensor_monitor.sensor.name`
- `unidade` ← `sensor_monitor.sensor.unit` (ou `measurement.type.unit`)
- `protocolo_origem` ← `sensor_monitor.sensor.protocol`
- `measurement_type` ← `measurement.type` (relação M2O em `sensor_monitor.sensor`)
- `area` ← `area` (relação M2O em `sensor_monitor.sensor`)

---

## 2. Threshold

Limites (mínimo e máximo) para alarmes, com marcação se é padrão regulatório.

### Definição TypeScript
```ts
type Threshold = {
  sensor_id: string                          // ID do sensor associado
  limite_min: number                         // Limite inferior
  limite_max: number                         // Limite superior
  is_valor_padrao_regulatorio: boolean       // Se é padrão regulatório
}
```

### Mapeamento Odoo (Fase 3)
- Lido de `alarm.threshold` (relação N2M em `sensor_monitor.sensor`)
- `sensor_id` ← `sensor_id.id`
- `limite_min` ← `threshold_min`
- `limite_max` ← `threshold_max`
- `is_valor_padrao_regulatorio` ← `is_regulatory_default` (ou similar)

---

## 3. HistoryResponse

Resposta de leitura histórica de sensor (pontos em série temporal).

### Definição TypeScript
```ts
type HistoryPoint = 
  | { ts: number; value: number }                           // Raw point
  | { ts: number; min: number; max: number; avg: number }   // Aggregated

type HistoryResponse = {
  sensor_code: string                // Código do sensor
  window: '1h' | '24h' | '7d' | '30d'  // Janela temporal requisitada
  resolution: 'raw' | 'agg'          // Tipo de resolução retornada
  points: HistoryPoint[]             // Série de pontos
}
```

### Mapeamento Odoo (Fase 3)
- Resposta de API que lê histórico do Timescale (banco de séries temporais)
- Para janelas curtas (1h) → `resolution: 'raw'` (ponto por ponto)
- Para janelas longas (24h, 7d, 30d) → `resolution: 'agg'` (agregado min/max/avg)
- `ts` ← timestamp em milissegundos (Unix * 1000)
- `value` / `min/max/avg` ← leitura do sensor

---

## 4. LivePoint

Ponto de leitura em tempo real (SSE/WebSocket feed).

### Definição TypeScript
```ts
type AlarmState = 'ok' | 'warn' | 'crit'

type LivePoint = {
  sensor_code: string              // Código do sensor
  ts: number                        // Timestamp em milissegundos
  value: number                     // Valor lido
  alarm_state: AlarmState           // Estado de alarme (computado ou no feed)
}
```

### Mapeamento Odoo (Fase 3)
- Publicado via SSE (Server-Sent Events) ou WebSocket feed em tempo real
- `sensor_code` ← código do sensor
- `ts` ← timestamp do evento
- `value` ← leitura atual
- `alarm_state` ← computado localmente por `computeStatus()` ou enviado do servidor

---

## Notas Implementação

1. **TypeScript**: Todos os shapes são exportados de `src/lib/types.ts` para reutilização.
2. **Status Computation**: O estado de alarme (`ok|warn|crit`) é calculado por `computeStatus(value, threshold)` em `src/lib/status.ts`.
3. **Null-safety**: `Threshold` pode ser `null` para sensores sem limite configurado (estado: `'unknown'`).
4. **Fase 3 Compliance**: Backend Odoo deve serializar objetos respeitando exatamente estas estruturas para garantir compatibilidade.
