# SSE Multiplexada (fix de limite de conexão por origem) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corrigir bug real achado em teste com dados reais: com N sensores na tela (dashboard fundido), o
frontend abre N `EventSource` simultâneos pro mesmo host — mas browsers limitam conexões HTTP/1.1
persistentes a 6 por origem. Sensores além do 6º nunca recebem dado ao vivo (fila fica pendurada pra
sempre). Confirmado com teste real: 12 sensores → 12 conexões → só ~6 primeiras recebem live.

**Architecture:** Backend ganha 1 endpoint novo `GET /live` (SSE, sem `sensor_code` na URL) que multiplexa
TODOS os sensores numa única conexão — cada mensagem já inclui `sensor_id` no payload (`live_listener.py`
já publica assim). Frontend troca o mecanismo interno de `realLiveApi` pra um **único EventSource
compartilhado** (singleton, aberto na primeira chamada de `subscribe`, fechado quando o último
inscrito sai), que demuxa mensagens por `sensor_id` pra um mapa de callbacks locais. O contrato público
`LiveApi.subscribe(sensor_code, cb): unsubscribe` não muda — zero mudança nos consumidores
(`useLiveTail`, `useLiveStatuses`, `DashboardPage`, etc.).

**Tech Stack:** FastAPI + `asyncio.Queue` (backend, `api/live.py` já existente); TypeScript + `EventSource`
nativo (frontend, `frontend/src/lib/api/real/liveApi.ts`).

## Global Constraints

- **Não quebrar o endpoint antigo `GET /sensores/{code}/live`.** Continua existindo (testes já cobrem:
  `api/tests/test_live_endpoint.py`), só deixa de ser usado pelo frontend. `api/live.py`'s `_registry`
  (por sensor) e `registrar`/`remover`/`publicar` existentes **não mudam de assinatura** — só ganham um
  mecanismo paralelo global.
- **Payload da mensagem já tem `sensor_id`** (`api/live_listener.py:_receber_notificacao` já publica
  `dados` completo, que inclui `sensor_id`) — o endpoint novo não precisa transformar nada, só repassar.
- **Frontend: 1 EventSource só, nunca mais que isso**, independente de quantos sensores a página estiver
  observando ao mesmo tempo. Reference-counting: fecha só quando não sobra nenhum inscrito.
- **Token de auth via query string** (`?token=`), mesmo padrão do endpoint por-sensor já existente
  (`verificar_token_query` em `api/auth.py`).

---

## Task 1: Backend — endpoint `GET /live` (multiplexado, todos os sensores)

**Files:**
- Modify: `api/live.py`
- Test: `api/tests/test_live_endpoint.py` (adicionar aos testes existentes, não reescrever)
- Test: `api/tests/test_live_registry.py` (adicionar aos testes existentes)

**Interfaces:**
- Produces: `GET /live?token=<jwt>` (SSE) — stream de `data: {"sensor_id":..., "time":..., "valor":...}\n\n`
  pra TODO evento publicado, independente do sensor. `registrar_global() -> asyncio.Queue`,
  `remover_global(fila)` (usados só internamente pelo endpoint, mas exportados pra teste direto, mesmo
  padrão de `registrar`/`remover`).
- Consumes: nada novo — reusa `publicar()` já existente (que agora também alimenta o registry global).

- [ ] **Step 1: Escrever os testes**

