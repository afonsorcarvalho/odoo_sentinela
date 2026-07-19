// Decodifica so o payload de um JWT (base64url, 2o segmento) pra ler `exp`.
// NAO verifica assinatura -- isso e responsabilidade do servidor a cada
// request autenticada. Uso client-side e so pra saber quando encerrar a
// sessao local (nao e um controle de seguranca).
export function decodeJwtExp(token: string): number | null {
  const parts = token.split('.')
  if (parts.length !== 3) return null
  try {
    const payloadB64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const json = atob(payloadB64)
    const payload = JSON.parse(json) as { exp?: number }
    if (typeof payload.exp !== 'number') return null
    return payload.exp * 1000 // segundos -> ms
  } catch {
    return null
  }
}

// Le um claim qualquer do payload de um JWT (base64url, 2o segmento).
// NAO verifica assinatura -- mesma ressalva de decodeJwtExp acima.
export function decodeJwtClaim(token: string, claim: string): unknown {
  try {
    const payload = token.split('.')[1]
    if (!payload) return null
    const json = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')))
    return json[claim] ?? null
  } catch {
    return null
  }
}
