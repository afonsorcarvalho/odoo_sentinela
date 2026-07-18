export function DemoBanner({
  simulating, onSimulate, onReset,
}: { simulating: boolean; onSimulate: () => void; onReset: () => void }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-2 text-sm font-semibold" style={{ background: 'var(--color-warn-soft)', color: 'var(--color-warn)' }}>
      <span>AMBIENTE DE DEMONSTRAÇÃO — dados simulados para apresentação. Nenhuma medição real.</span>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onSimulate}
          className="min-h-11 rounded-md px-3 text-sm font-semibold"
          style={simulating
            ? { border: '1px solid var(--color-crit)', color: 'var(--color-crit)' }
            : { background: 'var(--color-primary)', color: 'var(--color-surface)' }}
        >
          {simulating ? 'Interromper simulação' : 'Simular não conformidade (Expurgo · pressão)'}
        </button>
        <button type="button" onClick={onReset} className="min-h-11 rounded-md px-3 text-sm font-semibold" style={{ border: '1px solid var(--color-line-strong)', color: 'var(--color-muted)' }}>
          Reiniciar demonstração
        </button>
      </div>
    </div>
  )
}
