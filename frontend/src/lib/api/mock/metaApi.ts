import type { MetaApi } from '../contracts'
import { SENSOR, THRESHOLD } from './fixtures'

export const mockMetaApi: MetaApi = {
  async getSensor() { return SENSOR },
  async getThreshold() { return THRESHOLD },
}
