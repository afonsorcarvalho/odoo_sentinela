// Placeholder generico exibido por um widget quando o binding (areaCode /
// sensorCode) configurado no layout nao resolve para dado real -- ex.: area
// removida do cadastro depois do widget ja ter sido salvo no layout do site.
export function WidgetPlaceholder({ texto }: { texto: string }) {
  return (
    <div
      className="flex h-full items-center justify-center rounded-lg border border-dashed p-3 text-center text-xs"
      style={{ color: 'var(--color-muted)', borderColor: 'var(--color-muted)' }}
    >
      {texto}
    </div>
  )
}
