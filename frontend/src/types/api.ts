/**
 * API Types - Single source of truth for frontend data structures.
 * 
 * These types mirror the backend DTOs (app/api/schemas.py) exactly.
 * Any changes to the backend should be reflected here.
 */

// ============================================================================
// Enums
// ============================================================================

export type EvaluationStatus = 
  | 'pending'
  | 'queued'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'cancelled'

export type Verdict = 'SAFE' | 'CAUTION' | 'UNSAFE' | 'NEEDS_REVIEW'

export type Severity = 'low' | 'medium' | 'high' | 'critical'

// ============================================================================
// Criteria Types
// ============================================================================

export interface CriterionSummary {
  id: string
  label: string
  severity: Severity
  enabled: boolean
}

export interface CriteriaSummary {
  id: string
  name: string
  description?: string
  criteria_count: number
  is_preset: boolean
}

export interface CriteriaDetail extends CriteriaSummary {
  version: string
  criteria: Record<string, CriterionSummary>
  config_yaml?: string
}

// ============================================================================
// Evaluation Result Types
// ============================================================================

export interface Violation {
  criterion: string
  label: string
  severity: Severity
  score: number
  evidence?: Record<string, unknown>
}

export interface CriterionScore {
  score: number
  verdict: Verdict
  label: string
  severity: Severity
}

export interface EvaluationResult {
  item_id: string
  verdict: Verdict
  confidence: number
  criteria_scores: Record<string, CriterionScore>
  violations: Violation[]
  report?: string
  transcript?: Record<string, unknown>
  processing_time_sec?: number
  
  // Legacy/alternative property names for backward compatibility
  criteria?: Record<string, CriterionScore | number>
  evidence?: EvaluationEvidence
  metadata?: {
    video_id?: string
    duration?: number
    fps?: number
    resolution?: { width: number; height: number }
    detectors_run?: string[]
    [key: string]: unknown
  }
  explanation?: {
    summary?: string
    [key: string]: unknown
  } | string
  spec_id?: string
  summary?: string
}

export interface EvaluationEvidence {
  // Standard evidence arrays
  vision?: Array<{ label: string; confidence: number; timestamp: number; bbox?: number[] }>
  violence?: Array<{ segment: number; score: number; label: string }>
  ocr?: Array<{ text: string; timestamp: number }>
  moderation?: Array<{ text: string; label: string; score: number }>
  transcript?: Array<{ text: string; start: number; end: number }>
  
  // Alternative property names
  violence_segments?: Array<{ segment: number; score: number; label: string }>
  object_detections?: Array<{ label: string; confidence: number; timestamp: number; bbox?: number[] }>
  audio_transcript?: Array<{ text: string; start: number; end: number }>
  ocr_results?: Array<{ text: string; timestamp: number }>
  
  // Allow additional properties
  [key: string]: unknown
}

// ============================================================================
// Evaluation Item Types
// ============================================================================

export interface EvaluationItem {
  id: string
  evaluation_id: string
  filename: string
  source_type: string
  status: EvaluationStatus
  progress: number
  current_stage?: string
  error_message?: string
  created_at: string  // ISO datetime
  completed_at?: string
  
  // Artifacts
  labeled_video_path?: string
  uploaded_video_path?: string
  thumbnail_path?: string
  
  // Result (if completed)
  result?: EvaluationResult
}

// ============================================================================
// Evaluation Types
// ============================================================================

export interface EvaluationSummary {
  id: string
  status: EvaluationStatus
  progress: number
  overall_verdict?: Verdict
  items_total: number
  items_completed: number
  items_failed: number
  criteria_id?: string
  created_at: string
  completed_at?: string
}

export interface Evaluation extends EvaluationSummary {
  error_message?: string
  started_at?: string
  items: EvaluationItem[]
}

// ============================================================================
// API Request/Response Types
// ============================================================================

export interface EvaluationCreateRequest {
  criteria_id?: string
  criteria_yaml?: string
  criteria_json?: string
  is_async?: boolean
  urls?: string[]
}

export interface EvaluationCreateResponse {
  id: string
  status: EvaluationStatus
  items_total: number
  criteria_id?: string
  is_async: boolean
}

export interface EvaluationListResponse {
  evaluations: EvaluationSummary[]
  total: number
}

export interface ProgressEvent {
  stage: string
  message: string
  progress: number
  item_id?: string
  evaluation_complete?: boolean
}

export interface StageOutput {
  evaluation_id: string
  item_id?: string
  stage: string
  output: Record<string, unknown>
}

export interface Artifact {
  url: string
  artifact_type: string
  item_id: string
  expires_at?: string
}

export interface ProcessedFrame {
  id: string
  index: number
  timestamp: number
  thumbnail_url: string  // Small thumbnail for filmstrip
  full_url?: string      // Full-size frame (optional, available when thumbnails=true)
}

export interface FramesResponse {
  evaluation_id: string
  item_id: string
  frames: ProcessedFrame[]
  total: number
  // Pagination fields
  page: number
  page_size: number
  total_pages: number
}

// ============================================================================
// Health/Status Types
// ============================================================================

export interface Health {
  status: string
  version: string
  models_loaded: boolean
}

// ============================================================================
// Legacy Type Aliases (for backward compatibility during migration)
// ============================================================================

/** @deprecated Use EvaluationItem instead */
export type VideoItem = EvaluationItem

/** @deprecated Use EvaluationResult instead */
export type VideoResult = EvaluationResult

/** @deprecated Use EvaluationStatus instead */
export type VideoStatus = EvaluationStatus
