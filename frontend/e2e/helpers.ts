import type { Page } from '@playwright/test'

// Login admin real (backend FastAPI :8001, user admin do profile odoo-sentinela).
// Senha via ADMIN_PW no env do processo de teste. Labels da LoginPage:
// "Usuário" / "Senha" / botão "Entrar".
export async function loginIfNeeded(page: Page) {
  // networkidle: espera o SPA montar antes de checar o form (senao o count le 0
  // no HTML vazio e pula o login).
  await page.goto('/', { waitUntil: 'networkidle' })
  const user = page.getByLabel('Usuário')
  if (await user.count()) {
    await user.fill('admin')
    await page.getByLabel('Senha').fill(process.env.ADMIN_PW ?? '')
    await page.getByRole('button', { name: 'Entrar' }).click()
    await page.waitForLoadState('networkidle')
  }
}

export async function enterEdit(page: Page) {
  const btn = page.getByRole('button', { name: 'Editar' })
  await btn.waitFor({ state: 'visible', timeout: 10000 })
  await btn.click()
}

// ThemeToggle mostra "Escuro" quando o tema atual e claro (clicar vai p/ dark)
// e "Claro" quando atual e escuro. aria-label: "Trocar para tema escuro/claro".
export async function setTheme(page: Page, theme: 'claro' | 'escuro') {
  const label = theme === 'escuro' ? 'Trocar para tema escuro' : 'Trocar para tema claro'
  const toggle = page.getByRole('button', { name: label })
  if (await toggle.count()) {
    await toggle.first().click()
    await page.waitForTimeout(300)
  }
}
