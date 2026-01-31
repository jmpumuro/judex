/**
 * Pipeline Store - Manages pipeline UI state and stage data
 *
 * This store handles:
 * - UI states (modals, panels, selections)
 * - Stage outputs and loading states
 * - SSE connections for real-time updates
 * - Available stages and criteria presets
 *
 * Industry Standard (Zustand v5):
 * - Select primitive values or stable references directly from store
 * - Derive complex/filtered data in components using useMemo
 */
import { create } from 'zustand'

// ============================================================================
// Types
// ============================================================================

export interface StageOutput {
  data: any
  timestamp: number
}

export interface CriteriaPreset {
  id: string
  name: string
  description?: string
  criteria_count: number
}

export interface CustomCriterion {
  id: string
  name: string
  description?: string
}

export interface PipelineStage {
  id: string
  backendId: string
  name: string
  number: string
  isExternal?: boolean
  displayColor?: string
  enabled?: boolean
  hasOverrides?: boolean
}

interface PipelineStore {
  // UI State
  showUploadModal: boolean
  uploadSource: 'local' | 'url' | 'storage' | 'database'
  showChat: boolean
  showPresetDropdown: boolean
  videoType: 'labeled' | 'original'

  // Selection State
  selectedStage: string | null
  selectedPreset: string | null

  // Stage Data State
  stageOutput: Record<string, StageOutput>  // keyed by "videoId-stageId"
  stageLoading: boolean
  completedStages: string[]

  // Error State
  videoError: boolean
  labeledVideoError: boolean

  // Configuration State
  presets: CriteriaPreset[]
  customCriteria: CustomCriterion[]
  availableStages: PipelineStage[]

  // SSE State
  sseConnections: Map<string, EventSource>

  // Actions - UI
  setShowUploadModal: (show: boolean) => void
  setUploadSource: (source: 'local' | 'url' | 'storage' | 'database') => void
  setShowChat: (show: boolean) => void
  setShowPresetDropdown: (show: boolean) => void
  setVideoType: (type: 'labeled' | 'original') => void

  // Actions - Selection
  setSelectedStage: (stageId: string | null) => void
  setSelectedPreset: (presetId: string | null) => void

  // Actions - Stage Data
  setStageOutput: (key: string, output: StageOutput) => void
  clearStageOutput: (videoId: string) => void
  setStageLoading: (loading: boolean) => void
  addCompletedStage: (stageId: string) => void
  clearCompletedStages: () => void

  // Actions - Error
  setVideoError: (error: boolean) => void
  setLabeledVideoError: (error: boolean) => void

  // Actions - Configuration
  setPresets: (presets: CriteriaPreset[]) => void
  setCustomCriteria: (criteria: CustomCriterion[]) => void
  setAvailableStages: (stages: PipelineStage[]) => void

  // Actions - SSE
  addSSEConnection: (key: string, connection: EventSource) => void
  removeSSEConnection: (key: string) => void
  closeAllSSEConnections: () => void

  // Reset
  resetPipelineState: () => void
}

// ============================================================================
// Store Implementation
// ============================================================================

const initialState = {
  // UI State
  showUploadModal: false,
  uploadSource: 'local' as const,
  showChat: false,
  showPresetDropdown: false,
  videoType: 'labeled' as const,

  // Selection State
  selectedStage: null,
  selectedPreset: null,

  // Stage Data State
  stageOutput: {},
  stageLoading: false,
  completedStages: [],

  // Error State
  videoError: false,
  labeledVideoError: false,

  // Configuration State
  presets: [],
  customCriteria: [],
  availableStages: [],

  // SSE State
  sseConnections: new Map(),
}

export const usePipelineStore = create<PipelineStore>((set, get) => ({
  ...initialState,

  // UI Actions
  setShowUploadModal: (show) => set({ showUploadModal: show }),
  setUploadSource: (source) => set({ uploadSource: source }),
  setShowChat: (show) => set({ showChat: show }),
  setShowPresetDropdown: (show) => set({ showPresetDropdown: show }),
  setVideoType: (type) => set({ videoType: type }),

  // Selection Actions
  setSelectedStage: (stageId) => set({ selectedStage: stageId }),
  setSelectedPreset: (presetId) => set({ selectedPreset: presetId }),

  // Stage Data Actions
  setStageOutput: (key, output) => set((state) => ({
    stageOutput: { ...state.stageOutput, [key]: output }
  })),

  clearStageOutput: (videoId) => set((state) => {
    const newOutput = { ...state.stageOutput }
    Object.keys(newOutput).forEach(key => {
      if (key.startsWith(`${videoId}-`)) {
        delete newOutput[key]
      }
    })
    return { stageOutput: newOutput }
  }),

  setStageLoading: (loading) => set({ stageLoading: loading }),

  addCompletedStage: (stageId) => set((state) => ({
    completedStages: state.completedStages.includes(stageId)
      ? state.completedStages
      : [...state.completedStages, stageId]
  })),

  clearCompletedStages: () => set({ completedStages: [] }),

  // Error Actions
  setVideoError: (error) => set({ videoError: error }),
  setLabeledVideoError: (error) => set({ labeledVideoError: error }),

  // Configuration Actions
  setPresets: (presets) => set({ presets }),
  setCustomCriteria: (criteria) => set({ customCriteria: criteria }),
  setAvailableStages: (stages) => set({ availableStages: stages }),

  // SSE Actions
  addSSEConnection: (key, connection) => set((state) => {
    const newConnections = new Map(state.sseConnections)
    // Close existing connection if any
    const existing = newConnections.get(key)
    if (existing) {
      existing.close()
    }
    newConnections.set(key, connection)
    return { sseConnections: newConnections }
  }),

  removeSSEConnection: (key) => set((state) => {
    const newConnections = new Map(state.sseConnections)
    const connection = newConnections.get(key)
    if (connection) {
      connection.close()
      newConnections.delete(key)
    }
    return { sseConnections: newConnections }
  }),

  closeAllSSEConnections: () => {
    const connections = get().sseConnections
    connections.forEach(conn => conn.close())
    set({ sseConnections: new Map() })
  },

  // Reset
  resetPipelineState: () => set(initialState),
}))

// ============================================================================
// Selectors
// ============================================================================

export const selectStageOutput = (videoId: string, stageId: string) => (state: PipelineStore) =>
  state.stageOutput[`${videoId}-${stageId}`]

export const selectHasStageOutput = (videoId: string, stageId: string) => (state: PipelineStore) =>
  !!state.stageOutput[`${videoId}-${stageId}`]