```python
# api/tests/test_live_registry.py — adicionar ao final do arquivo
def test_registrar_global_e_publicar_entrega_em_todas_as_filas_globais():
    async def cenario():
        fila = live.registrar_global()
        live.publicar('QUALQUER-SENSOR', {'sensor_id': 'QUALQUER-SENSOR', 'valor': 42})
        item = await asyncio.wait_for(fila.get(), timeout=1)
        assert item == {'sensor_id': 'QUALQUER-SENSOR', 'valor': 42}
        live.remover_global(fila)

    asyncio.run(cenario())


def test_remover_global_impede_entrega_futura():
    async def cenario():
        fila = live.registrar_global()
        live.remover_global(fila)
        live.publicar('SNR-X', {'valor': 1})
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(fila.get(), timeout=0.2)

    asyncio.run(cenario())


def test_publicar_alimenta_fila_por_sensor_e_fila_global_ao_mesmo_tempo():
    async def cenario():
        fila_sensor = live.registrar('SNR-Y')
        fila_global = live.registrar_global()
        live.publicar('SNR-Y', {'sensor_id': 'SNR-Y', 'valor': 7})

        item_sensor = await asyncio.wait_for(fila_sensor.get(), timeout=1)
        item_global = await asyncio.wait_for(fila_global.get(), timeout=1)
        assert item_sensor == item_global == {'sensor_id': 'SNR-Y', 'valor': 7}

        live.remover('SNR-Y', fila_sensor)
        live.remover_global(fila_global)

    asyncio.run(cenario())
```

```python
# api/tests/test_live_endpoint.py — adicionar ao final do arquivo (mesmo estilo dos testes existentes)
def test_live_global_sem_token_retorna_422():
    client = TestClient(app)
    resposta = client.get('/live')
    assert resposta.status_code == 422


def test_live_global_token_invalido_retorna_401():
    client = TestClient(app)
    resposta = client.get('/live', params={'token': 'lixo.invalido.aqui'})
    assert resposta.status_code == 401


def test_live_global_recebe_evento_de_qualquer_sensor():
    # Mesma técnica do test_live_recebe_ponto_publicado_no_registry acima: chama a
    # coroutine da rota diretamente (não via ASGI transport), pelo mesmo motivo já
    # documentado (StreamingResponse infinito trava o ASGITransport do httpx).
    async def cenario():
        resposta = await live.get_live_global(_claims={})
        agen = resposta.body_iterator
        try:
            live.publicar('QUALQUER-OUTRO-SENSOR', {'sensor_id': 'QUALQUER-OUTRO-SENSOR', 'time': 1700000000000, 'valor': 15.0})
            linha = await asyncio.wait_for(agen.__anext__(), timeout=2)
            assert linha.startswith('data: ')
            payload = json.loads(linha[len('data: '):].strip())
            assert payload['sensor_id'] == 'QUALQUER-OUTRO-SENSOR'
            assert payload['valor'] == 15.0
        finally:
            await agen.aclose()

    asyncio.run(cenario())
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `python3 -m pytest api/tests/test_live_registry.py api/tests/test_live_endpoint.py -v`
Expected: FAIL (`registrar_global`/`remover_global`/`get_live_global` não existem ainda).

- [ ] **Step 3: Implementar**

```python
# api/live.py — substituir o arquivo inteiro
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from .auth import verificar_token_query
from .meta import obter_sensor
from .odoo import get_cliente_servico

router = APIRouter()

_registry: dict[str, set[asyncio.Queue]] = {}
_registry_global: set[asyncio.Queue] = set()


def registrar(sensor_code: str) -> asyncio.Queue:
    fila = asyncio.Queue()
    _registry.setdefault(sensor_code, set()).add(fila)
    return fila


def remover(sensor_code: str, fila: asyncio.Queue) -> None:
    filas = _registry.get(sensor_code)
    if filas is None:
        return
    filas.discard(fila)
    if not filas:
        _registry.pop(sensor_code, None)


def registrar_global() -> asyncio.Queue:
    fila = asyncio.Queue()
    _registry_global.add(fila)
    return fila


def remover_global(fila: asyncio.Queue) -> None:
    _registry_global.discard(fila)


def publicar(sensor_code: str, payload: dict) -> None:
    for fila in _registry.get(sensor_code, ()):
        fila.put_nowait(payload)
    for fila in _registry_global:
        fila.put_nowait(payload)


