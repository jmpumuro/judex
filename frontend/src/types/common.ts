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

// Generic criterion score - works with any criteria
export interface CriterionScore {
  score: number
  status: 'ok' | 'caution' | 'violation'
}

// Dynamic criteria scores - keyed by criterion ID
export type CriteriaScores = Record<string, CriterionScore>

// Legacy SafetyScores for backward compatibility
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
  video_metadata?: VideoMetadata
  object_detections?: {
    total_frames_analyzed: number
    detections: any[]
  }
  violence_segments?: Array<{
    start_time: number
    end_time: number
    score: number
  }>
  audio_transcript?: Array<{
    timestamp: number
    text: string
  }>
  ocr_results?: Array<{
    timestamp: number
    text: string
  }>
  moderation_flags?: any[]
  // Generic detector outputs
  [key: string]: any
}

// Explanation from FusionEngine
export interface CriterionExplanation {
  score: number
  verdict: string
  threshold?: string | null
  evidence_count: number
  detectors_used: string[]
  description?: string | null
}

export interface VerdictExplanation {
  verdict: string
  summary: string
  criterion_explanations: Record<string, CriterionExplanation>
  key_factors: Array<{
    criterion: string
    score: number
    evidence_count: number
  }>
}

export interface ModelVersionInfo {
  detector_id: string
  model_version?: string | null
  model_id?: string | null
}

export interface VideoResult {
  video_id?: string
  filename?: string
  verdict: Verdict
  confidence: number
  criteria: CriteriaScores
  // Legacy scores for backward compatibility
  scores?: SafetyScores
  processing_time_sec?: number
  violations?: Array<{
    criterion: string
    severity: string
    score: number
    timestamp_ranges?: number[][]
    evidence_refs?: string[]
  }>
  evidence: Evidence
  report?: string
  summary?: string
  stages?: PipelineStage[]
  model_versions?: ModelVersionInfo[]
  spec_id?: string
  explanation?: VerdictExplanation
  metadata?: {
    video_id?: string
    duration?: number
    width?: number
    height?: number
    fps?: number
    has_audio?: boolean
    frames_analyzed?: number
    segments_analyzed?: number
    detectors_run?: string[]
  }
  timings?: {
    total_seconds?: number
    operations?: Record<string, number>
  }
}

// Evaluation Spec types (for UI)
export interface CriterionSpec {
  id: string
  label: string
  description?: string
  enabled: boolean
  severity_weight: number
  thresholds: {
    safe_below: number
    caution_below: number
    unsafe_above: number
  }
}

export interface DetectorSpec {
  id: string
  type: string
  enabled: boolean
  priority: number
}

export interface EvaluationPreset {
  id: string
  name: string
  spec_name?: string
  schema_version?: string
  criteria?: CriterionSpec[]
  detectors?: DetectorSpec[]
  fusion?: {
    strategy: string
    aggregation: string
    require_confirmation: boolean
  }
}

export interface PolicyConfig {
  thresholds: {
    unsafe: Record<string, number>
    caution: Record<string, number>
  }
}
