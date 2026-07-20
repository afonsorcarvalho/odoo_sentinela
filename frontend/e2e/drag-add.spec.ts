import { test, expect } from '@playwright/test'
import { loginIfNeeded, enterEdit } from './helpers'

// react-grid-layout isDroppable escuta eventos HTML5 nativos (dragstart na
// paleta -> dragover/drop no container). dragTo()/dragAndDrop() do Playwright
// usam mouse sintetico e NAO iniciam uma sessao de drag nativa, entao aqui
// despachamos os DragEvents manualmente com um DataTransfer compartilhado.
//
// CRITICO: o onDragOver do RGL injeta o item '__dropping__' no state via
// setState (assincrono). O drop precisa acontecer DEPOIS desse flush, senao
// layout.find(i==='__dropping__') e undefined e nada e adicionado. Por isso
// disparamos dragover, esperamos o React reconciliar, e so entao o drop —
// em evaluates separados.
test('arrasta um widget da paleta pra grade', async ({ page }) => {
  await loginIfNeeded(page)
  await enterEdit(page)
  await page.getByRole('button', { name: '+ Adicionar' }).click()

  const before = await page.getByTestId('widget-frame').count()
  const source = page.getByRole('button', { name: 'KPI (valor único)' })
  await source.waitFor()

  await page.evaluate(() => {
    const w = window as unknown as { __dt: DataTransfer; __fire: (el: Element, t: string, x: number, y: number) => void }
    w.__dt = new DataTransfer()
    w.__fire = (el, type, x, y) => {
      const ev = new DragEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y })
      Object.defineProperty(ev, 'dataTransfer', { value: w.__dt })
      el.dispatchEvent(ev)
    }
  })

  // Fase 1: dragstart na paleta -> seta droppingType (React state).
  await source.evaluate((el) => (window as unknown as { __fire: (e: Element, t: string, x: number, y: number) => void }).__fire(el, 'dragstart', 0, 0))
  await page.waitForTimeout(150)

  // Fase 2: dragenter + dragover -> RGL injeta o placeholder '__dropping__'.
  await page.locator('.react-grid-layout').evaluate((grid) => {
    const r = grid.getBoundingClientRect()
    const x = r.left + 300, y = r.top + 200
    const fire = (window as unknown as { __fire: (e: Element, t: string, x: number, y: number) => void }).__fire
    fire(grid, 'dragenter', x, y)
    fire(grid, 'dragover', x, y)
  })
  await page.waitForTimeout(200) // deixa o setState do RGL reconciliar

  // Fase 3: drop (agora o item '__dropping__' existe no state.layout).
  await page.locator('.react-grid-layout').evaluate((grid) => {
    const r = grid.getBoundingClientRect()
    ;(window as unknown as { __fire: (e: Element, t: string, x: number, y: number) => void }).__fire(grid, 'drop', r.left + 300, r.top + 200)
  })
  await page.waitForTimeout(200)

  await expect(page.getByTestId('widget-frame')).toHaveCount(before + 1)
  await page.screenshot({ path: 'e2e/__shots__/drag-add.png', fullPage: true })
})
