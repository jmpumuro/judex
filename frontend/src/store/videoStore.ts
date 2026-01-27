import { create } from 'zustand'

export type VideoStatus = 'queued' | 'processing' | 'completed' | 'failed'
export type VideoSource = 'local' | 'url' | 'storage' | 'database'
export type Verdict = 'SAFE' | 'CAUTION' | 'UNSAFE' | 'NEEDS_REVIEW'

export interface VideoResult {
  verdict: Verdict
  confidence: number
  criteria: Record<string, any>
  evidence: {
    violence?: Array<{ start_time: number; end_time: number; violence_score: number }>
    transcription?: Array<{ timestamp: number; text: string }>
    ocr?: Array<{ timestamp: number; text: string }>
    detections?: any[]
  }
  metadata?: {
    duration: number
    fps: number
    width: number
    height: number
    has_audio: boolean
  }
  summary?: string
  model_versions?: Record<string, string>
}

export interface QueueVideo {
  id: string
  filename: string
  file: File | null
  status: VideoStatus
  source: VideoSource
  progress: number
  currentStage?: string
  statusMessage?: string
  verdict?: Verdict
  duration?: string
  result?: VideoResult
  batchVideoId?: string
  error?: string
  uploadedAt: number
}

interface VideoStore {
  queue: QueueVideo[]
  selectedVideoId: string | null
  processingBatch: boolean
  currentBatchId: string | null
  
  // Actions
  addVideos: (videos: Omit<QueueVideo, 'id' | 'uploadedAt'>[]) => string[]
  updateVideo: (id: string, updates: Partial<QueueVideo>) => void
  removeVideo: (id: string) => void
  selectVideo: (id: string | null) => void
  clearCompleted: () => void
  setProcessingBatch: (processing: boolean) => void
  setCurrentBatchId: (batchId: string | null) => void
  getVideoById: (id: string) => QueueVideo | undefined
  getVideoByBatchId: (batchVideoId: string) => QueueVideo | undefined
  loadSavedResults: (results: any[]) => void
}

const generateId = () => `vid_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`

export const useVideoStore = create<VideoStore>((set, get) => ({
  queue: [],
  selectedVideoId: null,
  processingBatch: false,
  currentBatchId: null,

  addVideos: (videos) => {
    const newVideos: QueueVideo[] = videos.map(v => ({
      ...v,
      id: generateId(),
      uploadedAt: Date.now(),
    }))
    
    set(state => ({
      queue: [...state.queue, ...newVideos]
    }))
    
    return newVideos.map(v => v.id)
  },

  updateVideo: (id, updates) => {
    set(state => ({
      queue: state.queue.map(v => 
        v.id === id ? { ...v, ...updates } : v
      )
    }))
  },

  removeVideo: (id) => {
    set(state => ({
      queue: state.queue.filter(v => v.id !== id),
      selectedVideoId: state.selectedVideoId === id ? null : state.selectedVideoId
    }))
  },

  selectVideo: (id) => {
    set({ selectedVideoId: id })
  },

  clearCompleted: () => {
    set(state => ({
      queue: state.queue.filter(v => v.status !== 'completed' && v.status !== 'failed')
    }))
  },

  setProcessingBatch: (processing) => {
    set({ processingBatch: processing })
  },

  setCurrentBatchId: (batchId) => {
    set({ currentBatchId: batchId })
  },

  getVideoById: (id) => {
    return get().queue.find(v => v.id === id)
  },

  getVideoByBatchId: (batchVideoId) => {
    return get().queue.find(v => v.batchVideoId === batchVideoId)
  },

  loadSavedResults: (results) => {
    set(state => {
      const existingIds = new Set(state.queue.map(v => v.id))
      const newVideos = results
        .filter((r: any) => !existingIds.has(r.id))
        .map((r: any) => ({
          id: r.id,
          filename: r.filename,
          file: null,
          status: r.status as VideoStatus,
          source: 'local' as VideoSource,
          progress: 100,
          verdict: r.verdict,
          duration: r.duration,
          result: r.result,
          batchVideoId: r.batchVideoId,
          uploadedAt: r.timestamp ? new Date(r.timestamp).getTime() : Date.now(),
        }))
      
      return {
        queue: [...state.queue, ...newVideos]
      }
    })
  },
}))
