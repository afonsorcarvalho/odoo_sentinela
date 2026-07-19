/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
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
    setupFiles: ['./src/test/setup.ts'],
    // Vite carrega .env.local em qualquer modo, incluindo test -- sem isto,
    // um .env.local de dev com VITE_API_MODE=real (usado p/ testar contra a
    // API de verdade) faz a suite tentar rede de verdade e falhar com
    // ECONNREFUSED quando a API nao esta de pe. Testes sempre rodam contra
    // mock, independente do que o .env.local local disser.
    env: { VITE_API_MODE: 'mock' },
  },
})
