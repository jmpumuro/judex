import { create } from 'zustand'

export interface PolicyThresholds {
  unsafe: {
    violence: number
    sexual: number
    hate: number
    drugs: number
  }
  caution: {
    violence: number
    profanity: number
    drugs: number
    sexual: number
    hate: number
  }
}

export interface PolicyConfig {
  thresholds: PolicyThresholds
}

export type PolicyPreset = 'strict' | 'balanced' | 'lenient' | 'custom'

interface SettingsStore {
  currentPolicy: PolicyConfig | null
  currentPreset: PolicyPreset
  presets: Record<string, PolicyConfig>
  
  // Actions
  setCurrentPolicy: (policy: PolicyConfig) => void
  setCurrentPreset: (preset: PolicyPreset) => void
  setPresets: (presets: Record<string, PolicyConfig>) => void
  updateThreshold: (category: 'unsafe' | 'caution', key: string, value: number) => void
  applyPreset: (preset: PolicyPreset) => void
}

const defaultPolicy: PolicyConfig = {
  thresholds: {
    unsafe: {
      violence: 0.75,
      sexual: 0.60,
      hate: 0.60,
      drugs: 0.70,
    },
    caution: {
      violence: 0.40,
      profanity: 0.40,
      drugs: 0.40,
      sexual: 0.30,
      hate: 0.30,
    },
  },
}

export const useSettingsStore = create<SettingsStore>((set, get) => ({
  currentPolicy: defaultPolicy,
  currentPreset: 'balanced',
  presets: {},

  setCurrentPolicy: (policy) => set({ currentPolicy: policy }),

  setCurrentPreset: (preset) => set({ currentPreset: preset }),

  setPresets: (presets) => set({ presets }),

  updateThreshold: (category, key, value) => {
    const currentPolicy = get().currentPolicy
    if (!currentPolicy) return
    
    set({
      currentPolicy: {
        ...currentPolicy,
        thresholds: {
          ...currentPolicy.thresholds,
          [category]: {
            ...currentPolicy.thresholds[category],
            [key]: value,
          },
        },
      },
      currentPreset: 'custom',
    })
  },

  applyPreset: (preset) => {
    const presets = get().presets
    if (presets[preset]) {
      set({
        currentPolicy: presets[preset],
        currentPreset: preset,
      })
    }
  },
}))
