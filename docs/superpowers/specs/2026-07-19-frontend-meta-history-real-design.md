# Adapters reais: metaApi + historyApi — Design

## Contexto

`frontend/src/lib/api/index.ts` já tem um adapter real de autenticação
(`realAuthApi`) por trás do switch `VITE_API_MODE`. `metaApi` e `historyApi`
continuam hardcoded pro mock mesmo com `VITE_API_MODE=real`. O backend
FastAPI (`api/`) já serve os quatro endpoints necessários, testados e em
`master`:

- `GET /sensores` — lista de sensores
- `GET /sensores/{code}` — sensor único (404 se não existe)
- `GET /sensores/{code}/threshold` — 200 com `null` se sensor não tem
  threshold configurado, 404 se sensor não existe
- `GET /sensores/{code}/historico?window=...` — histórico raw/agregado

Todos exigem `Authorization: Bearer <token>`. O token já vive em
`localStorage['sentinela_token']`, escrito por `useAuth.tsx` no login.

## Objetivo

Trocar `mockMetaApi`/`mockHistoryApi` por adapters reais que chamam esses
endpoints, plugados no mesmo switch `VITE_API_MODE` que já liga
`realAuthApi`.

## Arquitetura

Um helper novo, `frontend/src/lib/api/real/http.ts`, compartilhado pelos
dois adapters:

```ts
export async function authFetchJson<T>(path: string): Promise<T> {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY)
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw new Error(`erro ${res.status} ao chamar ${path}`)
  return res.json()
}
```

`BASE_URL` segue o padrão já usado em `real/authApi.ts`
(`import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8001'`).

`TOKEN_STORAGE_KEY` hoje é uma constante local não-exportada dentro de
`useAuth.tsx` (`const STORAGE_KEY = 'sentinela_token'`). Vai ser exportada
de lá e importada em `http.ts` — evita duplicar a string em dois lugares
(risco de divergência silenciosa se uma mudar sem a outra).

Esse helper cobre uniformemente os 4 endpoints, incluindo o caso especial
do threshold: resposta `200` com corpo `null` passa direto (o contrato já é
`Promise<Threshold | null>`); resposta `404` (sensor inexistente) cai no
`throw` genérico — mesmo comportamento que o mock já tem hoje
(`mockMetaApi.getThreshold` lança erro pra código desconhecido).

## Componentes

**`frontend/src/lib/api/real/metaApi.ts`**
```ts
export const realMetaApi: MetaApi = {
  getSensor(code) { return authFetchJson(`/sensores/${code}`) },
  getThreshold(code) { return authFetchJson(`/sensores/${code}/threshold`) },
  listSensors() { return authFetchJson('/sensores') },
}
```

**`frontend/src/lib/api/real/historyApi.ts`**
```ts
export const realHistoryApi: HistoryApi = {
  getHistory(code, window) {
    return authFetchJson(`/sensores/${code}/historico?window=${window}`)
  },
}
```

**`frontend/src/lib/api/index.ts`** — o switch existente passa a cobrir os
três adapters com backend pronto:

```ts
export const authApi: AuthApi = mode === 'real' ? realAuthApi : mockAuthApi
export const metaApi: MetaApi = mode === 'real' ? realMetaApi : mockMetaApi
export const historyApi: HistoryApi = mode === 'real' ? realHistoryApi : mockHistoryApi
export const liveApi: LiveApi = mockLiveApi // sem backend SSE ainda
```

Comentário existente sobre "metaApi/historyApi ainda mock" é atualizado
pra refletir só o `liveApi` como pendente.

## Tratamento de erro

Qualquer resposta não-`ok` (401, 404, 500...) vira `throw new Error(...)`
genérico — sem diferenciação por status code, sem logout automático. Mesma
politica que `realAuthApi` já usa hoje. Interceptor central de 401
(logout automático) fica fora de escopo — revisitar quando houver telas
reais consumindo isso e um lugar natural pra decidir esse comportamento.

## Testes

Mirror do padrão já estabelecido em `real/authApi.test.ts`
(`vi.stubGlobal('fetch', ...)`, `afterEach(() => vi.unstubAllGlobals())`):

- `real/metaApi.test.ts`: cada método (`getSensor`, `getThreshold`,
  `listSensors`) — happy path (URL correta, header `Authorization`
  presente quando há token em `localStorage`, resultado do `json()`
  repassado) e erro (`!ok` → rejeita).
- `real/historyApi.test.ts`: `getHistory` — URL com `?window=` correto,
  mesmo padrão de happy/erro.

## Fora de escopo

- `liveApi` real / SSE — backend ainda não expõe esse endpoint.
- Interceptor de 401 / logout automático.
- Retry / cache / invalidação de queries.