@router.get('/sensores/{sensor_code}/live')
async def get_live(
    sensor_code: str,
    cliente=Depends(get_cliente_servico),
    _claims=Depends(verificar_token_query),
):
    if await asyncio.to_thread(obter_sensor, cliente, sensor_code) is None:
        raise HTTPException(status_code=404, detail=f"sensor '{sensor_code}' não encontrado")

    fila = registrar(sensor_code)

    async def stream():
        try:
            while True:
                payload = await fila.get()
                yield f"data: {json.dumps(payload)}\n\n"
        finally:
            remover(sensor_code, fila)

    return StreamingResponse(stream(), media_type='text/event-stream')


@router.get('/live')
async def get_live_global(_claims=Depends(verificar_token_query)):
    # Sem sensor_code: multiplexa eventos de TODOS os sensores numa unica
    # conexao. Existe pra nao estourar o limite de 6 conexoes HTTP/1.1
    # persistentes por origem que os browsers aplicam -- com N sensores na
    # tela (dashboard fundido), abrir 1 EventSource por sensor trava os
    # sensores alem do 6o pra sempre (achado em teste real, ver plano).
    fila = registrar_global()

    async def stream():
        try:
            while True:
                payload = await fila.get()
                yield f"data: {json.dumps(payload)}\n\n"
        finally:
            remover_global(fila)

    return StreamingResponse(stream(), media_type='text/event-stream')
```

- [ ] **Step 4: Rodar e confirmar sucesso**

Run: `python3 -m pytest api/tests/test_live_registry.py api/tests/test_live_endpoint.py -v`
Expected: PASS (todos, incluindo os 4 antigos + 5 novos).

Run: `python3 -m pytest api/tests/ -v` (suite inteira)
Expected: PASS, sem regressão nos testes de `/sensores/{code}/live` existentes.

- [ ] **Step 5: Commit**

```bash
git add api/live.py api/tests/test_live_registry.py api/tests/test_live_endpoint.py
git commit -m "feat: endpoint GET /live multiplexado (todos os sensores numa so conexao SSE)"
```

---

## Task 2: Frontend — `realLiveApi` com EventSource único compartilhado

**Files:**
- Modify: `frontend/src/lib/api/real/liveApi.ts`
- Modify: `frontend/src/lib/api/real/liveApi.test.ts`

**Interfaces:**
- Consumes: `GET /live?token=` (Task 1).
- Produces: `realLiveApi: LiveApi` — **mesma assinatura pública de sempre**
  (`subscribe(sensor_code, cb): () => void`). Nenhum consumidor (`useLiveTail`, `useLiveStatuses`,
  `DashboardPage`, etc.) muda.

- [ ] **Step 1: Escrever os testes (substituir o arquivo de teste inteiro)**

```typescript
// frontend/src/lib/api/real/liveApi.test.ts
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest'
import { realLiveApi } from './liveApi'
import { TOKEN_STORAGE_KEY } from '../../useAuth'
import * as metaApiModule from './metaApi'

class MockEventSource {
  static instances: MockEventSource[] = []
  url: string
  onmessage: ((ev: { data: string }) => void) | null = null
  closed = false
  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }
  close() {
    this.closed = true
  }
}

const THRESHOLD = { sensor_id: 'SNR-1', limite_min: 10, limite_max: 20, is_valor_padrao_regulatorio: false }

beforeEach(() => {
  MockEventSource.instances = []
  vi.stubGlobal('EventSource', MockEventSource)
  vi.spyOn(metaApiModule.realMetaApi, 'getThreshold').mockResolvedValue(THRESHOLD)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  localStorage.clear()
})

