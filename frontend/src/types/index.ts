/**
 * Type exports - Single source of truth.
 * 
 * Import all types from here, not from individual files.
 */

// API types (match backend DTOs)
export * from './api'

// UI-specific types
export type StageStatus = 'pending' | 'active' | 'completed' | 'failed' | 'in_progress' | 'error'

// Re-export store types
export type { QueueVideo, VideoSource, VideoStatus } from '@/store/videoStore'

// Pipeline stage definition
export interface PipelineStage {
  id: string
  name: string
  backendId: string
  description: string
}

// Re-export commonly used types for convenience
export type {
  Evaluation,
  EvaluationSummary,
  EvaluationItem,
  EvaluationResult,
  EvaluationStatus,
  Verdict,
  Severity,
  CriteriaSummary,
  CriteriaDetail,
  Violation,
  CriterionScore,
  ProgressEvent,
} from './api'
