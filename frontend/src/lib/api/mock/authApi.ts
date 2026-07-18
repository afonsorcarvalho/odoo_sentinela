import type { AuthApi } from '../contracts'

// Mesma convencao das outras fixtures mock (liveApi.ts/historyApi.ts): base
// de tempo fixa, nao Date.now(), pra manter os testes deterministicos.
const MOCK_ISSUED_AT_S = 1_700_000_000
const EXP_SECONDS = 3600

// Formato JWT genuino (3 segmentos base64url) mesmo sendo mock -- assim
// decodeJwtExp funciona identico pro mock e pro real, sem logica duplicada.
// A "assinatura" e so um placeholder de texto -- nada verifica ela no mock.
function b64url(obj: object): string {
  return btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function makeFakeJwt(): string {
  const header = { alg: 'HS256', typ: 'JWT' }
  const payload = { sub: '1', partner_id: 1, exp: MOCK_ISSUED_AT_S + EXP_SECONDS }
  return `${b64url(header)}.${b64url(payload)}.mock-signature-nao-verificada`
}

export const mockAuthApi: AuthApi = {
  async login(usuario, senha) {
    // Mesma credencial de teste que a API real (Fase 3) usa -- ensina a
    // credencial certa pra quando acoplar de verdade.
    if (usuario !== 'admin' || senha !== 'admin') {
      throw new Error('credenciais inválidas')
    }
    return { access_token: makeFakeJwt(), token_type: 'bearer' }
  },
}
