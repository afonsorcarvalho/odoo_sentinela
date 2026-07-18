# Dashboard Visual Redesign (AFR Design System) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recriar o dashboard Sentinela CME com o AFR Design System (handoff em `docs/superpowers/Dashboard Sentinela CME/`), fundindo Overview + Detalhe do Sensor numa única tela real (`/`), com painel de alarmes, topbar e dados 100% via API real (não mock).

**Architecture:** Backend ganha 1 endpoint novo (`GET /alarmes`). Frontend ganha adapters `real/` para `metaApi`/`historyApi`/`liveApi`/`alarmApi` (mesmo padrão já usado por `real/authApi.ts`), troca os valores dos tokens CSS existentes (mantém os NOMES `--color-*` — ver Global Constraints), e funde `OverviewPage`+`SensorDetailPage`+`AreaPage` numa `DashboardPage` única controlada por querystring (`?area=&sensor=`).

**Tech Stack:** FastAPI + Odoo XML-RPC + TimescaleDB (backend); React 19 + React Router 7 + TanStack Query + Tailwind v4 (CSS-first `@theme`) + ECharts (frontend); Vitest + Testing Library; pytest + `TestClient` contra Odoo/Timescale reais (backend).

## Global Constraints

- **Não renomear tokens CSS.** Todo componente existente referencia `var(--color-bg|surface|panel|ink|muted|line|primary|good|warn|crit)` e `var(--font-mono)`. Esta migração troca só os VALORES desses tokens pelos do AFR — nomes ficam iguais. Renomear quebraria dezenas de componentes já testados sem ganho.
- **`--color-ink` não muda de forma.** Fica `oklch(L 0 none)` nos dois temas (valores atuais, inalterados) — é o token que participa de `color-mix(in oklch, ...)` em `statusVisuals.tsx`/`ThresholdBadge.tsx`, e `none` (hue "powerless") é o que evita o bug já corrigido no projeto (crit→roxo, warn→verde por interpolação de matiz). Os operandos de status (`--color-good/warn/crit/primary`) PODEM usar hex direto do handoff — `color-mix(in oklch, ...)` converte para oklch internamente e adota o hue do outro operando quando um deles é `none`, então a regra de segurança não depende do formato do token de status, só do `--color-ink`.
- **Toque ≥44px** (`min-h-11`/`min-w-11`) em todo controle interativo.
- **Estado nunca só por cor** — sempre cor + ícone + texto (`StatusIcon`/`LABELS` já existentes, reusar).
- **`motion-reduce:transition-none`** em toda transição nova.
- **Sem `box-shadow` de elevação** — só `--shadow-menu` em tooltip do gráfico e toasts.
- **Testes de frontend sempre mock**, mesmo com `.env.local` real (`vite.config.ts` já força `VITE_API_MODE=mock` no ambiente de teste — não precisa de guarda extra).
- **Testes de backend rodam contra Odoo/Timescale reais** (`TestClient` sem mock) — os serviços do `docker-compose.yml` precisam estar de pé (`docker compose up -d`) antes de `pytest`.
- **Escopo deliberadamente cortado** (ver spec `docs/superpowers/specs/2026-07-18-dashboard-visual-redesign-design.md` §9): "Registro íntegro" é health-flag simples (não verificação criptográfica da cadeia de ledger); modo "Ao vivo" é polling (não streaming); janela de tempo do gráfico continua sendo o seletor 1h/24h/7d/30d já existente (não o toggle binário "Ao vivo/Dia todo" do handoff — o seletor atual é estritamente mais capaz); selo "assinado na origem" por leitura fica DE FORA (sem campo de API pra isso ainda); nome da unidade no topbar vem de `VITE_UNIT_NAME` (env), não de um campo de API novo.

## Amendment (post-merge, antes da execução)

Entre o commit da spec e do plano, uma sessão paralela implementou (branch `feat/frontend-real-adapters`,
merged em master `5d5f23b`) exatamente o que as Tasks 2–4 originais planejavam, com nomes diferentes:

| Este plano previa | O que já existe em master (usar) |
|---|---|
| `frontend/src/lib/api/authToken.ts` (`getAuthToken`/`setAuthToken`/`clearAuthToken`) | `TOKEN_STORAGE_KEY` exportado de `frontend/src/lib/useAuth.tsx` — lido direto via `localStorage.getItem(TOKEN_STORAGE_KEY)` |
| `frontend/src/lib/api/real/httpClient.ts` (`authedGet`) | `frontend/src/lib/api/real/http.ts` (`authFetchJson<T>(path)`) |
| `frontend/src/lib/api/real/metaApi.ts` | já existe, mesmo nome/local, já wired em `index.ts` |
| `frontend/src/lib/api/real/historyApi.ts` | já existe, mesmo nome/local, já wired em `index.ts` |

**Tasks 2, 3 e 4 abaixo estão SKIP — não dispachar.** Ficam no plano só como registro do que foi
substituído. **Tasks 5, 6 e 7 foram reescritas** (ver os blocos "SUBSTITUÍDO" dentro de cada uma) pra
consumir `authFetchJson`/`./http` em vez de `authedGet`/`./httpClient`, e pra Task 7 fazer um ADD incremental
em cima do `index.ts` já real (não uma reescrita completa — o arquivo atual já liga `authApi`/`metaApi`/
`historyApi` reais).

---

## Task 1: Backend — endpoint `GET /alarmes`

**Files:**
- Create: `api/alarmes.py`
- Modify: `api/main.py:1-20` (registrar router)
- Test: `api/tests/test_alarmes.py`

**Interfaces:**
- Produces: `GET /alarmes` (autenticado, `Authorization: Bearer <token>`) → `200` com lista JSON `[{id, sensor_code, area: {area_code, name}, tipo_violacao, status, timestamp_deteccao, valor_lido, limite_configurado_snapshot, data_resolucao}]`, ordenada por `timestamp_deteccao` desc, limitada a 50. Sem token → `401`.

- [ ] **Step 1: Escrever o teste**

```python
# api/tests/test_alarmes.py
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from api.main import app
from api.odoo import get_cliente_servico
from ingestao import odoo_cliente

client = TestClient(app)


def _headers():
    resposta = client.post('/auth/login', json={'usuario': 'admin', 'senha': 'admin'})
    token = resposta.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def _criar_evento(cliente, sensor_code, status='aberto'):
    sensor_ids = odoo_cliente.executar(
        cliente, 'sensor_monitor.sensor', 'search', [('sensor_code', '=', sensor_code)],
    )
    sensor = odoo_cliente.executar(
        cliente, 'sensor_monitor.sensor', 'read', [sensor_ids[0]], fields=['area_id'],
    )[0]
    return odoo_cliente.executar(
        cliente, 'sensor_monitor.alarm.event', 'create', {
            'sensor_id': sensor_ids[0],
            'area_id': sensor['area_id'][0],
            'timestamp_deteccao': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
            'valor_lido': 99.9,
            'tipo_violacao': 'acima_limite',
            'limite_configurado_snapshot': 30.0,
            'status': status,
        },
    )


def test_listar_alarmes_sem_token_retorna_401():
    resposta = client.get('/alarmes')
    assert resposta.status_code == 401


def test_listar_alarmes_com_token_inclui_evento_criado():
    cliente = get_cliente_servico()
    _criar_evento(cliente, 'SNR-SIM-TEMP-01')

    resposta = client.get('/alarmes', headers=_headers())
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert len(corpo) > 0
    evento = corpo[0]
    assert evento['sensor_code'] == 'SNR-SIM-TEMP-01'
    assert evento['area']['area_code']
    assert evento['status'] == 'aberto'
    assert evento['tipo_violacao'] == 'acima_limite'


def test_listar_alarmes_ordenado_por_timestamp_desc():
    cliente = get_cliente_servico()
    _criar_evento(cliente, 'SNR-SIM-TEMP-01')
    _criar_evento(cliente, 'SNR-SIM-PRES-01')

    resposta = client.get('/alarmes', headers=_headers())
    timestamps = [e['timestamp_deteccao'] for e in resposta.json()]
    assert timestamps == sorted(timestamps, reverse=True)
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `docker compose up -d && pytest api/tests/test_alarmes.py -v`
Expected: FAIL (`ModuleNotFoundError` ou `404` — rota não existe ainda).

- [ ] **Step 3: Implementar o endpoint**

```python
# api/alarmes.py
from fastapi import APIRouter, Depends

from ingestao import odoo_cliente

from .auth import verificar_token
from .odoo import get_cliente_servico

router = APIRouter()

_CAMPOS_EVENTO = [
    'sensor_id', 'area_id', 'tipo_violacao', 'status',
    'timestamp_deteccao', 'valor_lido', 'limite_configurado_snapshot', 'data_resolucao',
]


def _serializar_evento(cliente, evento):
    sensor = odoo_cliente.executar(
        cliente, 'sensor_monitor.sensor', 'read', [evento['sensor_id'][0]], fields=['sensor_code'],
    )[0]
    area = odoo_cliente.executar(
        cliente, 'sensor_monitor.area', 'read', [evento['area_id'][0]], fields=['area_code', 'name'],
    )[0]
    return {
        'id': evento['id'],
        'sensor_code': sensor['sensor_code'],
        'area': {'area_code': area['area_code'], 'name': area['name']},
        'tipo_violacao': evento['tipo_violacao'],
        'status': evento['status'],
        'timestamp_deteccao': evento['timestamp_deteccao'],
        'valor_lido': evento['valor_lido'],
        'limite_configurado_snapshot': evento['limite_configurado_snapshot'],
        'data_resolucao': evento['data_resolucao'],
    }


@router.get('/alarmes')
def get_alarmes(cliente=Depends(get_cliente_servico), _claims=Depends(verificar_token)):
    eventos = odoo_cliente.executar(
        cliente, 'sensor_monitor.alarm.event', 'search_read', [],
        fields=_CAMPOS_EVENTO, order='timestamp_deteccao desc', limit=50,
    )
    return [_serializar_evento(cliente, e) for e in eventos]
```

```python
# api/main.py — adicionar ao lado das outras include_router (linha ~18-20)
from . import alarmes
...
app.include_router(alarmes.router)
```

- [ ] **Step 4: Rodar e confirmar sucesso**

Run: `pytest api/tests/test_alarmes.py -v`
Expected: PASS (3 testes).

- [ ] **Step 5: Commit**

```bash
git add api/alarmes.py api/main.py api/tests/test_alarmes.py
git commit -m "feat: endpoint GET /alarmes (leitura de eventos de alarme)"
```

---

## Task 2 (SKIP): helper de token de auth

**SKIP — não dispachar.** Já entregue por `frontend/src/lib/useAuth.tsx` (`TOKEN_STORAGE_KEY` exportado),
commit `1d392ac` em master. Usar `TOKEN_STORAGE_KEY` de `useAuth.tsx` em vez de criar `authToken.ts`.

---

## Task 3 (SKIP): httpClient + real/metaApi.ts

**SKIP — não dispachar.** Já entregue como `frontend/src/lib/api/real/http.ts` (`authFetchJson<T>(path)`)
+ `frontend/src/lib/api/real/metaApi.ts`, commits `1d392ac`/`c5cdfbb` em master.

---

## Task 4 (SKIP): real/historyApi.ts

**SKIP — não dispachar.** Já entregue como `frontend/src/lib/api/real/historyApi.ts`, commit `fc7a472`
em master, já wired em `index.ts`.

---

## Task 5: Frontend — `real/liveApi.ts` (polling)

**Files:**
- Create: `frontend/src/lib/api/real/liveApi.ts`
- Test: `frontend/src/lib/api/real/liveApi.test.ts`

**Interfaces:**
- Consumes: `realMetaApi.getThreshold` (já existe em `frontend/src/lib/api/real/metaApi.ts`), `realHistoryApi.getHistory` (já existe em `frontend/src/lib/api/real/historyApi.ts`), `computeStatus` de `../../status` (já existe).
- Produces: `realLiveApi: LiveApi` (usado pelo `index.ts` na Task 7). Sem endpoint de streaming dedicado — faz polling de `historico?window=1h` a cada 3s e emite o último ponto.

- [ ] **Step 1: Escrever o teste**

```typescript
// frontend/src/lib/api/real/liveApi.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { realLiveApi } from './liveApi'
import { realMetaApi } from './metaApi'
import { realHistoryApi } from './historyApi'

