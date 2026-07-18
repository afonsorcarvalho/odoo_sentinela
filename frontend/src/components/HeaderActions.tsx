import { ThemeToggle } from './ThemeToggle'
import { LogoutButton } from './LogoutButton'

export function HeaderActions() {
  return (
    <div className="flex items-center gap-2">
      <ThemeToggle />
      <LogoutButton />
    </div>
  )
}
