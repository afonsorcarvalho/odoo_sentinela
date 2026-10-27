import type { AlarmTipoViolacao } from './types'

// Texto humano de tipo_violacao (AlarmItem / Toast).
export const VIOLACAO_LABEL: Record<AlarmTipoViolacao, string> = {
  acima_limite: 'Acima do limite',
  abaixo_limite: 'Abaixo do limite',
  sensor_offline: 'Sem comunicação',
  erro_leitura: 'Leitura inválida',
  falha_sensor: 'Falha do sensor',
}

// Violacoes de instrumento: o valor lido nao e medicao, nao faz sentido
// mostrar "Valor lido X (limite Y)".
export function isViolacaoInstrumento(t: AlarmTipoViolacao): boolean {
  return t === 'falha_sensor' || t === 'sensor_offline' || t === 'erro_leitura'
}
