import { TOKEN_STORAGE_KEY } from '../../useAuth'

export const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8001'

// 422/404 da API trazem `detail` legivel (ex.: "periodo maximo de 366 dias"):
// repassa ao usuario. Demais erros mantem a mensagem generica.
async function erroHttp(res: Response, path: string): Promise<Error> {
  if (res.status === 422 || res.status === 404) {
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') return new Error(body.detail)
    } catch {
      // corpo nao-JSON: cai na mensagem generica
    }
  }
  return new Error(`erro ${res.status} ao chamar ${path}`)
}

export async function authFetchJson<T>(path: string): Promise<T> {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY)
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) {
    throw await erroHttp(res, path)
  }
  return res.json()
}

export async function authFetchBlob(path: string): Promise<Blob> {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY)
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) {
    throw await erroHttp(res, path)
  }
  return res.blob()
}

export async function authFetchJsonWrite<T>(path: string, method: 'POST' | 'PUT', body: unknown): Promise<T> {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY)
  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    throw new Error(`erro ${res.status} ao chamar ${path}`)
  }
  return res.json()
}
