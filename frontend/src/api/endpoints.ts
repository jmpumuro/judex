/**
 * Judex API Client
 * 
 * Primary APIs:
 * - evaluationApi: POST /v1/evaluate, GET /v1/evaluations/*
 * - criteriaApi: GET /v1/criteria/*
 * - stageApi: GET /v1/evaluations/{id}/stages/*
 * - liveApi: POST /v1/live/*
 */
import axios from 'axios'

export const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8012'
const API_URL = `${API_BASE}/v1`

export const api = axios.create({
  baseURL: API_URL,
  timeout: 300000, // 5 minutes for long evaluations
})

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const message = error.response?.data?.detail || error.message || 'An error occurred'
    if (error.response?.status !== 404) {
      console.error('API Error:', message)
    }
    return Promise.reject(error)
  }
)

// ===== Types =====

export interface Evaluation {
  id: string
  status: string
  progress: number
  overall_verdict: string | null
  items_total: number
  items_completed: number
  items_failed: number
  criteria_id: string | null
  error_message: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  items?: EvaluationItem[]
}

export interface EvaluationItem {
  id: string
  evaluation_id: string
  filename: string
  source_type: string
  status: string
  progress: number
  current_stage: string | null
  duration: number | null
  artifacts: {
    uploaded_video: string | null
    labeled_video: string | null
    thumbnail: string | null
  }
  result?: {
    verdict: string
    confidence: number
    criteria: Record<string, any>
    violations: any[]
    processing_time: number | null
    report: string | null
  }
  created_at: string
  completed_at: string | null
}

export interface CriteriaSummary {
  id: string
  name: string
  description: string | null
  criteria_count: number
  is_preset: boolean
}

export interface CriteriaDetails {
  id: string | null
  name: string
  description: string | null
  criteria: {
    id: string
    label: string
    description: string | null
    severity: string
    enabled: boolean
    thresholds: { safe: number; caution: number; unsafe: number }
  }[]
  options: Record<string, any>
  detectors_required: string[]
  is_preset: boolean
}

// ===== STAGE TYPES =====

export interface StageInfo {
  type: string
  display_name: string
  description?: string
  is_external: boolean
  is_builtin: boolean
  enabled: boolean
  impact: 'critical' | 'supporting' | 'advisory'
  required: boolean
  input_keys: string[]
  output_keys: string[]
  display_color?: string
  icon?: string
  endpoint_url?: string
  last_toggled_at?: string
  toggle_reason?: string
}

export interface ToggleStageResponse {
  stage_id: string
  enabled: boolean
  was_enabled: boolean
  impact: string
  required: boolean
  warning?: string
}

export interface ExternalStageConfig {
  id: string
  name: string
  description?: string
  yaml_content: string
  stage_ids: string[]
  enabled: boolean
  validated: boolean
  validation_error?: string
  created_at?: string
  updated_at?: string
}

export interface ValidationResult {
  valid: boolean
  error?: string
  stages: { id: string; name: string; endpoint: string }[]
}

// ===== EVALUATION API =====

