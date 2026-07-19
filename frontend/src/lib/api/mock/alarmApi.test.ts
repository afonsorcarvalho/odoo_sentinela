import { describe, it, expect } from 'vitest'
import { mockAlarmApi } from './alarmApi'

describe('mockAlarmApi', () => {
  it('listAlarms devolve ao menos 1 evento aberto e 1 resolvido, mais recente primeiro', async () => {
    const alarms = await mockAlarmApi.listAlarms()
    expect(alarms.some((a) => a.status === 'aberto')).toBe(true)
    expect(alarms.some((a) => a.status === 'resolvido')).toBe(true)
    const timestamps = alarms.map((a) => a.timestamp_deteccao)
    expect(timestamps).toEqual([...timestamps].sort((a, b) => b - a))
  })
})
