import { test } from '@playwright/test'
import { loginIfNeeded, enterEdit, setTheme } from './helpers'

// Harness de verificacao visual do modo edicao (light + dark). Gera screenshots
// em e2e/__shots__/ p/ inspecao de UX/design/layout apos cada task.
for (const theme of ['claro', 'escuro'] as const) {
  test(`editor ${theme}`, async ({ page }) => {
    await loginIfNeeded(page)
    await setTheme(page, theme)
    await enterEdit(page)
    await page.waitForTimeout(500)
    await page.screenshot({ path: `e2e/__shots__/editor-${theme}.png`, fullPage: true })
  })
}
