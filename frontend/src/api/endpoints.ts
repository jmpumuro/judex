import axios from 'axios'
import toast from 'react-hot-toast'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8012'
const API_URL = `${API_BASE}/v1`

export const api = axios.create({
  baseURL: API_URL,
  timeout: 120000,
})

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const message = error.response?.data?.detail || error.message || 'An error occurred'
    // Don't show toast for expected errors
    if (error.response?.status !== 404) {
      console.error('API Error:', message)
    }
    return Promise.reject(error)
  }
)

// ===== VIDEO EVALUATION API =====

export const evaluationApi = {
  // Upload and process batch of videos
  uploadBatch: async (files: File[], policy?: any) => {
    const formData = new FormData()
    files.forEach(file => formData.append('files', file))
    if (policy) formData.append('policy', JSON.stringify(policy))
    
    const { data } = await api.post('/evaluate/batch', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },

  // Get batch status
  getBatchStatus: async (batchId: string) => {
    const { data } = await api.get(`/evaluate/batch/${batchId}`)
    return data
  },

  // Single video evaluation (production API)
  evaluateVideo: async (file: File, policy?: any) => {
    const formData = new FormData()
    formData.append('video', file)
    if (policy) formData.append('policy_override', JSON.stringify(policy))
    
    const { data } = await api.post('/evaluate', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },
}

// ===== VIDEO API =====

export const videoApi = {
  // Get labeled video URL - use relative path for Vite proxy
  getLabeledVideoUrl: (videoId: string) => `/v1/video/labeled/${videoId}`,
  
  // Get uploaded (original) video URL - use relative path for Vite proxy
  getUploadedVideoUrl: (videoId: string) => `/v1/video/uploaded/${videoId}`,

  // Get video as blob
  getLabeledVideo: async (videoId: string) => {
    const { data } = await api.get(`/video/labeled/${videoId}`, { responseType: 'blob' })
    return data
  },

  getUploadedVideo: async (videoId: string) => {
    const { data } = await api.get(`/video/uploaded/${videoId}`, { responseType: 'blob' })
    return data
  },
}

// ===== RESULTS API =====

export const resultsApi = {
  // Load saved results
  load: async () => {
    try {
      const { data } = await api.get('/results/load')
      return data.results || []
    } catch {
      return []
    }
  },

  // Save results
  save: async (results: any[]) => {
    const { data } = await api.post('/results/save', results)
    return data
  },

  // Delete a result
  delete: async (videoId: string) => {
    await api.delete(`/results/${videoId}`)
  },

  // Clear all results
  clearAll: async () => {
    await api.delete('/results')
  },
}

// ===== CHECKPOINTS API =====

export const checkpointsApi = {
  // List all checkpoints
  list: async () => {
    try {
      const { data } = await api.get('/checkpoints/list')
      return data.checkpoints || []
    } catch {
      return []
    }
  },

  // Load a specific checkpoint
  load: async (videoId: string) => {
    const { data } = await api.get(`/checkpoints/load/${videoId}`)
    return data.checkpoint || data
  },

  // Delete a checkpoint
  delete: async (videoId: string) => {
    await api.delete(`/checkpoints/${videoId}`)
  },

  // Clear all checkpoints
  clearAll: async () => {
    await api.delete('/checkpoints')
  },
}

// ===== STAGE OUTPUT API =====

export const stageApi = {
  // Get all completed stage outputs for a video
  getAllStages: async (videoId: string) => {
    try {
      const { data } = await api.get(`/video/${videoId}/stages`)
      return data
    } catch {
      return { stages: {}, completed_stages: [] }
    }
  },

  // Get specific stage output
  getStageOutput: async (videoId: string, stageName: string) => {
    try {
      const { data } = await api.get(`/video/${videoId}/stage/${stageName}`)
      return data.output || null
    } catch {
      return null
    }
  },
}

// ===== POLICY API =====

export const policyApi = {
  // Get policy presets
  getPresets: async () => {
    const { data } = await api.get('/policy/presets')
    return data.presets
  },

  // Get current policy
  getCurrent: async () => {
    const { data } = await api.get('/policy/current')
    return data.policy
  },

  // Validate policy
  validate: async (policy: any) => {
    const { data } = await api.post('/policy/validate', policy)
    return data
  },
}

// ===== LIVE FEED API =====

export const liveApi = {
  // Analyze a single frame (send as file upload)
  analyzeFrame: async (imageData: string, streamId: string = 'webcam') => {
    // Convert base64 to blob
    const base64Data = imageData.replace(/^data:image\/\w+;base64,/, '')
    const binaryData = atob(base64Data)
    const bytes = new Uint8Array(binaryData.length)
    for (let i = 0; i < binaryData.length; i++) {
      bytes[i] = binaryData.charCodeAt(i)
    }
    const blob = new Blob([bytes], { type: 'image/jpeg' })
    
    // Create form data
    const formData = new FormData()
    formData.append('frame', blob, 'frame.jpg')
    
    const { data } = await api.post(`/live/analyze-frame?stream_id=${streamId}`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },

  // Start a live stream
  startStream: async (config: any) => {
    const { data } = await api.post('/live/stream/start', config)
    return data
  },

  // Stop a live stream
  stopStream: async (streamId: string) => {
    const { data } = await api.post('/live/stream/stop', { stream_id: streamId })
    return data
  },
}

// ===== IMPORT API =====

export const importApi = {
  // Import from URLs
  fromUrls: async (urls: string[]) => {
    const { data } = await api.post('/import/urls', { urls })
    return data
  },
}

// ===== SSE CONNECTION =====

export const createSSEConnection = (videoId: string) => {
  // Use relative URL to go through Vite proxy (handles CORS and buffering)
  const url = `/v1/sse/${videoId}`
  const eventSource = new EventSource(url)
  return eventSource
}

// ===== MODELS API =====

export const modelsApi = {
  // Get available models
  list: async () => {
    const { data } = await api.get('/models')
    return data.models
  },
}

// Export base URL for direct access
export { API_URL, API_BASE }