describe('realLiveApi', () => {
  it('subscribe abre 1 unico EventSource pra /live (sem sensor_code na URL), reusado por chamadas seguintes', () => {
    localStorage.setItem(TOKEN_STORAGE_KEY, 'abc.def.ghi')

    realLiveApi.subscribe('SNR-1', () => {})
    realLiveApi.subscribe('SNR-2', () => {})
    realLiveApi.subscribe('SNR-3', () => {})

    expect(MockEventSource.instances).toHaveLength(1)
    expect(MockEventSource.instances[0].url).toContain('/live?token=abc.def.ghi')
    expect(MockEventSource.instances[0].url).not.toContain('/sensores/')
  })

  it('demuxa mensagens por sensor_id: cada callback so recebe evento do seu proprio sensor', async () => {
    const cbA = vi.fn()
    const cbB = vi.fn()
    realLiveApi.subscribe('SNR-1', cbA)
    realLiveApi.subscribe('SNR-2', cbB)
    await Promise.resolve()

    const es = MockEventSource.instances[0]
    es.onmessage?.({ data: JSON.stringify({ sensor_id: 'SNR-1', time: 1700000000000, valor: 15 }) })

    expect(cbA).toHaveBeenCalledTimes(1)
    expect(cbB).not.toHaveBeenCalled()
  })

  it('onmessage computa alarm_state a partir do threshold cacheado do proprio sensor', async () => {
    const cb = vi.fn()
    realLiveApi.subscribe('SNR-1', cb)
    await Promise.resolve()

    const es = MockEventSource.instances[0]
    es.onmessage?.({ data: JSON.stringify({ sensor_id: 'SNR-1', time: 1700000000000, valor: 15 }) })

    expect(cb).toHaveBeenCalledWith({ sensor_code: 'SNR-1', ts: 1700000000000, value: 15, alarm_state: 'ok' })
  })

  it('valor fora da faixa do threshold gera alarm_state crit', async () => {
    const cb = vi.fn()
    realLiveApi.subscribe('SNR-1', cb)
    await Promise.resolve()

    const es = MockEventSource.instances[0]
    es.onmessage?.({ data: JSON.stringify({ sensor_id: 'SNR-1', time: 1700000000000, valor: 99 }) })

    expect(cb).toHaveBeenCalledWith(expect.objectContaining({ alarm_state: 'crit' }))
  })

  it('unsubscribe de 1 sensor nao fecha o EventSource compartilhado enquanto outros seguem inscritos', async () => {
    const unsubA = realLiveApi.subscribe('SNR-1', () => {})
    realLiveApi.subscribe('SNR-2', () => {})

    unsubA()

    expect(MockEventSource.instances[0].closed).toBe(false)
  })

  it('unsubscribe do ultimo inscrito fecha o EventSource compartilhado', () => {
    const unsubA = realLiveApi.subscribe('SNR-1', () => {})
    unsubA()

    expect(MockEventSource.instances[0].closed).toBe(true)
  })

  it('reabre um novo EventSource se subscribe for chamado de novo apos todo mundo sair', () => {
    const unsubA = realLiveApi.subscribe('SNR-1', () => {})
    unsubA()
    realLiveApi.subscribe('SNR-2', () => {})

    expect(MockEventSource.instances).toHaveLength(2)
    expect(MockEventSource.instances[1].closed).toBe(false)
  })

  it('sensor_code vazio: nao registra callback, nao quebra o demux dos outros', () => {
    const cb = vi.fn()
    const unsubscribe = realLiveApi.subscribe('', cb)

    expect(() => unsubscribe()).not.toThrow()
    // Nao conta como inscrito "de verdade" pro reference-count: sozinho, unsubscribe fecha o ES
    // (mesmo ES ainda foi aberto pelo subscribe('') em si -- ver nota de implementacao no Step 3).
  })
})
```

- [ ] **Step 2: Rodar e confirmar falha**

Run: `cd frontend && npx vitest run src/lib/api/real/liveApi.test.ts`
Expected: FAIL (implementação atual abre 1 EventSource por sensor, não compartilhado).

- [ ] **Step 3: Implementar**

```typescript
// frontend/src/lib/api/real/liveApi.ts
import type { LiveApi } from '../contracts'
import type { AlarmState, LivePoint, Threshold } from '../../types'
import { TOKEN_STORAGE_KEY } from '../../useAuth'
import { computeStatus } from '../../status'
import { BASE_URL } from './http'
import { realMetaApi } from './metaApi'

