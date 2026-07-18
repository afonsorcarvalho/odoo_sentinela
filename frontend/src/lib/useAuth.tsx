import { createContext, useContext, useState, type ReactNode } from 'react'
import { authApi } from './api'
import { decodeJwtExp } from './jwt'

const STORAGE_KEY = 'sentinela_token'

type AuthContextValue = {
  isAuthenticated: boolean
  login: (usuario: string, senha: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

function readValidToken(): string | null {
  const token = localStorage.getItem(STORAGE_KEY)
  if (!token) return null
  const exp = decodeJwtExp(token)
  if (exp === null || exp <= Date.now()) {
    localStorage.removeItem(STORAGE_KEY)
    return null
  }
  return token
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => readValidToken())

  async function login(usuario: string, senha: string) {
    const { access_token } = await authApi.login(usuario, senha)
    localStorage.setItem(STORAGE_KEY, access_token)
    setToken(access_token)
  }

  function logout() {
    localStorage.removeItem(STORAGE_KEY)
    setToken(null)
  }

  return (
    <AuthContext.Provider value={{ isAuthenticated: token !== null, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth precisa estar dentro de AuthProvider')
  return ctx
}
