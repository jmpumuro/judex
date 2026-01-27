import type { VideoResult, VideoStatus } from './common'

export interface QueueVideo {
  id: string
  filename: string
  size: number
  status: VideoStatus
  progress: number
  current_stage?: string
  file?: File
  result?: VideoResult
  uploaded_at: number
}

export interface BatchUploadResponse {
  batch_id: string
  videos: Array<{
    video_id: string
    filename: string
    batch_video_id: string
  }>
}

export interface BatchStatusResponse {
  batch_id: string
  status: string
  total_videos: number
  completed: number
  failed: number
  videos: Record<string, {
    video_id: string
    filename: string
    status: VideoStatus
    progress: number
  }>
}
