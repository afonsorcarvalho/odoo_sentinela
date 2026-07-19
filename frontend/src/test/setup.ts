import '@testing-library/jest-dom'

// jsdom nao implementa matchMedia; usePrefersReducedMotion (useSensorCarousel.ts)
// e o primeiro uso no projeto. Default matches:false (sem reducao de movimento);
// testes especificos de reduced-motion sobrescrevem via vi.stubGlobal.
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
