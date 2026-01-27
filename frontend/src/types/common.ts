export type Verdict = 'SAFE' | 'CAUTION' | 'UNSAFE' | 'NEEDS_REVIEW'
export type VideoStatus = 'pending' | 'processing' | 'completed' | 'error'
export type StageStatus = 'pending' | 'in_progress' | 'completed' | 'error'

export interface VideoMetadata {
  duration: number
  fps: number
  width: number
  height: number
  has_audio: boolean
}

export interface SafetyScores {
  violence: number
  sexual: number
  hate: number
  drugs: number
  profanity: number
}

export interface PipelineStage {
  id: string
  name: string
  progress: number
  status: StageStatus
  message?: string
  output?: any
}

export interface Evidence {
  video_metadata: VideoMetadata
  object_detections: {
    total_frames_analyzed: number
    detections: any[]
  }
  violence_segments: Array<{
    start_time: number
    end_time: number
    score: number
  }>
  audio_transcript: Array<{
    timestamp: number
    text: string
  }>
  ocr_results: Array<{
    timestamp: number
    text: string
  }>
  moderation_flags: any[]
}

export interface VideoResult {
  video_id: string
  filename: string
  verdict: Verdict
  confidence: number
  scores: SafetyScores
  processing_time_sec: number
  evidence: Evidence
  summary: string
  stages?: PipelineStage[]
  model_versions?: Record<string, string>
}

export interface PolicyConfig {
  thresholds: {
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
}
