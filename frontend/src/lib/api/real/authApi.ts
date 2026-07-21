import type { AuthApi } from '../contracts'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8001'

export const realAuthApi: AuthApi = {
  async login(usuario, senha) {
    let res: Response
    try {
      res = await fetch(`${BASE_URL}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ usuario, senha }),
      })
    } catch {
      throw new Error('erro de rede')
    }
    if (!res.ok) {
      throw new Error('credenciais inválidas')
    }
    return res.json()
  },
}
