import { useNavigate } from 'react-router'
import { useAuth } from '../lib/useAuth'

export function LogoutButton() {
  const { logout } = useAuth()
  const navigate = useNavigate()

  function handleClick() {
    logout()
    navigate('/login')
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      className="flex min-h-11 items-center gap-2 rounded-md px-3 py-1.5 text-sm font-semibold outline-none transition-colors duration-200 ease-out hover:text-[var(--color-crit)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)] motion-reduce:transition-none"
      style={{ border: '1px solid var(--color-line)', color: 'var(--color-muted)' }}
    >
      Sair
    </button>
  )
}
