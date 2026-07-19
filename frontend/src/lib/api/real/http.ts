import { TOKEN_STORAGE_KEY } from '../../useAuth'

export const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8001'

export async function authFetchJson<T>(path: string): Promise<T> {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY)
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) {
    throw new Error(`erro ${res.status} ao chamar ${path}`)
  }
  return res.json()
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
