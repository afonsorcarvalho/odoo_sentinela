import { defineConfig } from '@playwright/test'

// chrome-devtools MCP nao sobe no WSL2; usamos Playwright p/ screenshots reais
// do modo edicao (light+dark) como criterio de aceite de UX/design/layout.
// Browsers ja em cache (~/.cache/ms-playwright). Sem webServer: dev (:5173) e
// API (:8001) sobem fora do teste. Login admin exige ADMIN_PW no env.
export default defineConfig({
  testDir: './e2e',
  timeout: 30000,
  use: {
    baseURL: 'http://localhost:5173',
    viewport: { width: 1440, height: 900 },
  },
})
