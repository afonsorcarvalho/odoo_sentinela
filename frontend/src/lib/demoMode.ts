// Banner e controles de demonstração. NUNCA ativos com API real: o banner
// afirma "dados simulados — nenhuma medição real". Mostrar isso sobre dados
// REAIS é perigoso num contexto de CME (alguém pode ignorar um alarme real
// achando que é simulado), então exigimos que a API não esteja em modo real.
export function isDemoMode(): boolean {
  return (
    import.meta.env.VITE_DEMO_MODE === 'true' &&
    import.meta.env.VITE_API_MODE !== 'real'
  )
}
