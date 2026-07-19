import { test, expect } from '@playwright/test'
import { loginAndEnterEdit } from './helpers'

test('arrasta um widget da paleta pra grade', async ({ page }) => {
  await loginAndEnterEdit(page)
  await page.getByRole('button', { name: '+ Adicionar' }).click()
  const source = page.getByText('KPI (valor único)')
  const grid = page.locator('.react-grid-layout')
  const before = await page.getByTestId('widget-frame').count()
  await source.dragTo(grid, { targetPosition: { x: 300, y: 200 } })
  await expect(page.getByTestId('widget-frame')).toHaveCount(before + 1)
  await page.screenshot({ path: 'e2e/__shots__/drag-add.png' })
})
