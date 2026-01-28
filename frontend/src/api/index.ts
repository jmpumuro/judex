/**
 * API exports - Single entry point for all API functions.
 * 
 * Use:
 *   import { evaluations, criteria } from '@/api'
 *   import api from '@/api'
 */

export { default, evaluations, criteria, health, api, API_BASE } from './client'

// Re-export types for convenience
export type {
  Evaluation,
  EvaluationSummary,
  EvaluationItem,
  EvaluationResult,
  CriteriaSummary,
  CriteriaDetail,
  ProgressEvent,
} from '@/types/api'
