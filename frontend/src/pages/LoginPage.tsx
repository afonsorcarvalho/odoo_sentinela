import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { useAuth } from '../lib/useAuth'

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [usuario, setUsuario] = useState('')
  const [senha, setSenha] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  const [carregando, setCarregando] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setErro(null)
    setCarregando(true)
    try {
      await login(usuario, senha)
      navigate('/')
    } catch {
      setErro('Usuário ou senha inválidos.')
    } finally {
      setCarregando(false)
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-sm flex-col justify-center p-4">
      <h1 className="mb-6 text-xl font-bold" style={{ color: 'var(--color-ink)' }}>
        Sentinela CME
      </h1>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="usuario" className="mb-1 block text-sm font-medium" style={{ color: 'var(--color-muted)' }}>
            Usuário
          </label>
          <input
            id="usuario"
            type="text"
            value={usuario}
            onChange={(e) => setUsuario(e.target.value)}
            className="min-h-11 w-full rounded-md px-3 text-sm outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
            style={{ border: '1px solid var(--color-line)', color: 'var(--color-ink)', background: 'var(--color-surface)' }}
            autoComplete="username"
          />
        </div>
        <div>
          <label htmlFor="senha" className="mb-1 block text-sm font-medium" style={{ color: 'var(--color-muted)' }}>
            Senha
          </label>
          <input
            id="senha"
            type="password"
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            className="min-h-11 w-full rounded-md px-3 text-sm outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
            style={{ border: '1px solid var(--color-line)', color: 'var(--color-ink)', background: 'var(--color-surface)' }}
            autoComplete="current-password"
          />
        </div>
        {erro && (
          <p className="text-sm font-semibold" style={{ color: 'var(--color-crit)' }}>
            {erro}
          </p>
        )}
        <button
          type="submit"
          disabled={carregando}
          className="min-h-11 w-full rounded-md text-sm font-semibold text-[var(--color-surface)] outline-none transition-colors duration-200 ease-out focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] disabled:opacity-60 motion-reduce:transition-none"
          style={{ background: 'var(--color-primary)' }}
        >
          {carregando ? 'Entrando…' : 'Entrar'}
        </button>
      </form>
    </div>
  )
}
