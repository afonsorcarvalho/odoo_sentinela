import { describe, it, expect, vi, afterEach } from 'vitest'
import { realMetaApi } from './metaApi'

afterEach(() => vi.unstubAllGlobals())

const SENSOR = {
  sensor_code: 'SNR-1',
  name: 'Sensor 1',
  unidade: 'C',
  protocolo_origem: '4-20ma',
  measurement_type: { code: 'TEMP', name: 'Temperatura' },
  area: { area_code: 'AREA-1', name: 'Expurgo', category: 'CME' },
}

describe('realMetaApi', () => {
  it('getSensor chama GET /sensores/{code} e devolve o JSON', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => SENSOR })
    vi.stubGlobal('fetch', mockFetch)

    const result = await realMetaApi.getSensor('SNR-1')

    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('/sensores/SNR-1'), expect.anything())
    expect(result).toEqual(SENSOR)
  })

  it('getThreshold chama GET /sensores/{code}/threshold e devolve o JSON (podendo ser null)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => null }))

    const result = await realMetaApi.getThreshold('SNR-SEM-THRESHOLD')

    expect(result).toBeNull()
  })

  it('getThreshold com sensor inexistente (404) lanca erro', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404, json: async () => ({}) }))

    await expect(realMetaApi.getThreshold('SNR-NAO-EXISTE')).rejects.toThrow()
  })

  it('listSensors chama GET /sensores e devolve a lista', async () => {
    const mockFetch = vi.fn().mockResolvedValue({ ok: true, json: async () => [SENSOR] })
    vi.stubGlobal('fetch', mockFetch)

    const result = await realMetaApi.listSensors()

    expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('/sensores'), expect.anything())
    expect(result).toEqual([SENSOR])
  })
})