export const evaluationApi = {
  /**
   * Submit a new evaluation
   */
  create: async (params: {
    files?: File[]
    urls?: string[]
    criteriaId?: string
    criteria?: string
    async?: boolean
  }): Promise<Evaluation> => {
    const formData = new FormData()
    
    if (params.files) {
      params.files.forEach(file => formData.append('files', file))
    }
    if (params.urls) {
      formData.append('urls', params.urls.join(','))
    }
    if (params.criteriaId) {
      formData.append('criteria_id', params.criteriaId)
    }
    if (params.criteria) {
      formData.append('criteria', params.criteria)
    }
    formData.append('async', String(params.async ?? true))
    
    const { data } = await api.post<Evaluation>('/evaluate', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    return data
  },

  /**
   * Get evaluation status and results
   */
  get: async (evaluationId: string, includeItems = true): Promise<Evaluation> => {
    const { data } = await api.get<Evaluation>(`/evaluations/${evaluationId}`, {
      params: { include_items: includeItems }
    })
    return data
  },

  /**
   * List recent evaluations
   */
  list: async (limit = 50): Promise<{ evaluations: Evaluation[]; total: number }> => {
    const { data } = await api.get('/evaluations', { params: { limit } })
    return data
  },

  /**
   * Delete an evaluation
   */
  delete: async (evaluationId: string): Promise<void> => {
    await api.delete(`/evaluations/${evaluationId}`)
  },

  /**
   * Reprocess an evaluation with current stage settings
   */
  reprocess: async (evaluationId: string, skipEarlyStages: boolean = true): Promise<{
    status: string
    evaluation_id: string
    items_count: number
    skip_early_stages: boolean
  }> => {
    const { data } = await api.post(`/evaluations/${evaluationId}/reprocess`, null, {
      params: { skip_early_stages: skipEarlyStages }
    })
    return data
  },

  /**
   * Get all stage outputs for an evaluation
   */
  getStages: async (evaluationId: string, itemId?: string): Promise<any> => {
    const { data } = await api.get(`/evaluations/${evaluationId}/stages`, {
      params: itemId ? { item_id: itemId } : {}
    })
    return data
  },

  /**
   * Get specific stage output
   */
  getStage: async (evaluationId: string, stageName: string, itemId?: string): Promise<any> => {
    const { data } = await api.get(`/evaluations/${evaluationId}/stages/${stageName}`, {
      params: itemId ? { item_id: itemId } : {}
    })
    return data
  },

  /**
   * Get artifact metadata
   */
  getArtifact: async (evaluationId: string, artifactType: string, itemId?: string): Promise<any> => {
    const { data } = await api.get(`/evaluations/${evaluationId}/artifacts/${artifactType}`, {
      params: itemId ? { item_id: itemId } : {}
    })
    return data
  }
}

// ===== STAGE API =====

export const stageApi = {
  /**
   * Get all stage outputs for a video
   */
  getAllStages: async (evaluationId: string, itemId?: string) => {
    return evaluationApi.getStages(evaluationId, itemId)
  },

  /**
   * Get specific stage output
   */
  getStageOutput: async (evaluationId: string, stageName: string, itemId?: string) => {
    try {
      const result = await evaluationApi.getStage(evaluationId, stageName, itemId)
      // Extract the output for the specific item, or the first available
      const targetId = itemId || Object.keys(result.outputs || {})[0]
      return result.outputs?.[targetId] || null
    } catch (error) {
      console.warn(`Failed to get stage output:`, error)
      return null
    }
  }
}

// ===== CRITERIA API =====

export const criteriaApi = {
  /**
   * List preset criteria
   */
  listPresets: async (): Promise<CriteriaSummary[]> => {
    const { data } = await api.get<CriteriaSummary[]>('/criteria/presets')
    return data
  },

  /**
   * Get preset details
   */
  getPreset: async (presetId: string): Promise<CriteriaDetails> => {
    const { data } = await api.get<CriteriaDetails>(`/criteria/presets/${presetId}`)
    return data
  },

  /**
   * Export preset as YAML/JSON
   */
  exportPreset: async (presetId: string, format: 'yaml' | 'json' = 'yaml'): Promise<{ format: string; content: string; filename: string }> => {
    const { data } = await api.get(`/criteria/presets/${presetId}/export`, { params: { format } })
    return data
  },

  /**
   * Validate criteria configuration
   */
  validate: async (content: string, format: 'yaml' | 'json' = 'yaml'): Promise<{
    valid: boolean
    errors: string[]
    warnings: string[]
    detectors_required: string[]
  }> => {
    const formData = new FormData()
    formData.append('content', content)
    formData.append('format', format)
    const { data } = await api.post('/criteria/validate', formData)
    return data
  },

  /**
   * Save custom criteria
   */
  save: async (criteriaId: string, content: string, format: 'yaml' | 'json' = 'yaml'): Promise<any> => {
    const formData = new FormData()
    formData.append('criteria_id', criteriaId)
    formData.append('content', content)
    formData.append('format', format)
    const { data } = await api.post('/criteria', formData)
    return data
  },

  /**
   * List custom criteria
   */
  listCustom: async (): Promise<CriteriaSummary[]> => {
    const { data } = await api.get<CriteriaSummary[]>('/criteria/custom')
    return data
  },

  /**
   * Get custom criteria by ID
   */
  get: async (criteriaId: string): Promise<CriteriaDetails> => {
    const { data } = await api.get<CriteriaDetails>(`/criteria/custom/${criteriaId}`)
    return data
  },

  /**
   * Delete custom criteria
   */
  delete: async (criteriaId: string): Promise<void> => {
    await api.delete(`/criteria/custom/${criteriaId}`)
  }
}

// ===== STAGES API =====

export const stagesApi = {
  /**
   * List all available stages (builtin + external)
   */
  list: async (): Promise<{ stages: StageInfo[]; builtin_count: number; external_count: number }> => {
    const { data } = await api.get('/stages')
    return data
  },

  /**
   * List external stage configurations
   */
  listExternal: async (): Promise<ExternalStageConfig[]> => {
    const { data } = await api.get<ExternalStageConfig[]>('/stages/external')
    return data
  },

  /**
   * Create or update external stage config
   */
  createExternal: async (config: {
    id: string
    name: string
    description?: string
    yaml_content: string
    enabled?: boolean
  }): Promise<ExternalStageConfig> => {
    const { data } = await api.post<ExternalStageConfig>('/stages/external', config)
    return data
  },

  /**
   * Get external stage config by ID
   */
  getExternal: async (configId: string): Promise<ExternalStageConfig> => {
    const { data } = await api.get<ExternalStageConfig>(`/stages/external/${configId}`)
    return data
  },

  /**
   * Delete external stage config
   */
  deleteExternal: async (configId: string): Promise<void> => {
    await api.delete(`/stages/external/${configId}`)
  },

  /**
   * Validate YAML without saving
   */
  validateYaml: async (yaml_content: string): Promise<ValidationResult> => {
    const { data } = await api.post<ValidationResult>('/stages/external/validate', { yaml_content })
    return data
  },

  /**
   * Toggle external config enabled/disabled
   */
  toggleExternal: async (configId: string, enabled: boolean): Promise<void> => {
    await api.post(`/stages/external/${configId}/toggle`, { enabled })
  },

  /**
   * Toggle any stage (builtin or external)
   */
  toggleStage: async (stageId: string, enabled: boolean, reason?: string): Promise<ToggleStageResponse> => {
    const { data } = await api.post<ToggleStageResponse>(`/stages/${stageId}/toggle`, { 
      enabled,
      reason 
    })
    return data
  },

  /**
   * Get all stage settings (for debugging/admin)
   */
  getSettings: async (): Promise<{ settings: any[]; count: number }> => {
    const { data } = await api.get('/stages/settings')
    return data
  },
}

// ===== LIVE FEED API =====

export const liveApi = {
  analyzeFrame: async (imageData: string, streamId: string = 'webcam') => {
    const base64Data = imageData.replace(/^data:image\/\w+;base64,/, '')
    const binaryData = atob(base64Data)
    const bytes = new Uint8Array(binaryData.length)
    for (let i = 0; i < binaryData.length; i++) {
      bytes[i] = binaryData.charCodeAt(i)
    }
    const blob = new Blob([bytes], { type: 'image/jpeg' })
    
    const formData = new FormData()
    formData.append('frame', blob, 'frame.jpg')
    
    const { data } = await api.post(`/live/analyze-frame?stream_id=${streamId}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },
  startStream: async (config: any) => {
    const { data } = await api.post('/live/stream/start', config)
    return data
  },
  stopStream: async (streamId: string) => {
    const { data } = await api.post('/live/stream/stop', { stream_id: streamId })
    return data
  },
}

// ===== SSE CONNECTION =====

export const createSSEConnection = (evaluationId: string) => {
  const url = `${API_BASE}/v1/evaluations/${evaluationId}/events`
  return new EventSource(url)
}
