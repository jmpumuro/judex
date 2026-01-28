/**
 * Video Queue Store - Manages the queue of videos being evaluated.
 * 
 * This store handles:
 * - Queue of videos pending/processing/completed
 * - Progress tracking during evaluation
 * - Selection state for the UI
 */
import { create } from 'zustand'
import type { EvaluationStatus, Verdict, EvaluationResult } from '@/types/api'

// ============================================================================
// Types
// ============================================================================

export type VideoSource = 'local' | 'url' | 'storage'

export interface QueueVideo {
  id: string
  filename: string
  file: File | null
  status: EvaluationStatus
  source: VideoSource
  progress: number
  currentStage?: string
  statusMessage?: string
  verdict?: Verdict
  duration?: string
  result?: EvaluationResult
  
  // Evaluation tracking
  evaluationId?: string    // ID of the evaluation this video belongs to
  itemId?: string          // ID of this item within the evaluation (for batch)
  
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
  clearQueue: () => void
  selectVideo: (id: string | null) => void
  getVideoById: (id: string) => QueueVideo | undefined
  getVideoByItemId: (itemId: string) => QueueVideo | undefined
  setProcessingBatch: (processing: boolean) => void
  setCurrentBatchId: (batchId: string | null) => void
}

// ============================================================================
// Store Implementation
// ============================================================================

export const useVideoStore = create<VideoStore>((set, get) => ({
  queue: [],
  selectedVideoId: null,
  processingBatch: false,
  currentBatchId: null,
  
  addVideos: (videos) => {
    const ids: string[] = []
    const newVideos = videos.map(video => {
      const id = `video-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
      ids.push(id)
      return {
        ...video,
        id,
        uploadedAt: Date.now(),
      }
    })
    
    set(state => ({
      queue: [...state.queue, ...newVideos]
    }))
    
    return ids
  },
  
  updateVideo: (id, updates) => {
    set(state => ({
      queue: state.queue.map(video =>
        video.id === id ? { ...video, ...updates } : video
      )
    }))
  },
  
  removeVideo: (id) => {
    set(state => ({
      queue: state.queue.filter(video => video.id !== id),
      selectedVideoId: state.selectedVideoId === id ? null : state.selectedVideoId
    }))
  },
  
  clearQueue: () => {
    set({ queue: [], selectedVideoId: null })
  },
  
  selectVideo: (id) => {
    set({ selectedVideoId: id })
  },
  
  getVideoById: (id) => {
    return get().queue.find(video => video.id === id)
  },
  
  getVideoByItemId: (itemId) => {
    return get().queue.find(video => video.itemId === itemId)
  },
  
  setProcessingBatch: (processing) => {
    set({ processingBatch: processing })
  },
  
  setCurrentBatchId: (batchId) => {
    set({ currentBatchId: batchId })
  },
}))

// ============================================================================
// Selectors (for performance optimization)
// ============================================================================

export const selectSelectedVideo = (state: VideoStore) => 
  state.queue.find(v => v.id === state.selectedVideoId)

export const selectQueuedVideos = (state: VideoStore) => 
  state.queue.filter(v => v.status === 'queued' || v.status === 'pending')

export const selectProcessingVideos = (state: VideoStore) => 
  state.queue.filter(v => v.status === 'processing')

export const selectCompletedVideos = (state: VideoStore) => 
  state.queue.filter(v => v.status === 'completed')

export const selectFailedVideos = (state: VideoStore) => 
  state.queue.filter(v => v.status === 'failed')

// Re-export for backward compatibility
export { type QueueVideo as VideoItem }
export { type EvaluationStatus as VideoStatus } from '@/types/api'
