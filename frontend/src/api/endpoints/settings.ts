import apiClient from '../client'
import { PolicyConfig } from '@/types'

export const settingsApi = {
  // Get policy presets
  getPresets: async (): Promise<Record<string, PolicyConfig>> => {
    const { data } = await apiClient.get('/policy/presets')
    return data.presets
  },

  // Get current policy
  getCurrentPolicy: async (): Promise<PolicyConfig> => {
    const { data } = await apiClient.get('/policy/current')
    return data.policy
  },

  // Validate policy
  validatePolicy: async (policy: PolicyConfig): Promise<{ status: string; message: string }> => {
    const { data } = await apiClient.post('/policy/validate', policy)
    return data
  },
}
