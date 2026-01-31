/**
 * API Client - Clean interface to backend API.
 * 
 * Uses the new evaluation-centric API:
 * - POST /v1/evaluate - Submit evaluation
 * - GET /v1/evaluations/{id} - Get status/results
 * - GET /v1/evaluations/{id}/events - SSE progress
 * - GET /v1/evaluations/{id}/artifacts/{type} - Get artifacts
 * - GET /v1/criteria/* - Criteria management
 */
import axios from 'axios'
import type {
  Evaluation,
  EvaluationSummary,
  EvaluationListResponse,
  EvaluationItem,
  CriteriaSummary,
  CriteriaDetail,
  Artifact,
  StageOutput,
  Health,
  FramesResponse,
} from '@/types/api'

// API base URL - in dev this goes through Vite proxy, in prod it's the same origin
export const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8012'

// Axios instance with default config
export const api = axios.create({
  baseURL: `${API_BASE}/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Error handling interceptor
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const message = error.response?.data?.detail || error.message || 'API Error'
    console.error('API Error:', message)
    return Promise.reject(error)
  }
)

// ============================================================================
// Evaluation API
// ============================================================================

export const evaluations = {
  /**
   * Submit a new evaluation.
   * Returns evaluation ID for tracking.
   */
  create: async (params: {
    files?: File[]
    urls?: string[]
    criteriaId?: string
    criteriaYaml?: string
    criteriaJson?: string
    isAsync?: boolean
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
    if (params.criteriaYaml) {
      formData.append('criteria', params.criteriaYaml)
    }
    if (params.criteriaJson) {
      formData.append('criteria', params.criteriaJson)
    }
    formData.append('async', String(params.isAsync ?? true))
    
    const { data } = await api.post<Evaluation>('/evaluate', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },
  
  /**
   * Get evaluation by ID.
   */
  get: async (id: string, includeItems = true): Promise<Evaluation> => {
    const { data } = await api.get<Evaluation>(`/evaluations/${id}`, {
      params: { include_items: includeItems }
    })
    return data
  },
  
  /**
   * List recent evaluations.
   */
  list: async (limit = 50, status?: string): Promise<EvaluationListResponse> => {
    const { data } = await api.get<EvaluationListResponse>('/evaluations', {
      params: { limit, status }
    })
    return data
  },
  
  /**
   * Delete an evaluation.
   */
  delete: async (id: string): Promise<void> => {
    await api.delete(`/evaluations/${id}`)
  },
  
  /**
   * Create SSE connection for progress updates.
   */
  createEventSource: (id: string): EventSource => {
    return new EventSource(`${API_BASE}/v1/evaluations/${id}/events`)
  },
  
  /**
   * Get stage outputs for debugging.
   */
  getStages: async (id: string): Promise<StageOutput[]> => {
    const { data } = await api.get<{ stages: StageOutput[] }>(`/evaluations/${id}/stages`)
    return data.stages || []
  },
  
  /**
   * Get specific stage output.
   */
  getStageOutput: async (id: string, stageName: string): Promise<StageOutput | null> => {
    const { data } = await api.get<StageOutput>(`/evaluations/${id}/stages/${stageName}`)
    return data
  },
  
  /**
   * Get artifact URL (labeled video, thumbnail, etc.)
   */
  getArtifact: async (id: string, type: string, itemId?: string): Promise<Artifact> => {
    const { data } = await api.get<Artifact>(`/evaluations/${id}/artifacts/${type}`, {
      params: itemId ? { item_id: itemId } : undefined
    })
    return data
  },
  
  /**
   * Get direct URL for labeled video (streams content through API).
   */
  getLabeledVideoUrl: (evaluationId: string, itemId: string): string => {
    return `${API_BASE}/v1/evaluations/${evaluationId}/artifacts/labeled_video?item_id=${itemId}&stream=true`
  },
  
  /**
   * Get direct URL for uploaded video (streams content through API).
   */
  getUploadedVideoUrl: (evaluationId: string, itemId: string): string => {
    return `${API_BASE}/v1/evaluations/${evaluationId}/artifacts/uploaded_video?item_id=${itemId}&stream=true`
  },
  
  /**
   * Get processed frames (keyframes extracted during segmentation).
   * Supports pagination for long videos.
   * 
   * @param evaluationId - Evaluation ID
   * @param itemId - Item ID (required for multi-item evaluations)
   * @param page - Page number (1-indexed)
   * @param pageSize - Items per page (max 200)
   * @param thumbnails - If true, returns thumbnail URLs (default); if false, full-size frames
   */
  getFrames: async (
    evaluationId: string, 
    itemId?: string, 
    page = 1, 
    pageSize = 50,
    thumbnails = true
  ): Promise<FramesResponse> => {
    const { data } = await api.get<FramesResponse>(`/evaluations/${evaluationId}/frames`, {
      params: { 
        item_id: itemId,
        page,
        page_size: pageSize,
        thumbnails
      }
    })
    return data
  },
  
  /**
   * Get URL for a full-size frame image.
   */
  getFrameUrl: (evaluationId: string, filename: string, itemId: string): string => {
    // Convert thumbnail filename to frame filename if needed
    const frameFilename = filename.replace(/^thumb_/, 'frame_')
    return `${API_BASE}/v1/evaluations/${evaluationId}/frames/${frameFilename}?item_id=${itemId}&stream=true`
  },
  
  /**
   * Get URL for a thumbnail image (small, for filmstrip display).
   */
  getThumbnailUrl: (evaluationId: string, filename: string, itemId: string): string => {
    // Convert frame filename to thumbnail filename if needed
    const thumbFilename = filename.replace(/^frame_/, 'thumb_')
    return `${API_BASE}/v1/evaluations/${evaluationId}/thumbnails/${thumbFilename}?item_id=${itemId}&stream=true`
  },
}

// ============================================================================
// Criteria API
// ============================================================================

export const criteria = {
  /**
   * List available presets.
   */
  listPresets: async (): Promise<CriteriaSummary[]> => {
    const { data } = await api.get<CriteriaSummary[]>('/criteria/presets')
    return data
  },
  
  /**
   * Get preset details.
   */
  getPreset: async (id: string): Promise<CriteriaDetail> => {
    const { data } = await api.get<CriteriaDetail>(`/criteria/presets/${id}`)
    return data
  },
  
  /**
   * Export preset as YAML/JSON.
   */
  exportPreset: async (id: string, format: 'yaml' | 'json' = 'yaml'): Promise<string> => {
    const { data } = await api.get<{ content: string }>(`/criteria/presets/${id}/export`, {
      params: { format }
    })
    return data.content
  },
  
  /**
   * List custom (user-saved) criteria.
   */
  listCustom: async (): Promise<CriteriaSummary[]> => {
    const { data } = await api.get<CriteriaSummary[]>('/criteria/custom')
    return data
  },
  
  /**
   * Get custom criteria by ID.
   */
  getCustom: async (id: string): Promise<CriteriaDetail> => {
    const { data } = await api.get<CriteriaDetail>(`/criteria/custom/${id}`)
    return data
  },
  
  /**
   * Save custom criteria.
   */
  saveCustom: async (name: string, content: string, format: 'yaml' | 'json' = 'yaml'): Promise<CriteriaSummary> => {
    const formData = new FormData()
    formData.append('name', name)
    formData.append('content', content)
    formData.append('format', format)
    
    const { data } = await api.post<CriteriaSummary>('/criteria', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },
  
  /**
   * Delete custom criteria.
   */
  deleteCustom: async (id: string): Promise<void> => {
    await api.delete(`/criteria/custom/${id}`)
  },
  
  /**
   * Validate criteria configuration.
   */
  validate: async (content: string, format: 'yaml' | 'json' = 'yaml'): Promise<{ valid: boolean; errors: string[] }> => {
    const formData = new FormData()
    formData.append('content', content)
    formData.append('format', format)
    
    const { data } = await api.post<{ valid: boolean; errors: string[] }>('/criteria/validate', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },
}

// ============================================================================
// Health API
// ============================================================================

export const health = {
  check: async (): Promise<Health> => {
    const { data } = await api.get<Health>('/health')
    return data
  },
}

// ============================================================================
// Chat API (ReportChat Agent)
// ============================================================================

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  tool_calls?: any[]
  metadata?: Record<string, any>
  timestamp: string
}

export interface ChatResponse {
  thread_id: string
  evaluation_id: string
  messages: ChatMessage[]
  tool_trace?: {
    steps: any[]
    tools_called: number
  }
  suggested_questions?: string[]
}

export interface ThreadResponse {
  thread_id: string
  evaluation_id: string
  messages: ChatMessage[]
  message_count: number
  created_at?: string
  updated_at?: string
}

export const chat = {
  /**
   * Start a new chat thread with the initial report.
   */
  startThread: async (evaluationId: string, threadId?: string): Promise<ChatResponse> => {
    const { data } = await api.post<ChatResponse>(
      `/evaluations/${evaluationId}/chat/start`,
      { thread_id: threadId }
    )
    return data
  },

  /**
   * Send a message to the chat agent.
   */
  sendMessage: async (
    evaluationId: string, 
    threadId: string, 
    message: string
  ): Promise<ChatResponse> => {
    const { data } = await api.post<ChatResponse>(
      `/evaluations/${evaluationId}/chat`,
      { thread_id: threadId, message }
    )
    return data
  },

  /**
   * Get full thread history.
   */
  getThread: async (evaluationId: string, threadId: string): Promise<ThreadResponse> => {
    const { data } = await api.get<ThreadResponse>(
      `/evaluations/${evaluationId}/chat/${threadId}`
    )
    return data
  },

  /**
   * Get suggested questions for an evaluation.
   */
  getSuggestedQuestions: async (evaluationId: string): Promise<{ questions: string[] }> => {
    const { data } = await api.get<{ questions: string[] }>(
      `/evaluations/${evaluationId}/chat/questions`
    )
    return data
  },
}

// ============================================================================
// Default export - full API client
// ============================================================================

export default {
  evaluations,
  criteria,
  health,
  chat,
  // Raw axios instance for custom requests
  raw: api,
}