vi.mock('./metaApi', () => ({ realMetaApi: { getThreshold: vi.fn() } }))
vi.mock('./historyApi', () => ({ realHistoryApi: { getHistory: vi.fn() } }))

beforeEach(() => {
  vi.useFakeTimers()
  vi.mocked(realMetaApi.getThreshold).mockResolvedValue({
    sensor_id: 'A', limite_min: 10, limite_max: 20, is_valor_padrao_regulatorio: false,
  })
  vi.mocked(realHistoryApi.getHistory).mockResolvedValue({
    sensor_code: 'A', window: '1h', resolution: 'raw', points: [{ ts: 1000, value: 15 }],
  })
})
afterEach(() => vi.useRealTimers())

describe('realLiveApi', () => {
  it('subscribe busca o historico e emite o ultimo ponto com alarm_state derivado do threshold', async () => {
    const cb = vi.fn()
    realLiveApi.subscribe('A', cb)
    await vi.runOnlyPendingTimersAsync()

    expect(cb).toHaveBeenCalledWith({ sensor_code: 'A', ts: 1000, value: 15, alarm_state: 'ok' })
  })

  it('unsubscribe para o polling', async () => {
    const cb = vi.fn()
    const unsub = realLiveApi.subscribe('A', cb)
    await vi.runOnlyPendingTimersAsync()
    cb.mockClear()
    unsub()

    await vi.advanceTimersByTimeAsync(10_000)
    expect(cb).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `cd frontend && npx vitest run src/lib/api/real/liveApi.test.ts`
Expected: FAIL (módulo não existe).

- [ ] **Step 3: Implementar**

```typescript
// frontend/src/lib/api/real/liveApi.ts
import type { LiveApi } from '../contracts'
import type { LivePoint, Threshold } from '../../types'
import { computeStatus } from '../../status'
import { realMetaApi } from './metaApi'
import { realHistoryApi } from './historyApi'

const POLL_MS = 3000

export const realLiveApi: LiveApi = {
  subscribe(sensor_code, cb) {
    let cancelled = false
    let threshold: Threshold | null = null
    realMetaApi.getThreshold(sensor_code).then((t) => { threshold = t })

    const tick = async () => {
      const history = await realHistoryApi.getHistory(sensor_code, '1h')
      const last = history.points[history.points.length - 1]
      if (!last || cancelled) return
      const value = 'value' in last ? last.value : last.avg
      const state = computeStatus(value, threshold).state
      const alarm_state = state === 'unknown' ? 'ok' : state
      cb({ sensor_code, ts: last.ts, value, alarm_state } satisfies LivePoint)
    }

    tick()
    const id = setInterval(tick, POLL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  },
}
```

- [ ] **Step 4: Rodar e confirmar sucesso**

Run: `cd frontend && npx vitest run src/lib/api/real/liveApi.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api/real/liveApi.ts frontend/src/lib/api/real/liveApi.test.ts
git commit -m "feat(frontend): realLiveApi via polling de historico (sem streaming ainda)"
```

---

## Task 6: Frontend — contrato + adapters de Alarmes

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Modify: `frontend/src/lib/api/contracts.ts`
- Create: `frontend/src/lib/api/mock/alarmApi.ts`
- Create: `frontend/src/lib/api/real/alarmApi.ts`
- Test: `frontend/src/lib/api/mock/alarmApi.test.ts`
- Test: `frontend/src/lib/api/real/alarmApi.test.ts`

**Interfaces:**
- Produces: `AlarmEvent` type, `AlarmApi.listAlarms(): Promise<AlarmEvent[]>`, `mockAlarmApi`, `realAlarmApi` — usados pelo `index.ts` (Task 7) e por `useAlarms()` (Task 14).

- [ ] **Step 1: Adicionar o tipo em `types.ts`**

```typescript
// frontend/src/lib/types.ts — adicionar ao final do arquivo
export type AlarmEventStatus = 'aberto' | 'reconhecido' | 'resolvido'
export type AlarmTipoViolacao = 'acima_limite' | 'abaixo_limite' | 'sensor_offline' | 'erro_leitura'

export type AlarmEvent = {
  id: number
  sensor_code: string
  area: { area_code: string; name: string }
  tipo_violacao: AlarmTipoViolacao
  status: AlarmEventStatus
  timestamp_deteccao: string
  valor_lido: number | null
  limite_configurado_snapshot: number | null
  data_resolucao: string | null
}
```

- [ ] **Step 2: Adicionar o contrato em `contracts.ts`**

```typescript
// frontend/src/lib/api/contracts.ts — adicionar import e tipo
import type { SensorMeta, Threshold, HistoryResponse, LivePoint, Window, AlarmEvent } from '../types'

export type AlarmApi = {
  listAlarms(): Promise<AlarmEvent[]>
}
```

- [ ] **Step 3: Escrever os testes**

```typescript
// frontend/src/lib/api/mock/alarmApi.test.ts
import { describe, it, expect } from 'vitest'
import { mockAlarmApi } from './alarmApi'

describe('mockAlarmApi', () => {
  it('listAlarms devolve ao menos 1 evento aberto e 1 resolvido, mais recente primeiro', async () => {
    const alarms = await mockAlarmApi.listAlarms()
    expect(alarms.some((a) => a.status === 'aberto')).toBe(true)
    expect(alarms.some((a) => a.status === 'resolvido')).toBe(true)
    const timestamps = alarms.map((a) => a.timestamp_deteccao)
    expect(timestamps).toEqual([...timestamps].sort().reverse())
  })
})
```

```typescript
// frontend/src/lib/api/real/alarmApi.test.ts
import { describe, it, expect, vi, afterEach } from 'vitest'
import { realAlarmApi } from './alarmApi'

afterEach(() => vi.unstubAllGlobals())

describe('realAlarmApi', () => {
  it('listAlarms faz GET /alarmes', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => [] })
    vi.stubGlobal('fetch', mockFetch)
    await realAlarmApi.listAlarms()
    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('/alarmes'), expect.anything())
  })
})
```

- [ ] **Step 4: Rodar e confirmar falha**

Run: `cd frontend && npx vitest run src/lib/api/mock/alarmApi.test.ts src/lib/api/real/alarmApi.test.ts`
Expected: FAIL (módulos não existem).

- [ ] **Step 5: Implementar**

```typescript
// frontend/src/lib/api/mock/alarmApi.ts
import type { AlarmApi } from '../contracts'
import type { AlarmEvent } from '../../types'

const NOW = 1_700_000_000_000

const FIXTURE: AlarmEvent[] = [
  {
    id: 2, sensor_code: 'PRESS-EXP-01', area: { area_code: 'EXPURGO', name: 'Expurgo' },
    tipo_violacao: 'abaixo_limite', status: 'aberto',
    timestamp_deteccao: new Date(NOW).toISOString(),
    valor_lido: -1.7, limite_configurado_snapshot: -2.5, data_resolucao: null,
  },
  {
    id: 1, sensor_code: 'TEMP-PRE-01', area: { area_code: 'PREPARO', name: 'Preparo' },
    tipo_violacao: 'acima_limite', status: 'resolvido',
    timestamp_deteccao: new Date(NOW - 600_000).toISOString(),
    valor_lido: 24.1, limite_configurado_snapshot: 23.0, data_resolucao: new Date(NOW - 300_000).toISOString(),
  },
]

export const mockAlarmApi: AlarmApi = {
  async listAlarms() {
    return FIXTURE
  },
}
```

```typescript
// frontend/src/lib/api/real/alarmApi.ts
import type { AlarmApi } from '../contracts'
import type { AlarmEvent } from '../../types'
import { authFetchJson } from './http'

export const realAlarmApi: AlarmApi = {
  listAlarms: () => authFetchJson<AlarmEvent[]>('/alarmes'),
}
```

- [ ] **Step 6: Rodar e confirmar sucesso**

Run: `cd frontend && npx vitest run src/lib/api/mock/alarmApi.test.ts src/lib/api/real/alarmApi.test.ts`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/lib/api/contracts.ts frontend/src/lib/api/mock/alarmApi.ts frontend/src/lib/api/real/alarmApi.ts frontend/src/lib/api/mock/alarmApi.test.ts frontend/src/lib/api/real/alarmApi.test.ts
git commit -m "feat(frontend): contrato AlarmApi + adapters mock/real"
```

---

## Task 7: Frontend — ligar tudo em `index.ts` (modo real) + flag de demo

**Files:**
- Modify: `frontend/src/lib/api/index.ts`
- Create: `frontend/src/lib/demoMode.ts`
- Test: `frontend/src/lib/api/index.test.ts` (novo)
- Test: `frontend/src/lib/demoMode.test.ts`

**Interfaces:**
- Consumes: `realMetaApi`/`realHistoryApi` (já existem em master), `realLiveApi` (Task 5), `realAlarmApi` (Task 6).
- Produces: `metaApi`/`historyApi`/`liveApi`/`alarmApi` exportados de `index.ts` já resolvidos pelo modo; `isDemoMode(): boolean` (usado pela Task 17).
- Nota: `index.ts` atual (master) já liga `authApi`/`metaApi`/`historyApi` reais com um ternário inline por
  export (não uma const `useReal` compartilhada) e um comentário próprio. O Step 3 abaixo substitui o
  arquivo inteiro por uma versão equivalente + `liveApi`/`alarmApi` — funcionalmente idêntica pro que já
  existe, só reorganizada. Isso é intencional, não uma regressão.

- [ ] **Step 1: Escrever os testes**

```typescript
// frontend/src/lib/demoMode.test.ts
import { describe, it, expect, vi, afterEach } from 'vitest'
import { isDemoMode } from './demoMode'

afterEach(() => vi.unstubAllEnvs())

describe('isDemoMode', () => {
  it('falso quando VITE_DEMO_MODE nao esta definido', () => {
    expect(isDemoMode()).toBe(false)
  })
})
```

```typescript
// frontend/src/lib/api/index.test.ts
import { describe, it, expect } from 'vitest'
import { metaApi, historyApi, liveApi, authApi, alarmApi } from './index'

// Em teste, VITE_API_MODE e forcado para 'mock' (vite.config.ts) — este teste
// so confirma que o barril exporta todos os adapters exigidos pelo app.
describe('api barrel', () => {
  it('exporta os 5 adapters', () => {
    expect(metaApi).toBeDefined()
    expect(historyApi).toBeDefined()
    expect(liveApi).toBeDefined()
    expect(authApi).toBeDefined()
    expect(alarmApi).toBeDefined()
  })
})
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `cd frontend && npx vitest run src/lib/demoMode.test.ts src/lib/api/index.test.ts`
Expected: FAIL (`demoMode.ts` não existe; `alarmApi` não exportado de `index.ts`).

- [ ] **Step 3: Implementar**

```typescript
// frontend/src/lib/demoMode.ts
export function isDemoMode(): boolean {
  return import.meta.env.VITE_DEMO_MODE === 'true'
}
```

```typescript
// frontend/src/lib/api/index.ts — substituir integralmente
import type { MetaApi, HistoryApi, LiveApi, AuthApi, AlarmApi } from './contracts'
import { mockMetaApi } from './mock/metaApi'
import { mockHistoryApi } from './mock/historyApi'
import { mockLiveApi } from './mock/liveApi'
import { mockAuthApi } from './mock/authApi'
import { mockAlarmApi } from './mock/alarmApi'
import { realAuthApi } from './real/authApi'
import { realMetaApi } from './real/metaApi'
import { realHistoryApi } from './real/historyApi'
import { realLiveApi } from './real/liveApi'
import { realAlarmApi } from './real/alarmApi'

const mode = import.meta.env.VITE_API_MODE ?? 'mock'
if (mode !== 'real' && mode !== 'mock') {
  console.warn(`VITE_API_MODE=${mode} nao reconhecido; usando mock para todos os adapters`)
}

const useReal = mode === 'real'

export const authApi: AuthApi = useReal ? realAuthApi : mockAuthApi
export const metaApi: MetaApi = useReal ? realMetaApi : mockMetaApi
export const historyApi: HistoryApi = useReal ? realHistoryApi : mockHistoryApi
export const liveApi: LiveApi = useReal ? realLiveApi : mockLiveApi
export const alarmApi: AlarmApi = useReal ? realAlarmApi : mockAlarmApi
```

- [ ] **Step 4: Rodar e confirmar sucesso**

Run: `cd frontend && npx vitest run`
Expected: PASS (suite inteira — este passo troca o barril usado por toda a app, então roda tudo).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api/index.ts frontend/src/lib/demoMode.ts frontend/src/lib/demoMode.test.ts frontend/src/lib/api/index.test.ts
git commit -m "feat(frontend): liga metaApi/historyApi/liveApi/alarmApi reais quando VITE_API_MODE=real"
```

---

## Task 8: Tokens visuais AFR (`index.css`)

**Files:**
- Modify: `frontend/src/index.css`

**Interfaces:**
- Produces: valores novos para `--color-*`/`--font-mono` existentes + tokens novos `--color-good-soft`, `--color-warn-soft`, `--color-crit-soft`, `--color-line-strong`, `--shadow-menu`, `--font-sans`, classe `.theme-control` (substitui `.dark`). Consumido por todos os componentes já existentes (restyle automático) e pelos componentes novos das Tasks 10–15.

- [ ] **Step 1: Substituir o arquivo**

```css
/* frontend/src/index.css */
@import "tailwindcss";
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

@theme {
  /* ---------- Document (claro) — default, mesmo papel de :root de antes ---------- */
  --color-bg:              #f7f9fb;
  --color-surface:         #ffffff;
  --color-panel:           #f1f4f7;
  /* Matiz "none" (nao 0): color-mix(in oklch, ...) interpola matiz pelo arco
     mais curto entre os dois endpoints. Com ink carregando um matiz de baixa
     saturacao mas nao-zero, misturar status crit/warn com ele fazia o
     resultado atravessar a roda de cores pelo lado errado -- crit (vermelho)
     virava roxo, warn (ambar) virava verde, podendo ser confundido com o
     estado 'ok'. A palavra-chave CSS `none` marca o matiz como "ausente"
     (powerless hue, CSS Color 4) e faz color-mix usar so o matiz do operando
     de status, sem nenhum desvio. IMPORTANTE: chroma 0 sozinho NAO basta --
     `oklch(L 0 0)` tem matiz 0deg EXPLICITO (nao "ausente"), e ainda causa
     desvio; só `oklch(L 0 none)` funciona. Ver components/statusVisuals.tsx.
     Este token NAO muda nesta migracao -- so os operandos de status abaixo
     trocam para os valores AFR (hex e seguro: color-mix converte p/ oklch
     internamente e adota o hue do operando nao-"none"). */
  --color-ink:              oklch(0.24 0 none);
  --color-muted:            #4a5968;
  --color-line:             #e2e7ec;
  --color-line-strong:      #c9d1da;
  --color-primary:          #008a9b;
  --color-good:             #14794d;
  --color-good-soft:        #def4e9;
  --color-warn:             #a86b00;
  --color-warn-soft:        #fbecd0;
  --color-crit:             #c2241a;
  --color-crit-soft:        #fbe2df;
  --shadow-menu:            0 8px 24px rgb(16 24 32 / 0.10), 0 0 0 1px var(--color-line);
  --font-mono: 'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, monospace;
  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

/* ---------- Control (escuro) — tema padrao recomendado p/ monitoramento continuo ---------- */
.theme-control {
  --color-bg:              #0b1620;
  --color-surface:         #101f2c;
  --color-panel:           #132635;
  --color-ink:              oklch(0.95 0 none); /* mesma razao do bloco claro acima */
  --color-muted:            #a8b7c6;
  --color-line:             #22384d;
  --color-line-strong:      #31506c;
  --color-primary:          #00b3c7;
  --color-good:             #22c57a;
  --color-good-soft:        #0e2e20;
  --color-warn:             #f5b23d;
  --color-warn-soft:        #2e2209;
  --color-crit:             #ef4444;
  --color-crit-soft:        #2e0b0b;
  --shadow-menu:            0 8px 24px rgb(0 0 0 / 0.45), 0 0 0 1px var(--color-line);
}

body {
  background: var(--color-bg);
  color: var(--color-ink);
  font-family: var(--font-sans);
}
```

- [ ] **Step 2: Rodar toda a suite (visual não é testável por vitest, mas garante que nada de lógica quebrou por causa do CSS)**

Run: `cd frontend && npx vitest run`
Expected: PASS (suite inteira — troca de tokens não deveria quebrar assert de comportamento, só de aparência).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/index.css
git commit -m "feat(frontend): tokens visuais AFR Design System (valores; nomes de token inalterados)"
```

---

## Task 9: `ThemeToggle` — default escuro (Control) + classe renomeada

**Files:**
- Modify: `frontend/src/components/ThemeToggle.tsx`
- Test: `frontend/src/components/ThemeToggle.test.tsx` (novo)

**Interfaces:**
- Consumes: classe CSS `.theme-control` (Task 8).
- Produces: `<ThemeToggle />` — inalterado externamente (sem props), usado pelo `Topbar` (Task 13).

- [ ] **Step 1: Escrever o teste**

```typescript
// frontend/src/components/ThemeToggle.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, afterEach } from 'vitest'
import { ThemeToggle } from './ThemeToggle'

afterEach(() => {
  document.documentElement.classList.remove('theme-control')
})

describe('ThemeToggle', () => {
  it('tema Control (escuro) e o default: aplica a classe theme-control ao montar', () => {
    render(<ThemeToggle />)
    expect(document.documentElement.classList.contains('theme-control')).toBe(true)
  })

  it('clicar alterna para Document (claro): remove a classe', () => {
    render(<ThemeToggle />)
    fireEvent.click(screen.getByRole('button'))
    expect(document.documentElement.classList.contains('theme-control')).toBe(false)
  })

  it('alvo de toque tem no minimo 44px (min-h-11)', () => {
    render(<ThemeToggle />)
    expect(screen.getByRole('button').className).toContain('min-h-11')
  })
})
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `cd frontend && npx vitest run src/components/ThemeToggle.test.tsx`
Expected: FAIL (comportamento atual usa `prefersDark()`/classe `dark`, não `theme-control` por default).

- [ ] **Step 3: Implementar**

```typescript
// frontend/src/components/ThemeToggle.tsx — só a lógica de estado/classe muda,
// os ícones SunIcon/MoonIcon ficam iguais.
import { useEffect, useState } from 'react'

function SunIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <circle cx="8" cy="8" r="3.4" />
      <path
        strokeLinecap="round"
        d="M8 1.2v1.6M8 13.2v1.6M14.8 8h-1.6M2.8 8H1.2M12.7 3.3l-1.1 1.1M4.4 11.6l-1.1 1.1M12.7 12.7l-1.1-1.1M4.4 4.4 3.3 3.3"
      />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M13.6 10.2A6 6 0 0 1 5.8 2.4a6.4 6.4 0 1 0 7.8 7.8Z" />
    </svg>
  )
}

export function ThemeToggle() {
  // Control (escuro) e o tema padrao recomendado p/ monitoramento continuo —
  // nao segue mais prefers-color-scheme do SO.
  const [control, setControl] = useState(true)

  useEffect(() => {
    document.documentElement.classList.toggle('theme-control', control)
  }, [control])

  return (
    <button
      type="button"
      onClick={() => setControl((c) => !c)}
      className="flex min-h-11 items-center gap-2 rounded-md px-3 py-1.5 text-sm font-semibold outline-none transition-colors duration-200 ease-out hover:text-[var(--color-ink)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] motion-reduce:transition-none"
      style={{ border: '1px solid var(--color-line)', color: 'var(--color-muted)' }}
      aria-pressed={control}
      aria-label={control ? 'Trocar para tema claro' : 'Trocar para tema escuro'}
    >
      {control ? <SunIcon /> : <MoonIcon />}
      <span>{control ? 'Claro' : 'Escuro'}</span>
    </button>
  )
}
```

- [ ] **Step 4: Rodar e confirmar sucesso**

Run: `cd frontend && npx vitest run src/components/ThemeToggle.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ThemeToggle.tsx frontend/src/components/ThemeToggle.test.tsx
git commit -m "feat(frontend): tema Control (escuro) como default; classe theme-control"
```

---

## Task 10: `StatusChip` e `StatusDot` (peças visuais reusáveis novas)

**Files:**
- Create: `frontend/src/components/StatusChip.tsx`
- Create: `frontend/src/components/StatusDot.tsx`
- Test: `frontend/src/components/StatusChip.test.tsx`
- Test: `frontend/src/components/StatusDot.test.tsx`

**Interfaces:**
- Consumes: `StatusResult['state']` de `../lib/status`, `LABELS`, `StatusIcon` (já existentes).
- Produces: `<StatusChip state={...} />` (pill: fundo `-soft`, texto sólido, ícone+label) e `<StatusDot state={...} />` (bolinha 6px, cor sólida) — usados por `AreaCard` (Task 11) e `AlarmPanel` (Task 14).

- [ ] **Step 1: Escrever os testes**

```typescript
// frontend/src/components/StatusChip.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { StatusChip } from './StatusChip'

describe('StatusChip', () => {
  it('mostra o texto do estado (nao so cor)', () => {
    render(<StatusChip state="crit" />)
    expect(screen.getByText('Fora da faixa')).toBeInTheDocument()
  })

  it('inclui um icone (svg) ao lado do texto', () => {
    const { container } = render(<StatusChip state="ok" />)
    expect(container.querySelector('svg')).not.toBeNull()
  })
})
```

```typescript
// frontend/src/components/StatusDot.test.tsx
import { render } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { StatusDot } from './StatusDot'

describe('StatusDot', () => {
  it('renderiza sem lancar, marcado aria-hidden (decorativo — status ja tem texto ao lado)', () => {
    const { container } = render(<StatusDot state="warn" />)
    expect(container.firstChild).toHaveAttribute('aria-hidden', 'true')
  })
})
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `cd frontend && npx vitest run src/components/StatusChip.test.tsx src/components/StatusDot.test.tsx`
Expected: FAIL (módulos não existem).

- [ ] **Step 3: Implementar**

```typescript
// frontend/src/components/StatusChip.tsx
import { LABELS, type StatusResult } from '../lib/status'
import { StatusIcon } from './statusVisuals'

type State = StatusResult['state']

const SOFT_BG: Record<State, string> = {
  ok: 'var(--color-good-soft)',
  warn: 'var(--color-warn-soft)',
  crit: 'var(--color-crit-soft)',
  unknown: 'var(--color-panel)',
}
const SOLID_TEXT: Record<State, string> = {
  ok: 'var(--color-good)',
  warn: 'var(--color-warn)',
  crit: 'var(--color-crit)',
  unknown: 'var(--color-muted)',
}

export function StatusChip({ state }: { state: State }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-bold"
      style={{ background: SOFT_BG[state], color: SOLID_TEXT[state] }}
    >
      <StatusIcon state={state} />
      {LABELS[state]}
    </span>
  )
}
```

```typescript
// frontend/src/components/StatusDot.tsx
import type { StatusResult } from '../lib/status'

type State = StatusResult['state']

const DOT: Record<State, string> = {
  ok: 'var(--color-good)',
  warn: 'var(--color-warn)',
  crit: 'var(--color-crit)',
  unknown: 'var(--color-muted)',
}

export function StatusDot({ state }: { state: State }) {
  return (
    <span
      aria-hidden="true"
      className="inline-block size-1.5 shrink-0 rounded-full"
      style={{ background: DOT[state] }}
    />
  )
}
```

- [ ] **Step 4: Rodar e confirmar sucesso**

Run: `cd frontend && npx vitest run src/components/StatusChip.test.tsx src/components/StatusDot.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/StatusChip.tsx frontend/src/components/StatusDot.tsx frontend/src/components/StatusChip.test.tsx frontend/src/components/StatusDot.test.tsx
git commit -m "feat(frontend): StatusChip e StatusDot (vocabulario visual do handoff AFR)"
```

---

## Task 11: `AreaCard` — reescrita (borda de status, chip, linhas de sensor clicáveis)

**Files:**
- Modify: `frontend/src/components/AreaCard.tsx`
- Modify: `frontend/src/components/AreaCard.test.tsx`

**Interfaces:**
- Consumes: `StatusChip`/`StatusDot` (Task 10).
- Produces: `<AreaCard group selectedSensorCode onSelectSensor hadAlarmToday thresholdsByCode liveByCode />` — troca de assinatura (antes era `<Link>` para `/area/:code`; agora é interativo dentro da própria página). Usado pela `DashboardPage` (Task 16).

- [ ] **Step 1: Reescrever o teste**

```typescript
// frontend/src/components/AreaCard.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { AreaCard } from './AreaCard'
import type { AreaGroup } from '../lib/aggregateStatus'

const group: AreaGroup = {
  area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' },
  sensors: [
    { sensor_code: 'TEMP-EXP-01', name: 'Temp', unidade: '°C', protocolo_origem: '4-20ma', measurement_type: { code: 'temperatura', name: 'Temperatura' }, area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' } },
    { sensor_code: 'PRESS-EXP-01', name: 'Pressao', unidade: 'Pa', protocolo_origem: '4-20ma', measurement_type: { code: 'pressao_diferencial', name: 'Pressão' }, area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' } },
  ],
}
const thresholdsByCode = {
  'TEMP-EXP-01': { sensor_id: 'TEMP-EXP-01', limite_min: 18, limite_max: 26, is_valor_padrao_regulatorio: false },
  'PRESS-EXP-01': { sensor_id: 'PRESS-EXP-01', limite_min: -15, limite_max: -2.5, is_valor_padrao_regulatorio: true },
}
const liveByCode = {
  'TEMP-EXP-01': { sensor_code: 'TEMP-EXP-01', ts: 1, value: 21, alarm_state: 'ok' as const },
  'PRESS-EXP-01': { sensor_code: 'PRESS-EXP-01', ts: 1, value: -3.6, alarm_state: 'ok' as const },
}

describe('AreaCard', () => {
  it('mostra nome da area e cada sensor com valor mono', () => {
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    expect(screen.getByText('Expurgo')).toBeInTheDocument()
    expect(screen.getByText('Temperatura')).toBeInTheDocument()
    expect(screen.getByText('21.0')).toBeInTheDocument()
  })

  it('clicar numa linha de sensor chama onSelectSensor com o codigo certo', () => {
    const onSelectSensor = vi.fn()
    render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={onSelectSensor} hadAlarmToday={false} />,
    )
    fireEvent.click(screen.getByText('Temperatura'))
    expect(onSelectSensor).toHaveBeenCalledWith('TEMP-EXP-01')
  })

  it('badge "!" aparece so quando hadAlarmToday=true', () => {
    const { rerender } = render(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday={false} />,
    )
    expect(screen.queryByLabelText('Houve não conformidade hoje')).not.toBeInTheDocument()

    rerender(
      <AreaCard group={group} thresholdsByCode={thresholdsByCode} liveByCode={liveByCode}
        selectedSensorCode={null} onSelectSensor={vi.fn()} hadAlarmToday />,
    )
    expect(screen.getByLabelText('Houve não conformidade hoje')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `cd frontend && npx vitest run src/components/AreaCard.test.tsx`
Expected: FAIL (assinatura antiga não bate).

- [ ] **Step 3: Implementar**

```typescript
// frontend/src/components/AreaCard.tsx
import { sensorDisplayState, worstAlarmState, type AreaGroup } from '../lib/aggregateStatus'
import { StatusChip } from './StatusChip'
import { StatusDot } from './StatusDot'
import { statusTextColor } from './statusVisuals'
import type { LivePoint, Threshold } from '../lib/types'

const BORDER_COLOR: Record<ReturnType<typeof worstAlarmState>, string> = {
  ok: 'var(--color-line)',
  warn: 'var(--color-warn)',
  crit: 'var(--color-crit)',
  unknown: 'var(--color-line)',
}

export function AreaCard({
  group,
  thresholdsByCode,
  liveByCode,
  selectedSensorCode,
  onSelectSensor,
  hadAlarmToday,
}: {
  group: AreaGroup
  thresholdsByCode: Record<string, Threshold | null | undefined>
  liveByCode: Record<string, LivePoint | undefined>
  selectedSensorCode: string | null
  onSelectSensor: (code: string) => void
  hadAlarmToday: boolean
}) {
  const states = group.sensors.map((s) =>
    sensorDisplayState(thresholdsByCode[s.sensor_code] ?? null, liveByCode[s.sensor_code]),
  )
  const aggregate = worstAlarmState(states)

  return (
    <div
      className="rounded-md p-4"
      style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-line)',
        borderLeft: `3px solid ${BORDER_COLOR[aggregate]}`,
      }}
      data-testid={`area-card-${group.area.area_code}`}
    >
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-base font-semibold" style={{ color: 'var(--color-ink)' }}>
          {group.area.name}
        </h2>
        <div className="flex items-center gap-2">
          {hadAlarmToday && (
            <span
              aria-label="Houve não conformidade hoje"
              className="flex size-[18px] items-center justify-center rounded-full text-xs font-bold"
              style={{ background: 'var(--color-warn-soft)', color: 'var(--color-warn)' }}
            >
              !
            </span>
          )}
          <StatusChip state={aggregate} />
        </div>
      </div>

      <div className="mt-3 border-t" style={{ borderColor: 'var(--color-line)' }} />

      <div className="mt-2 space-y-1">
        {group.sensors.map((s) => {
          const state = sensorDisplayState(thresholdsByCode[s.sensor_code] ?? null, liveByCode[s.sensor_code])
          const selected = s.sensor_code === selectedSensorCode
          const live = liveByCode[s.sensor_code]
          return (
            <button
              key={s.sensor_code}
              type="button"
              onClick={() => onSelectSensor(s.sensor_code)}
              className="flex min-h-11 w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left outline-none transition-colors duration-200 ease-out focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] motion-reduce:transition-none"
              style={{ background: selected ? 'var(--color-panel)' : 'transparent' }}
            >
              <span className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--color-muted)' }}>
                <StatusDot state={state} />
                {s.measurement_type.name}
              </span>
              <span
                className="font-mono text-sm font-semibold tabular-nums"
                style={{ color: state === 'ok' || state === 'unknown' ? 'var(--color-ink)' : statusTextColor(state) }}
              >
                {live ? live.value.toFixed(1) : '—'} {s.unidade}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Rodar e confirmar sucesso**

Run: `cd frontend && npx vitest run src/components/AreaCard.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/AreaCard.tsx frontend/src/components/AreaCard.test.tsx
git commit -m "feat(frontend): AreaCard reescrito (borda de status, chip, linhas de sensor clicaveis)"
```

---

## Task 12: `TimeSeriesChart` — faixa verde de conformidade

**Files:**
- Modify: `frontend/src/components/chartOption.ts`
- Modify: `frontend/src/components/chartOption.test.ts`

**Interfaces:**
- Produces: `buildChartOption(...)` ganha `markArea` verde translúcido entre `limite_min`/`limite_max`, além do `markLine` já existente. Assinatura da função não muda.

- [ ] **Step 1: Adicionar o teste**

```typescript
// frontend/src/components/chartOption.test.ts — adicionar este `it` ao describe existente
it('com threshold, series[0].markArea cobre limite_min..limite_max', () => {
  const threshold = { sensor_id: 'A', limite_min: 10, limite_max: 20, is_valor_padrao_regulatorio: false }
  const option = buildChartOption(undefined, threshold)
  const markArea = (option.series as any)[0].markArea
  expect(markArea.data).toEqual([[{ yAxis: 10 }, { yAxis: 20 }]])
})

it('sem threshold, series[0].markArea e undefined', () => {
  const option = buildChartOption(undefined, null)
  expect((option.series as any)[0].markArea).toBeUndefined()
})
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `cd frontend && npx vitest run src/components/chartOption.test.ts`
Expected: FAIL (`markArea` ainda não existe).

- [ ] **Step 3: Implementar**

```typescript
// frontend/src/components/chartOption.ts — dentro de buildChartOption, junto ao markLine existente
  const markArea = threshold
    ? {
        itemStyle: { color: 'var(--color-good-soft)', opacity: 0.5 },
        data: [[{ yAxis: threshold.limite_min }, { yAxis: threshold.limite_max }]],
      }
    : undefined
```

```typescript
// e no objeto series retornado, adicionar markArea ao lado de markLine:
    series: [{ type: 'line' as const, showSymbol: false, data, markLine, markArea }],
```

- [ ] **Step 4: Rodar e confirmar sucesso**

Run: `cd frontend && npx vitest run src/components/chartOption.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/chartOption.ts frontend/src/components/chartOption.test.ts
git commit -m "feat(frontend): faixa verde de conformidade no grafico (markArea)"
```

---

## Task 13: `Topbar` (marca, pill de unidade, selo, relógio, tema, logout)

**Files:**
- Create: `frontend/src/components/Topbar.tsx`
- Create: `frontend/src/components/LiveClock.tsx`
- Test: `frontend/src/components/Topbar.test.tsx`
- Test: `frontend/src/components/LiveClock.test.tsx`
- `frontend/src/components/HeaderActions.tsx` (absorvido pelo Topbar) — **NÃO deletar nesta task**, ver Step 4. Deletado só na Task 16, junto das páginas que ainda o importam.

**Interfaces:**
- Consumes: `ThemeToggle` (Task 9), `LogoutButton` (já existe).
- Produces: `<Topbar healthy unitName />` — usado pela `DashboardPage` (Task 16). `unitName` vem de `import.meta.env.VITE_UNIT_NAME` no chamador (não hardcoded dentro do componente, pra manter o componente puro/testável).

- [ ] **Step 1: Escrever os testes**

```typescript
// frontend/src/components/LiveClock.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { LiveClock } from './LiveClock'

afterEach(() => vi.useRealTimers())

describe('LiveClock', () => {
  it('mostra a hora atual no formato HH:MM:SS', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-18T15:19:00Z'))
    render(<LiveClock />)
    expect(screen.getByText(/\d{2}:\d{2}:\d{2}/)).toBeInTheDocument()
  })
})
```

```typescript
// frontend/src/components/Topbar.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { Topbar } from './Topbar'

describe('Topbar', () => {
  it('mostra a marca, o nome da unidade e o indicador AO VIVO', () => {
    render(<Topbar healthy unitName="Hospital Demonstração" />)
    expect(screen.getByText('Sentinela')).toBeInTheDocument()
    expect(screen.getByText('CME')).toBeInTheDocument()
    expect(screen.getByText('Hospital Demonstração')).toBeInTheDocument()
    expect(screen.getByText('AO VIVO')).toBeInTheDocument()
  })

  it('healthy=true mostra "Registro íntegro"; healthy=false nao mostra', () => {
    const { rerender } = render(<Topbar healthy unitName="X" />)
    expect(screen.getByText('Registro íntegro')).toBeInTheDocument()

    rerender(<Topbar healthy={false} unitName="X" />)
    expect(screen.queryByText('Registro íntegro')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `cd frontend && npx vitest run src/components/LiveClock.test.tsx src/components/Topbar.test.tsx`
Expected: FAIL (módulos não existem).

- [ ] **Step 3: Implementar**

```typescript
// frontend/src/components/LiveClock.tsx
import { useEffect, useState } from 'react'

function formatClock(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

export function LiveClock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(id)
  }, [])
  return (
    <span className="font-mono text-base font-semibold tabular-nums" style={{ color: 'var(--color-muted)' }}>
      {formatClock(now)}
    </span>
  )
}
```

```typescript
// frontend/src/components/Topbar.tsx
import { ThemeToggle } from './ThemeToggle'
import { LogoutButton } from './LogoutButton'
import { LiveClock } from './LiveClock'

function ShieldIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3Z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="m9 12 2 2 4-4" />
    </svg>
  )
}

export function Topbar({ healthy, unitName }: { healthy: boolean; unitName: string }) {
  return (
    <header
      className="sticky top-0 z-10 flex items-center gap-4 px-6 py-3"
      style={{ background: 'var(--color-surface)', borderBottom: '1px solid var(--color-line)' }}
    >
      <div className="flex items-center gap-2">
        <div
          className="flex size-[34px] items-center justify-center rounded-md"
          style={{ background: 'var(--color-primary)', color: 'var(--color-surface)' }}
        >
          <ShieldIcon />
        </div>
        <span className="text-lg font-bold" style={{ color: 'var(--color-ink)' }}>
          Sentinela
        </span>
        <span className="text-lg font-bold" style={{ color: 'var(--color-primary)' }}>
          CME
        </span>
      </div>

      <span
        className="rounded-full px-3 py-1 text-sm font-semibold"
        style={{ background: 'var(--color-panel)', border: '1px solid var(--color-line)', color: 'var(--color-ink)' }}
      >
        {unitName}
      </span>

      <div className="ml-auto flex items-center gap-3">
        {healthy && (
          <span
            className="rounded-md px-3 py-1.5 text-sm font-bold"
            style={{ background: 'var(--color-good-soft)', color: 'var(--color-good)' }}
          >
            Registro íntegro
          </span>
        )}

        <LiveClock />

        <span className="flex items-center gap-1.5 text-xs font-bold tracking-wide" style={{ color: 'var(--color-good)' }}>
          <span
            aria-hidden="true"
            className="size-[9px] rounded-full motion-safe:animate-pulse"
            style={{ background: 'var(--color-good)' }}
          />
          AO VIVO
        </span>

        <ThemeToggle />
        <LogoutButton />
      </div>
    </header>
  )
}
```

- [ ] **Step 4: NÃO deletar `HeaderActions.tsx` ainda**

Correção pós-merge: `HeaderActions.tsx` ainda é importado por `OverviewPage.tsx`/`AreaPage.tsx`/
`SensorDetailPage.tsx` (vivas até a Task 16). Deletar agora quebra o import dessas 3 páginas — ao
contrário do mismatch de props do `AreaCard` (Task 11), um módulo faltando é falha de resolução, não
silenciosa. `HeaderActions.tsx` só é deletado na Task 16, junto das páginas que o importam.

- [ ] **Step 5: Rodar e confirmar sucesso**

Run: `cd frontend && npx vitest run src/components/LiveClock.test.tsx src/components/Topbar.test.tsx`, depois `npx vitest run` (suite inteira — deve continuar 100% verde, `HeaderActions.tsx` não foi tocado).
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/Topbar.tsx frontend/src/components/LiveClock.tsx frontend/src/components/Topbar.test.tsx frontend/src/components/LiveClock.test.tsx
git commit -m "feat(frontend): Topbar (marca, unidade, selo, relogio, AO VIVO, tema, logout)"
```

---

## Task 14: `AlarmPanel` + `AlarmItem` + `useAlarms`

**Files:**
- Create: `frontend/src/components/AlarmPanel.tsx`
- Create: `frontend/src/components/AlarmItem.tsx`
- Modify: `frontend/src/lib/queries.ts`
- Test: `frontend/src/components/AlarmPanel.test.tsx`
- Test: `frontend/src/lib/queries.test.ts` (novo, se não existir)

**Interfaces:**
- Consumes: `alarmApi` (Task 7), `AlarmEvent` (Task 6).
- Produces: `useAlarms()` hook (TanStack Query, `queryKey: ['alarms']`, `refetchInterval: 5000` — usado por Task 15 e Task 16); `<AlarmPanel alarms />` — usado pela `DashboardPage` (Task 16).

- [ ] **Step 1: Escrever os testes**

```typescript
// frontend/src/lib/queries.test.ts
import { describe, it, expect } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAlarms } from './queries'

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient()
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

describe('useAlarms', () => {
  it('carrega a lista de alarmes do mock', async () => {
    const { result } = renderHook(() => useAlarms(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.length).toBeGreaterThan(0)
  })
})
```

```typescript
// frontend/src/components/AlarmPanel.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { AlarmPanel } from './AlarmPanel'
import type { AlarmEvent } from '../lib/types'

const ABERTO: AlarmEvent = {
  id: 1, sensor_code: 'PRESS-EXP-01', area: { area_code: 'EXPURGO', name: 'Expurgo' },
  tipo_violacao: 'abaixo_limite', status: 'aberto', timestamp_deteccao: '2026-07-18T15:19:00Z',
  valor_lido: -1.7, limite_configurado_snapshot: -2.5, data_resolucao: null,
}

describe('AlarmPanel', () => {
  it('lista vazia mostra estado "Nenhum alarme ativo"', () => {
    render(<AlarmPanel alarms={[]} />)
    expect(screen.getByText('Nenhum alarme ativo.')).toBeInTheDocument()
  })

  it('com alarmes, mostra contador e o tipo em maiusculas', () => {
    render(<AlarmPanel alarms={[ABERTO]} />)
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText('NÃO CONFORMIDADE')).toBeInTheDocument()
    expect(screen.getByText('Expurgo · PRESS-EXP-01')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `cd frontend && npx vitest run src/lib/queries.test.ts src/components/AlarmPanel.test.tsx`
Expected: FAIL (`useAlarms`/`AlarmPanel` não existem).

- [ ] **Step 3: Implementar**

```typescript
// frontend/src/lib/queries.ts — adicionar import de alarmApi, o hook useAlarms,
// e tornar useHistory tolerante a code='' (a DashboardPage da Task 16 chama
// useHistory antes do sensor selecionado estar resolvido — sem `enabled`,
// isso dispararia um fetch pra `/sensores//historico`).
import { useQuery, useQueries } from '@tanstack/react-query'
import { metaApi, historyApi, alarmApi } from './api'
import type { Window } from './types'

// ... (useSensorMeta, useThreshold, useSensors, useThresholds inalterados) ...

export function useHistory(code: string, window: Window) {
  return useQuery({
    queryKey: ['history', code, window],
    queryFn: () => historyApi.getHistory(code, window),
    enabled: code !== '',
  })
}

export function useAlarms() {
  return useQuery({ queryKey: ['alarms'], queryFn: () => alarmApi.listAlarms(), refetchInterval: 5000 })
}
```

```typescript
// frontend/src/components/AlarmItem.tsx
import type { AlarmEvent } from '../lib/types'

const TIPO_LABEL: Record<AlarmEvent['status'], string> = {
  aberto: 'NÃO CONFORMIDADE',
  reconhecido: 'NÃO CONFORMIDADE',
  resolvido: 'NORMALIZAÇÃO',
}
const BORDER_COLOR: Record<AlarmEvent['status'], string> = {
  aberto: 'var(--color-crit)',
  reconhecido: 'var(--color-crit)',
  resolvido: 'var(--color-good)',
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

export function AlarmItem({ alarm }: { alarm: AlarmEvent }) {
  return (
    <li
      className="rounded-md p-3"
      style={{ background: 'var(--color-panel)', borderLeft: `3px solid ${BORDER_COLOR[alarm.status]}` }}
    >
      <div className="flex items-center justify-between gap-2 text-xs font-bold" style={{ color: BORDER_COLOR[alarm.status] }}>
        <span>{TIPO_LABEL[alarm.status]}</span>
        <span className="font-mono" style={{ color: 'var(--color-muted)' }}>{formatTime(alarm.timestamp_deteccao)}</span>
      </div>
      <p className="mt-1 text-sm font-semibold" style={{ color: 'var(--color-ink)' }}>
        {alarm.area.name} · {alarm.sensor_code}
      </p>
      <p className="mt-0.5 text-xs font-medium" style={{ color: 'var(--color-muted)' }}>
        Valor lido {alarm.valor_lido ?? '—'} (limite {alarm.limite_configurado_snapshot ?? '—'})
      </p>
    </li>
  )
}
```

```typescript
// frontend/src/components/AlarmPanel.tsx
import { AlarmItem } from './AlarmItem'
import type { AlarmEvent } from '../lib/types'

export function AlarmPanel({ alarms }: { alarms: AlarmEvent[] }) {
  const ativos = alarms.filter((a) => a.status !== 'resolvido').length

  return (
    <aside
      className="sticky top-[78px] flex w-full flex-col gap-3 rounded-md p-4 md:w-[300px]"
      style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-line)',
        borderLeft: `3px solid ${ativos > 0 ? 'var(--color-crit)' : 'var(--color-line)'}`,
      }}
    >
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold" style={{ color: 'var(--color-ink)' }}>
          Alarmes
        </h2>
        <span
          className="rounded-full px-2 py-0.5 text-xs font-bold"
          style={{
            background: ativos > 0 ? 'var(--color-crit-soft)' : 'var(--color-good-soft)',
            color: ativos > 0 ? 'var(--color-crit)' : 'var(--color-good)',
          }}
        >
          {ativos}
        </span>
      </div>

      {alarms.length === 0 ? (
        <p className="py-6 text-center text-sm" style={{ color: 'var(--color-muted)' }}>
          Nenhum alarme ativo.
        </p>
      ) : (
        <ul className="space-y-2">
          {alarms.map((a) => (
            <AlarmItem key={a.id} alarm={a} />
          ))}
        </ul>
      )}
    </aside>
  )
}
```

- [ ] **Step 4: Rodar e confirmar sucesso**

Run: `cd frontend && npx vitest run src/lib/queries.test.ts src/components/AlarmPanel.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/queries.ts frontend/src/components/AlarmPanel.tsx frontend/src/components/AlarmItem.tsx frontend/src/lib/queries.test.ts frontend/src/components/AlarmPanel.test.tsx
git commit -m "feat(frontend): AlarmPanel + AlarmItem + useAlarms"
```

---

## Task 15: `ToastContainer` + `Toast` (novo alarme/normalização)

**Files:**
- Create: `frontend/src/components/Toast.tsx`
- Create: `frontend/src/components/ToastContainer.tsx`
- Test: `frontend/src/components/ToastContainer.test.tsx`

**Interfaces:**
- Consumes: `AlarmEvent[]` (mesma lista de `useAlarms`, Task 14).
- Produces: `<ToastContainer alarms loaded />` — detecta `id`s novos desde a última lista recebida e dispara um toast por evento novo, auto-dispensado em 6s. `loaded` (bool, obrigatório) trava a captura da baseline/diff enquanto os dados ainda estão carregando (evita toast-storm de alarmes pré-existentes quando `useAlarms()` resolve pela 1a vez). Usado pela `DashboardPage` (Task 16) como `loaded={!alarmsQuery.isLoading}`. [Corrigido pós-review da Task 15 — ver `.superpowers/sdd/progress.md`]

- [ ] **Step 1: Escrever o teste**

```typescript
// frontend/src/components/ToastContainer.test.tsx
import { render, screen, act } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { ToastContainer } from './ToastContainer'
import type { AlarmEvent } from '../lib/types'

const EVT = (id: number, status: AlarmEvent['status'] = 'aberto'): AlarmEvent => ({
  id, sensor_code: 'PRESS-EXP-01', area: { area_code: 'EXPURGO', name: 'Expurgo' },
  tipo_violacao: 'abaixo_limite', status, timestamp_deteccao: '2026-07-18T15:19:00Z',
  valor_lido: -1.7, limite_configurado_snapshot: -2.5, data_resolucao: null,
})

afterEach(() => vi.useRealTimers())

describe('ToastContainer', () => {
  it('nao mostra toast na primeira renderizacao (baseline, nao "tudo e novo")', () => {
    render(<ToastContainer alarms={[EVT(1)]} />)
    expect(screen.queryByText(/Expurgo/)).not.toBeInTheDocument()
  })

  it('um alarme com id novo apos a primeira renderizacao dispara um toast', () => {
    const { rerender } = render(<ToastContainer alarms={[EVT(1)]} />)
    rerender(<ToastContainer alarms={[EVT(2), EVT(1)]} />)
    expect(screen.getByText(/Não conformidade — Expurgo/)).toBeInTheDocument()
  })

  it('toast some sozinho apos 6s', () => {
    vi.useFakeTimers()
    const { rerender } = render(<ToastContainer alarms={[EVT(1)]} />)
    act(() => rerender(<ToastContainer alarms={[EVT(2), EVT(1)]} />))
    expect(screen.getByText(/Não conformidade — Expurgo/)).toBeInTheDocument()

    act(() => vi.advanceTimersByTime(6000))
    expect(screen.queryByText(/Não conformidade — Expurgo/)).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `cd frontend && npx vitest run src/components/ToastContainer.test.tsx`
Expected: FAIL (módulos não existem).

- [ ] **Step 3: Implementar**

```typescript
// frontend/src/components/Toast.tsx
import type { AlarmEvent } from '../lib/types'

export function Toast({ alarm, onClose }: { alarm: AlarmEvent; onClose: () => void }) {
  const isResolucao = alarm.status === 'resolvido'
  const color = isResolucao ? 'var(--color-good)' : 'var(--color-crit)'
  const titulo = isResolucao ? `Normalização — ${alarm.area.name}` : `Não conformidade — ${alarm.area.name}`

  return (
    <div
      role="status"
      className="flex w-[340px] items-start gap-3 rounded-md p-3"
      style={{ background: 'var(--color-surface)', border: `1px solid var(--color-line)`, boxShadow: 'var(--shadow-menu)' }}
    >
      <span className="flex size-[26px] shrink-0 items-center justify-center rounded-full text-xs font-bold" style={{ background: color, color: 'var(--color-surface)' }}>
        !
      </span>
      <div className="flex-1">
        <p className="text-sm font-semibold" style={{ color: 'var(--color-ink)' }}>{titulo}</p>
        <p className="text-xs font-medium" style={{ color: 'var(--color-muted)' }}>{alarm.sensor_code}</p>
      </div>
      <button type="button" onClick={onClose} aria-label="Fechar" className="min-h-11 min-w-11 text-lg" style={{ color: 'var(--color-muted)' }}>
        ×
      </button>
    </div>
  )
}
```

```typescript
// frontend/src/components/ToastContainer.tsx
import { useEffect, useRef, useState } from 'react'
import { Toast } from './Toast'
import type { AlarmEvent } from '../lib/types'

const AUTO_DISMISS_MS = 6000

export function ToastContainer({ alarms }: { alarms: AlarmEvent[] }) {
  const [visible, setVisible] = useState<AlarmEvent[]>([])
  const seenIds = useRef<Set<number> | null>(null)

  useEffect(() => {
    if (seenIds.current === null) {
      // Primeira renderizacao: so estabelece a baseline, nao dispara toast
      // pra cada alarme ja existente ao abrir a tela.
      seenIds.current = new Set(alarms.map((a) => a.id))
      return
    }
    const novos = alarms.filter((a) => !seenIds.current!.has(a.id))
    if (novos.length === 0) return
    novos.forEach((a) => seenIds.current!.add(a.id))
    setVisible((prev) => [...novos, ...prev])
    novos.forEach((a) => {
      setTimeout(() => setVisible((prev) => prev.filter((v) => v.id !== a.id)), AUTO_DISMISS_MS)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [alarms])

  if (visible.length === 0) return null

  return (
    <div className="fixed right-6 top-[70px] z-20 flex flex-col gap-2.5" aria-live="polite">
      {visible.map((a) => (
        <Toast key={a.id} alarm={a} onClose={() => setVisible((prev) => prev.filter((v) => v.id !== a.id))} />
      ))}
    </div>
  )
}
```

- [ ] **Step 4: Rodar e confirmar sucesso**

Run: `cd frontend && npx vitest run src/components/ToastContainer.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Toast.tsx frontend/src/components/ToastContainer.tsx frontend/src/components/ToastContainer.test.tsx
git commit -m "feat(frontend): Toast + ToastContainer (dispara em alarme/normalizacao novos)"
```

---

## Task 16: `DashboardPage` — fusão de telas + roteamento por querystring

**Files:**
- Create: `frontend/src/pages/DashboardPage.tsx`
- Create: `frontend/src/components/SensorDetailPanel.tsx`
- Delete: `frontend/src/pages/OverviewPage.tsx`, `frontend/src/pages/SensorDetailPage.tsx`, `frontend/src/pages/AreaPage.tsx`
- Delete: `frontend/src/components/SensorRow.tsx`, `frontend/src/components/LiveReadout.tsx`, `frontend/src/components/ThresholdBadge.tsx`, `frontend/src/components/HeaderActions.tsx` (só agora — Task 13 criou o `Topbar` que o substitui, mas não pôde deletar `HeaderActions.tsx` ainda porque as 3 páginas acima ainda o importavam; esta task deleta ambos os lados juntos)
- Modify: `frontend/src/App.tsx`
- Test: `frontend/src/pages/DashboardPage.test.tsx`
- Test: `frontend/src/components/SensorDetailPanel.test.tsx`
- Delete testes correspondentes: `OverviewPage.test.tsx`, `SensorDetailPage.test.tsx`, `LiveReadout.test.tsx` (a lógica coberta migra para os novos testes)

**Interfaces:**
- Consumes: `AreaCard` (Task 11), `Topbar` (Task 13), `AlarmPanel`+`useAlarms` (Task 14), `ToastContainer` (Task 15), `TimeSeriesChart`/`WindowSelector`/`ToleranceRail` (existentes), `groupSensorsByArea`/`useSensors`/`useThresholds`/`useLiveStatuses`/`useHistory`/`useLiveTail` (existentes).
- Produces: rota `/` renderiza `DashboardPage`; `/area/:areaCode` e `/sensor/:code` viram redirects para `/?area=` / `/?sensor=`.

- [ ] **Step 1: Escrever o teste do `SensorDetailPanel`**

```typescript
// frontend/src/components/SensorDetailPanel.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { SensorDetailPanel } from './SensorDetailPanel'
import type { AreaGroup } from '../lib/aggregateStatus'

const group: AreaGroup = {
  area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' },
  sensors: [
    { sensor_code: 'TEMP-EXP-01', name: 'Temp', unidade: '°C', protocolo_origem: '4-20ma', measurement_type: { code: 'temperatura', name: 'Temperatura' }, area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' } },
    { sensor_code: 'PRESS-EXP-01', name: 'Pressao', unidade: 'Pa', protocolo_origem: '4-20ma', measurement_type: { code: 'pressao_diferencial', name: 'Pressão' }, area: { area_code: 'EXPURGO', name: 'Expurgo', category: 'Expurgo' } },
  ],
}

describe('SensorDetailPanel', () => {
  it('mostra titulo Area . Sensor, botoes de metrica para cada sensor da area, e a leitura', () => {
    render(
      <SensorDetailPanel
        group={group}
        selectedCode="TEMP-EXP-01"
        onSelectSensor={vi.fn()}
        threshold={{ sensor_id: 'TEMP-EXP-01', limite_min: 18, limite_max: 26, is_valor_padrao_regulatorio: false }}
        unidade="°C"
        value={21}
        state="ok"
        window="24h"
        onWindowChange={vi.fn()}
        history={undefined}
        tail={[]}
      />,
    )
    expect(screen.getByText('Detalhe do sensor')).toBeInTheDocument()
    expect(screen.getByText('Expurgo · Temperatura')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Temperatura' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Pressão' })).toBeInTheDocument()
    expect(screen.getByText('21.0')).toBeInTheDocument()
  })

  it('clicar no botao de outra metrica chama onSelectSensor', () => {
    const onSelectSensor = vi.fn()
    render(
      <SensorDetailPanel
        group={group} selectedCode="TEMP-EXP-01" onSelectSensor={onSelectSensor}
        threshold={null} unidade="°C" value={21} state="ok"
        window="24h" onWindowChange={vi.fn()} history={undefined} tail={[]}
      />,
    )
    screen.getByRole('button', { name: 'Pressão' }).click()
    expect(onSelectSensor).toHaveBeenCalledWith('PRESS-EXP-01')
  })
})
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `cd frontend && npx vitest run src/components/SensorDetailPanel.test.tsx`
Expected: FAIL (módulo não existe).

- [ ] **Step 3: Implementar `SensorDetailPanel`**

```typescript
// frontend/src/components/SensorDetailPanel.tsx
import { computeStatus, LABELS, type StatusResult } from '../lib/status'
import type { AreaGroup } from '../lib/aggregateStatus'
import type { AlarmState, HistoryResponse, LivePoint, Threshold, Window } from '../lib/types'
import { ToleranceRail } from './ToleranceRail'
import { StatusIcon, statusTextColor } from './statusVisuals'
import { WindowSelector } from './WindowSelector'
import { TimeSeriesChart } from './TimeSeriesChart'

export function SensorDetailPanel({
  group, selectedCode, onSelectSensor, threshold, unidade, value, state,
  window, onWindowChange, history, tail,
}: {
  group: AreaGroup
  selectedCode: string
  onSelectSensor: (code: string) => void
  threshold: Threshold | null
  unidade: string
  value: number | null
  state?: AlarmState
  window: Window
  onWindowChange: (w: Window) => void
  history: HistoryResponse | undefined
  tail: LivePoint[]
}) {
  const selected = group.sensors.find((s) => s.sensor_code === selectedCode)
  const derived: StatusResult =
    value !== null
      ? computeStatus(value, threshold)
      : { state: 'unknown', label: LABELS.unknown, position: null }
  const st = state ?? derived.state

  return (
    <div className="rounded-md p-4" style={{ background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold" style={{ color: 'var(--color-ink)' }}>Detalhe do sensor</h2>
          <p className="mt-0.5 font-mono text-sm" style={{ color: 'var(--color-muted)' }}>
            {group.area.name} · {selected?.measurement_type.name}
          </p>
        </div>
        <div className="flex gap-1.5">
          {group.sensors.map((s) => {
            const on = s.sensor_code === selectedCode
            return (
              <button
                key={s.sensor_code}
                type="button"
                onClick={() => onSelectSensor(s.sensor_code)}
                className="min-h-11 rounded-md px-3 text-sm font-semibold outline-none transition-colors duration-200 ease-out focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] motion-reduce:transition-none"
                style={on
                  ? { background: 'var(--color-primary)', color: 'var(--color-surface)' }
                  : { border: '1px solid var(--color-line)', color: 'var(--color-muted)' }}
              >
                {s.measurement_type.name}
              </button>
            )
          })}
        </div>
      </div>

      <div className="mt-4 flex items-end gap-2">
        <span className="font-mono text-5xl font-semibold leading-none tabular-nums md:text-6xl" style={{ color: 'var(--color-ink)' }}>
          {value === null ? '—' : value.toFixed(1)}
        </span>
        <span className="pb-1 text-lg font-medium uppercase" style={{ color: 'var(--color-muted)' }}>{unidade}</span>
      </div>
      <div className="mt-2 flex items-center gap-2 text-sm font-semibold" style={{ color: statusTextColor(st) }}>
        <StatusIcon state={st} />
        <span>{LABELS[st]}</span>
      </div>
      <div className="mt-4">
        <ToleranceRail position={derived.position} state={st} min={threshold?.limite_min} max={threshold?.limite_max} />
      </div>

      <div className="mt-5 mb-3 flex justify-end">
        <WindowSelector value={window} onChange={onWindowChange} />
      </div>
      <TimeSeriesChart history={history} threshold={threshold} tail={tail} />
    </div>
  )
}
```

- [ ] **Step 4: Rodar e confirmar sucesso do `SensorDetailPanel`**

Run: `cd frontend && npx vitest run src/components/SensorDetailPanel.test.tsx`
Expected: PASS.

- [ ] **Step 5: Escrever o teste da `DashboardPage`**

```typescript
// frontend/src/pages/DashboardPage.test.tsx
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { MemoryRouter } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DashboardPage } from './DashboardPage'

function renderWithProviders(initialEntries: string[]) {
  const client = new QueryClient()
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={initialEntries}>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('DashboardPage', () => {
  it('sem querystring, mostra os cards de area e o painel de detalhe do 1o sensor', async () => {
    renderWithProviders(['/'])
    await waitFor(() => expect(screen.getByText('Detalhe do sensor')).toBeInTheDocument())
    expect(screen.getAllByTestId(/area-card-/).length).toBeGreaterThan(0)
  })

  it('com ?sensor=CODE, o painel de detalhe abre nesse sensor', async () => {
    renderWithProviders(['/?sensor=TEMP-PRE-01'])
    // Nome da area + measurement_type.name no fixture mock (TEMP-PRE-01) e
    // "Preparo/Esterilização" / "Temperatura" — ver frontend/src/lib/api/mock/fixtures.ts.
    await waitFor(() => expect(screen.getByText('Preparo/Esterilização · Temperatura')).toBeInTheDocument())
  })

  it('mostra o painel de alarmes e o topbar', async () => {
    renderWithProviders(['/'])
    await waitFor(() => expect(screen.getByText('Alarmes')).toBeInTheDocument())
    expect(screen.getByText('Sentinela')).toBeInTheDocument()
  })
})
```

- [ ] **Step 6: Rodar e confirmar falha**

Run: `cd frontend && npx vitest run src/pages/DashboardPage.test.tsx`
Expected: FAIL (módulo não existe).

- [ ] **Step 7: Implementar `DashboardPage`, deletar páginas/componentes superados, atualizar `App.tsx`**

```typescript
// frontend/src/pages/DashboardPage.tsx
import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { useSensors, useThresholds, useHistory, useAlarms } from '../lib/queries'
import { useLiveStatuses } from '../lib/useLiveStatuses'
import { useLiveTail } from '../lib/useLiveTail'
import { groupSensorsByArea } from '../lib/aggregateStatus'
import { AreaCard } from '../components/AreaCard'
import { Topbar } from '../components/Topbar'
import { AlarmPanel } from '../components/AlarmPanel'
import { ToastContainer } from '../components/ToastContainer'
import { SensorDetailPanel } from '../components/SensorDetailPanel'
import type { Window } from '../lib/types'

const UNIT_NAME = import.meta.env.VITE_UNIT_NAME ?? 'Unidade não configurada'

function isToday(iso: string): boolean {
  return iso.slice(0, 10) === new Date().toISOString().slice(0, 10)
}

export function DashboardPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [window, setWindow] = useState<Window>('24h')

  const sensorsQuery = useSensors()
  const sensors = sensorsQuery.data ?? []
  const codes = sensors.map((s) => s.sensor_code)
  const thresholdResults = useThresholds(codes)
  const thresholdsByCode = Object.fromEntries(codes.map((c, i) => [c, thresholdResults[i]?.data]))
  const liveByCode = useLiveStatuses(codes)
  const groups = groupSensorsByArea(sensors)
  const alarmsQuery = useAlarms()
  const alarms = alarmsQuery.data ?? []

  const areaParam = searchParams.get('area')
  const sensorParam = searchParams.get('sensor')
  const selectedGroup =
    groups.find((g) => g.sensors.some((s) => s.sensor_code === sensorParam))
    ?? groups.find((g) => g.area.area_code === areaParam)
    ?? groups[0]
  const selectedCode =
    selectedGroup?.sensors.find((s) => s.sensor_code === sensorParam)?.sensor_code
    ?? selectedGroup?.sensors[0]?.sensor_code
    ?? null

  const history = useHistory(selectedCode ?? '', window)
  const { last, tail } = useLiveTail(selectedCode ?? '')

  function selectSensor(code: string) {
    const group = groups.find((g) => g.sensors.some((s) => s.sensor_code === code))
    setSearchParams(group ? { area: group.area.area_code, sensor: code } : { sensor: code })
  }

  const ready = sensorsQuery.isSuccess && thresholdResults.every((r) => r.isSuccess)
  const healthy = sensorsQuery.isSuccess && !alarmsQuery.isError

  return (
    <div>
      <Topbar healthy={healthy} unitName={UNIT_NAME} />
      <ToastContainer alarms={alarms} loaded={!alarmsQuery.isLoading} />

      <div className="mx-auto max-w-6xl p-4 sm:p-6">
        <p className="mb-2 text-xs font-bold uppercase tracking-wide" style={{ color: 'var(--color-muted)' }}>
          Áreas monitoradas
        </p>

        <div className="flex flex-wrap gap-6">
          <div className="flex-1" style={{ minWidth: 280 }}>
            {!ready ? (
              <p className="text-sm" style={{ color: 'var(--color-muted)' }}>Carregando…</p>
            ) : (
              <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(232px, 1fr))' }}>
                {groups.map((g) => (
                  <AreaCard
                    key={g.area.area_code}
                    group={g}
                    thresholdsByCode={thresholdsByCode}
                    liveByCode={liveByCode}
                    selectedSensorCode={selectedCode}
                    onSelectSensor={selectSensor}
                    hadAlarmToday={alarms.some((a) => a.area.area_code === g.area.area_code && isToday(a.timestamp_deteccao))}
                  />
                ))}
              </div>
            )}

            {ready && selectedGroup && selectedCode && (
              <div className="mt-6">
                <SensorDetailPanel
                  group={selectedGroup}
                  selectedCode={selectedCode}
                  onSelectSensor={selectSensor}
                  threshold={thresholdsByCode[selectedCode] ?? null}
                  unidade={selectedGroup.sensors.find((s) => s.sensor_code === selectedCode)?.unidade ?? ''}
                  value={last?.value ?? null}
                  state={last?.alarm_state}
                  window={window}
                  onWindowChange={setWindow}
                  history={history.data}
                  tail={tail}
                />
              </div>
            )}
          </div>

          <AlarmPanel alarms={alarms} />
        </div>
      </div>
    </div>
  )
}
```

```typescript
// frontend/src/App.tsx — substituir integralmente
import { Routes, Route, Navigate, useParams } from 'react-router'
import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { AuthGuard } from './components/AuthGuard'

function AreaRedirect() {
  const { areaCode } = useParams<{ areaCode: string }>()
  return <Navigate to={`/?area=${areaCode}`} replace />
}

function SensorRedirect() {
  const { code } = useParams<{ code: string }>()
  return <Navigate to={`/?sensor=${code}`} replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<AuthGuard />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/area/:areaCode" element={<AreaRedirect />} />
        <Route path="/sensor/:code" element={<SensorRedirect />} />
      </Route>
    </Routes>
  )
}
```

```bash
git rm frontend/src/pages/OverviewPage.tsx frontend/src/pages/OverviewPage.test.tsx \
       frontend/src/pages/SensorDetailPage.tsx frontend/src/pages/SensorDetailPage.test.tsx \
       frontend/src/pages/AreaPage.tsx \
       frontend/src/components/SensorRow.tsx \
       frontend/src/components/LiveReadout.tsx frontend/src/components/LiveReadout.test.tsx \
       frontend/src/components/ThresholdBadge.tsx \
       frontend/src/components/HeaderActions.tsx
```

- [ ] **Step 8: Rodar a suite inteira e confirmar sucesso**

Run: `cd frontend && npx vitest run`
Expected: PASS (nenhum arquivo remanescente importa os módulos deletados — se algum import quebrar, ajustar antes de seguir).

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat(frontend): funde Overview+Sensor Detail+Area em DashboardPage unica; rotas antigas viram redirect"
```

---

## Task 17: Banner + botões de demo (atrás de `VITE_DEMO_MODE`)

**Files:**
- Create: `frontend/src/components/DemoBanner.tsx`
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Test: `frontend/src/components/DemoBanner.test.tsx`

**Interfaces:**
- Consumes: `isDemoMode()` (Task 7).
- Produces: `<DemoBanner onSimulate onReset simulating />` — só renderizado pela `DashboardPage` quando `isDemoMode()` é verdadeiro.

- [ ] **Step 1: Escrever o teste**

```typescript
// frontend/src/components/DemoBanner.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { DemoBanner } from './DemoBanner'

describe('DemoBanner', () => {
  it('mostra o banner e o botao de simular; clicar chama onSimulate', () => {
    const onSimulate = vi.fn()
    render(<DemoBanner simulating={false} onSimulate={onSimulate} onReset={vi.fn()} />)
    expect(screen.getByText(/Ambiente de demonstração/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Simular não conformidade/ }))
    expect(onSimulate).toHaveBeenCalled()
  })

  it('simulating=true troca o botao para "Interromper simulação"', () => {
    render(<DemoBanner simulating onSimulate={vi.fn()} onReset={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Interromper simulação' })).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `cd frontend && npx vitest run src/components/DemoBanner.test.tsx`
Expected: FAIL (módulo não existe).

- [ ] **Step 3: Implementar**

```typescript
// frontend/src/components/DemoBanner.tsx
export function DemoBanner({
  simulating, onSimulate, onReset,
}: { simulating: boolean; onSimulate: () => void; onReset: () => void }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-2 text-sm font-semibold" style={{ background: 'var(--color-warn-soft)', color: 'var(--color-warn)' }}>
      <span>AMBIENTE DE DEMONSTRAÇÃO — dados simulados para apresentação. Nenhuma medição real.</span>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onSimulate}
          className="min-h-11 rounded-md px-3 text-sm font-semibold"
          style={simulating
            ? { border: '1px solid var(--color-crit)', color: 'var(--color-crit)' }
            : { background: 'var(--color-primary)', color: 'var(--color-surface)' }}
        >
          {simulating ? 'Interromper simulação' : 'Simular não conformidade (Expurgo · pressão)'}
        </button>
        <button type="button" onClick={onReset} className="min-h-11 rounded-md px-3 text-sm font-semibold" style={{ border: '1px solid var(--color-line-strong)', color: 'var(--color-muted)' }}>
          Reiniciar demonstração
        </button>
      </div>
    </div>
  )
}
```

```typescript
// frontend/src/pages/DashboardPage.tsx — adicionar (dentro do componente, antes do return;
// e o banner condicional logo apos <ToastContainer .../> no JSX):
import { useQueryClient } from '@tanstack/react-query'
import { isDemoMode } from '../lib/demoMode'
import { DemoBanner } from '../components/DemoBanner'
import type { AlarmEvent } from '../lib/types'

// dentro de DashboardPage():
  const queryClient = useQueryClient()
  const [simulating, setSimulating] = useState(false)

  function simulateAlarm() {
    setSimulating(true)
    const fake: AlarmEvent = {
      id: Date.now(), sensor_code: 'PRESS-EXP-01', area: { area_code: 'EXPURGO', name: 'Expurgo' },
      tipo_violacao: 'abaixo_limite', status: 'aberto',
      timestamp_deteccao: new Date().toISOString(),
      valor_lido: -1.7, limite_configurado_snapshot: -2.5, data_resolucao: null,
    }
    queryClient.setQueryData<AlarmEvent[]>(['alarms'], (old) => [fake, ...(old ?? [])])
  }

  function resetDemo() {
    setSimulating(false)
    queryClient.invalidateQueries({ queryKey: ['alarms'] })
  }

// no JSX, logo apos <ToastContainer alarms={alarms} />:
      {isDemoMode() && <DemoBanner simulating={simulating} onSimulate={simulateAlarm} onReset={resetDemo} />}
```

- [ ] **Step 4: Rodar e confirmar sucesso**

Run: `cd frontend && npx vitest run`
Expected: PASS (suite inteira).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/DemoBanner.tsx frontend/src/components/DemoBanner.test.tsx frontend/src/pages/DashboardPage.tsx
git commit -m "feat(frontend): banner + simulacao de demo atras de VITE_DEMO_MODE"
```

---

## Task 18: Verificação visual manual (checklist)

**Files:** nenhum (task de verificação, não de código).

- [ ] **Step 1: Subir o backend real**

Run: `docker compose up -d`
Expected: Odoo, TimescaleDB e serviços de ingestão de pé.

- [ ] **Step 2: Rodar a API e o frontend em modo real**

Run: `cd api && uvicorn main:app --reload --port 8001` (terminal 1)
Run: `cd frontend && VITE_API_MODE=real VITE_UNIT_NAME="Hospital Demonstração — CME Central" npm run dev` (terminal 2)

- [ ] **Step 3: Checklist visual — tema Control (escuro, default)**

- [ ] Topbar: marca, pill de unidade, selo "Registro íntegro" (verde), relógio contando, "AO VIVO" pulsando.
- [ ] Cards de área: borda esquerda colorida por status, chip com ícone+texto, linhas de sensor com valor mono à direita.
- [ ] Clicar numa linha de sensor: painel de detalhe atualiza (título, leitura, gráfico) e a URL ganha `?area=&sensor=`.
- [ ] Gráfico: faixa verde de conformidade visível, linha de leitura, tooltip no hover.
- [ ] Painel de alarmes: contador, itens com borda colorida, estado vazio quando não há alarme.
- [ ] Alvos de toque (botões de métrica, seletor de janela, tema) ≥44px visualmente.

- [ ] **Step 4: Checklist visual — tema Document (claro)**

- [ ] Clicar toggle de tema, repetir os itens do Step 3 — contraste permanece legível, nenhuma cor "estourada".

- [ ] **Step 5: Checklist — responsivo**

- [ ] Reduzir viewport a ~375px: painel de alarmes desce abaixo dos cards (`flex-wrap`), nada corta/overflow horizontal.

- [ ] **Step 6: Registrar o resultado**

Se algum item falhar, abrir um ajuste pontual (não um novo plano) nos arquivos relevantes, re-rodar a suite (`npx vitest run`), commitar. Se tudo passar, este é o último passo do plano — não precisa de commit próprio.

---

## Task 18a (addendum, achada rodando a Task 18): bugs de modo real

Rodando o app de verdade (`VITE_API_MODE=real`) pela primeira vez nesta fatia, 2 bugs reais apareceram —
nenhum dos dois é pego pela suite (que roda 100% mock):

**Bug 1 — subscribe com sensor_code vazio.** `DashboardPage.tsx` chama `useLiveTail(selectedCode ?? '')`
antes dos sensores carregarem (`selectedCode` começa `null`). `useLiveTail`/`useLiveStatuses` não têm
conceito de `enabled` (não são React Query) — `realLiveApi.subscribe('', cb)` dispara na hora, batendo
`GET /sensores//threshold` e `GET /sensores//historico?window=1h` (404, barra dupla) a cada poll (3s) até
os sensores carregarem.

- **Fix:** `frontend/src/lib/api/real/liveApi.ts` — `subscribe` retorna um no-op (`() => {}`) sem chamar
  `realMetaApi.getThreshold`/`realHistoryApi.getHistory` quando `sensor_code === ''`.

**Bug 2 — cliente XML-RPC compartilhado sem lock (backend, pré-existente).** `api/odoo.py`
(`get_cliente_servico`, `@lru_cache`) devolve o MESMO `ServerProxy` XML-RPC pra todas as requests. A
DashboardPage é a primeira coisa no projeto a disparar várias chamadas reais em paralelo pro backend
(sensores + alarmes + thresholds×N + polling do live) — duas requests concorrentes reusando a mesma
conexão HTTP persistente colidem: `http.client.ResponseNotReady: Idle` → 500 sem corpo JSON limpo → como
a exceção não tratada escapa do meio do stack do Starlette antes de `CORSMiddleware` injetar headers na
resposta, o browser reporta "blocked by CORS policy" (sintoma enganoso — a causa real é o 500 de
concorrência, não config de CORS).

- **Fix:** lock (`threading.Lock`) em `ingestao/odoo_cliente.py` — todo `executar(...)` (a função que
  chama `cliente.models.execute_kw`) serializa via lock module-level antes de usar a conexão XML-RPC
  compartilhada. Fix mínimo (serializa acesso à conexão, não redesenha pooling/conexão-por-request) —
  aceitável dado que o volume de chamadas por request do dashboard é pequeno (não é hot path de alta
  concorrência).

- [ ] **Step 1: Escrever os testes**

Para o Bug 1 (`frontend/src/lib/api/real/liveApi.test.ts` — adicionar ao describe existente):

```typescript
it('sensor_code vazio: nao chama getThreshold/getHistory, devolve unsubscribe no-op', async () => {
  const cb = vi.fn()
  const unsub = realLiveApi.subscribe('', cb)
  await vi.runOnlyPendingTimersAsync().catch(() => {})
  expect(realMetaApi.getThreshold).not.toHaveBeenCalled()
  expect(realHistoryApi.getHistory).not.toHaveBeenCalled()
  expect(cb).not.toHaveBeenCalled()
  expect(() => unsub()).not.toThrow()
})
```

Para o Bug 2, um teste Python de concorrência real contra o backend (`api/tests/test_odoo_concorrencia.py`):

```python
import threading
from api.odoo import get_cliente_servico
from ingestao import odoo_cliente

def test_chamadas_concorrentes_nao_colidem():
    cliente = get_cliente_servico()
    erros = []

    def chamar():
        try:
            odoo_cliente.executar(cliente, 'sensor_monitor.sensor', 'search_read', [], fields=['sensor_code'])
        except Exception as exc:  # noqa: BLE001 -- queremos capturar QUALQUER falha de concorrencia
            erros.append(exc)

    threads = [threading.Thread(target=chamar) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert erros == [], f"chamadas concorrentes falharam: {erros}"
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `cd frontend && npx vitest run src/lib/api/real/liveApi.test.ts` — FAIL (comportamento atual chama getThreshold/getHistory mesmo com code vazio).
Run: `python3 -m pytest api/tests/test_odoo_concorrencia.py -v` — FAIL (`ResponseNotReady` ou erro de conexão em pelo menos 1 das 8 threads, de forma não-determinística — pode precisar rodar mais de uma vez pra reproduzir, é uma race condition).

- [ ] **Step 3: Implementar**

`frontend/src/lib/api/real/liveApi.ts` — guarda no topo de `subscribe`:
```typescript
subscribe(sensor_code, cb) {
  if (sensor_code === '') return () => {}
  // ... resto inalterado
```

`ingestao/odoo_cliente.py` — lock module-level em torno do XML-RPC:
```python
import threading

_lock = threading.Lock()

def executar(cliente, modelo, metodo, *args, **kwargs):
    with _lock:
        return cliente.models.execute_kw(
            cliente.db, cliente.uid, cliente.senha, modelo, metodo, list(args), kwargs,
        )
```
(usar a assinatura/corpo REAL de `executar` já existente em `ingestao/odoo_cliente.py` — só envolver a
chamada de rede existente com `with _lock:`, não reescrever a função.)

- [ ] **Step 4: Rodar e confirmar sucesso**

Run: `cd frontend && npx vitest run` — suite inteira verde.
Run: `python3 -m pytest api/tests/ -v` — suite inteira verde, incluindo o novo teste de concorrência
rodado umas 3x seguidas pra ganhar confiança de que não é flaky.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api/real/liveApi.ts frontend/src/lib/api/real/liveApi.test.ts \
        ingestao/odoo_cliente.py api/tests/test_odoo_concorrencia.py
git commit -m "fix: subscribe com sensor_code vazio e race no cliente XML-RPC compartilhado (achados na verificacao visual)"
```