// EventSource compartilhado por toda a app: browsers limitam a 6 conexoes
// HTTP/1.1 persistentes por origem, e o dashboard fundido pode ter dezenas
// de sensores visiveis ao mesmo tempo (grid de areas + painel de detalhe) --
// 1 EventSource por sensor estoura esse limite e sensores alem do 6o nunca
// recebem dado (achado em teste real com 12 sensores). Aqui, 1 conexao so
// pro endpoint /live (multiplexado, ver api/live.py), demuxada por
// sensor_id pros callbacks inscritos. Reference-counting: a conexao só
// fecha quando o ultimo inscrito sai.
let sharedSource: EventSource | null = null
const subscribers = new Map<string, Set<(p: LivePoint) => void>>()
const thresholdCache = new Map<string, Threshold | null>()

function ensureSharedSource(): EventSource {
  if (sharedSource) return sharedSource

  const token = localStorage.getItem(TOKEN_STORAGE_KEY)
  const es = new EventSource(`${BASE_URL}/live?token=${token}`)
  es.onmessage = (event) => {
    const { sensor_id, time, valor } = JSON.parse(event.data)
    const callbacks = subscribers.get(sensor_id)
    if (!callbacks || callbacks.size === 0) return
    const threshold = thresholdCache.get(sensor_id) ?? null
    const { state } = computeStatus(valor, threshold)
    const alarm_state: AlarmState = state === 'unknown' ? 'ok' : state
    const point: LivePoint = { sensor_code: sensor_id, ts: time, value: valor, alarm_state }
    callbacks.forEach((cb) => cb(point))
  }
  sharedSource = es
  return es
}

function closeSharedSourceIfIdle(): void {
  const totalSubscribers = [...subscribers.values()].reduce((acc, set) => acc + set.size, 0)
  if (totalSubscribers === 0 && sharedSource) {
    sharedSource.close()
    sharedSource = null
  }
}

export const realLiveApi: LiveApi = {
  subscribe(sensor_code, cb) {
    ensureSharedSource()

    if (sensor_code === '') {
      return () => closeSharedSourceIfIdle()
    }

    if (!thresholdCache.has(sensor_code)) {
      realMetaApi.getThreshold(sensor_code)
        .then((t) => thresholdCache.set(sensor_code, t))
        .catch(() => thresholdCache.set(sensor_code, null))
    }

    const callbacks = subscribers.get(sensor_code) ?? new Set()
    callbacks.add(cb)
    subscribers.set(sensor_code, callbacks)

    return () => {
      callbacks.delete(cb)
      if (callbacks.size === 0) subscribers.delete(sensor_code)
      closeSharedSourceIfIdle()
    }
  },
}
```

- [ ] **Step 4: Rodar e confirmar sucesso**

Run: `cd frontend && npx vitest run src/lib/api/real/liveApi.test.ts`
Expected: PASS (todos os 8 testes).

Run: `cd frontend && npx vitest run` (suite inteira)
Expected: PASS — nenhum consumidor de `LiveApi` muda, então nada mais deveria quebrar.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/api/real/liveApi.ts frontend/src/lib/api/real/liveApi.test.ts
git commit -m "fix(frontend): realLiveApi usa 1 EventSource compartilhado (evita estourar limite de 6 conexoes/origem)"
```

---

## Task 3: Verificação manual (checklist)

**Files:** nenhum.

- [ ] **Step 1:** Com API e frontend reais rodando (`VITE_API_MODE=real`) e ≥8 sensores cadastrados,
  abrir o dashboard num browser real (ou script Playwright) e contar quantas requisições
  `.../live?token=` são abertas. Esperado: **exatamente 1**, contra `/live` (sem `/sensores/{code}/`).
- [ ] **Step 2:** Confirmar que TODOS os sensores da tela recebem valor ao vivo (nenhum fica travado em
  "—"), incluindo o 7º+ sensor que antes travava.
- [ ] **Step 3:** Trocar de sensor selecionado várias vezes rápido (clicar em várias linhas) — confirmar
  que não abre EventSource novo a cada clique (continua 1 só) e que não há erro no console.
