import apiClient from '../client'
import { BatchUploadResponse, BatchStatusResponse, VideoResult, PolicyConfig } from '@/types'

export const videoApi = {
  // Upload batch of videos
  uploadBatch: async (files: File[], policy?: PolicyConfig): Promise<BatchUploadResponse> => {
    const formData = new FormData()
    files.forEach(file => formData.append('files', file))
    if (policy) formData.append('policy', JSON.stringify(policy))

    const { data } = await apiClient.post('/evaluate/batch', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data
  },

  // Get batch status
  getBatchStatus: async (batchId: string): Promise<BatchStatusResponse> => {
    const { data } = await apiClient.get(`/evaluate/batch/${batchId}`)
    return data
  },

  // Get all results
  getResults: async (): Promise<VideoResult[]> => {
    const { data } = await apiClient.get('/results')
    return data
  },

  // Save results
  saveResults: async (results: VideoResult[]): Promise<void> => {
    await apiClient.post('/results', results)
  },

  // Delete result
  deleteResult: async (videoId: string): Promise<void> => {
    await apiClient.delete(`/results/${videoId}`)
  },

  // Clear all results
  clearAllResults: async (): Promise<void> => {
    await apiClient.delete('/results')
  },

  // Get labeled video
  getLabeledVideo: async (videoId: string): Promise<Blob> => {
    const { data } = await apiClient.get(`/videos/${videoId}/labeled`, {
      responseType: 'blob',
    })
    return data
  },

  // Get uploaded (original) video
  getUploadedVideo: async (videoId: string): Promise<Blob> => {
    const { data } = await apiClient.get(`/videos/${videoId}/uploaded`, {
      responseType: 'blob',
    })
    return data
  },

  // Import from URL
  importFromUrl: async (urls: string[]): Promise<any> => {
    const { data } = await apiClient.post('/import/urls', { urls })
    return data
  },

  // Get checkpoints
  getCheckpoints: async (): Promise<any[]> => {
    try {
      const { data } = await apiClient.get('/checkpoints')
      return data
    } catch (error) {
      return []
    }
  },

  // Delete checkpoint
  deleteCheckpoint: async (videoId: string): Promise<void> => {
    await apiClient.delete(`/checkpoints/${videoId}`)
  },
}
