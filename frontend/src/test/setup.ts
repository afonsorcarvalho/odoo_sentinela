import '@testing-library/jest-dom'

// jsdom nao implementa matchMedia; usePrefersReducedMotion (useSensorCarousel.ts)
// e o primeiro uso no projeto. Default matches:false (sem reducao de movimento);
// testes especificos de reduced-motion sobrescrevem via vi.stubGlobal.
// jsdom nao implementa ResizeObserver; DashboardGrid usa para medir a largura
// do container e alinhar a grade de fundo do modo edicao. Stub no-op: no jsdom
// a largura fica 0 e o overlay renderiza sem background (comportamento testado).
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
}

if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
}
