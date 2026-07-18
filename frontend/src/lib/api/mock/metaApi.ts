import type { MetaApi } from '../contracts'
import { SENSORS, THRESHOLDS } from './fixtures'

export const mockMetaApi: MetaApi = {
  async getSensor(code) {
    const found = SENSORS.find((s) => s.sensor_code === code)
    if (!found) throw new Error(`sensor nao encontrado: ${code}`)
    return found
  },
  async getThreshold(code) {
    if (!(code in THRESHOLDS)) throw new Error(`sensor nao encontrado: ${code}`)
    return THRESHOLDS[code]
  },
  async listSensors() {
    return SENSORS
  },
}
