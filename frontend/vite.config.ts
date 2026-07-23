/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Proxy de dev: o browser fala só com o Vite (mesma origem da página), e o
  // Vite repassa /api/* para a API FastAPI (server-side). Mata CORS e a dor de
  // rede WSL2↔Windows (o browser não precisa alcançar :8000 diretamente).
  // VITE_API_BASE_URL=/api no .env.local casa com isto. SSE (/api/live) é
  // streaming HTTP — o proxy do Vite repassa sem bufferizar.
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
  // react-draggable (via react-grid-layout) referencia process.env.DRAGGABLE_DEBUG
  // no seu util `log`, chamado em handleDragStart. Vite nao polyfilla `process`
  // no browser (ao contrario de webpack/CRA), entao qualquer drag/resize estoura
  // ReferenceError: process is not defined. NODE_ENV o Vite ja substitui sozinho;
  // esta flag de debug nao, entao a fixamos como false.
  define: {
    'process.env.DRAGGABLE_DEBUG': 'false',
  },
  test: {
    environment: 'jsdom',
    globals: true,
    // e2e/*.spec.ts sao testes Playwright (browser real), rodados por `npm run
    // shot`/playwright — nao pelo vitest (que quebraria ao importar @playwright/test).
    exclude: ['**/node_modules/**', '**/e2e/**'],
    setupFiles: ['./src/test/setup.ts'],
    // Vite carrega .env.local em qualquer modo, incluindo test -- sem isto,
    // um .env.local de dev com VITE_API_MODE=real (usado p/ testar contra a
    // API de verdade) faz a suite tentar rede de verdade e falhar com
    // ECONNREFUSED quando a API nao esta de pe. Testes sempre rodam contra
    // mock, independente do que o .env.local local disser.
    env: { VITE_API_MODE: 'mock', VITE_DEMO_MODE: '' },
  },
})
