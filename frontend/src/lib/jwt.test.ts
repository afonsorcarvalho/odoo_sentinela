import { describe, it, expect } from 'vitest'
import { decodeJwtExp } from './jwt'

function b64url(obj: object): string {
  return btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function makeJwt(payload: object): string {
  return `${b64url({ alg: 'HS256', typ: 'JWT' })}.${b64url(payload)}.fake-signature`
}

describe('decodeJwtExp', () => {
  it('decodifica exp de um JWT valido (segundos -> ms)', () => {
    const token = makeJwt({ sub: '2', partner_id: 3, exp: 1784399777 })
    expect(decodeJwtExp(token)).toBe(1784399777 * 1000)
  })

  it('decodifica um JWT REAL emitido pela API (Fase 3, capturado via curl)', () => {
    const real =
      'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyIiwicGFydG5lcl9pZCI6MywiZXhwIjoxNzg0Mzk5Nzc3fQ.uAEPdegFf2aPpqX-eLPRwb7GaE6u1psq0RH9M_B1Bw4'
    expect(decodeJwtExp(real)).toBe(1784399777 * 1000)
  })

  it('token malformado (sem 3 segmentos) devolve null, nao lanca', () => {
    expect(decodeJwtExp('nao-e-um-jwt')).toBeNull()
  })

  it('payload sem exp devolve null', () => {
    const token = makeJwt({ sub: '2' })
    expect(decodeJwtExp(token)).toBeNull()
  })

  it('payload nao-JSON valido devolve null, nao lanca', () => {
    expect(decodeJwtExp('abc.###.def')).toBeNull()
  })
})
