/**
 * useSSEConnection Hook - Manages Server-Sent Events for real-time pipeline updates
 *
 * Handles:
 * - SSE connection lifecycle
 * - Event parsing and video updates
 * - Retry logic with exponential backoff
 * - Progress calculation based on stage position
 */
import { useCallback, useRef } from 'react'
import { useVideoStoreActions } from '@/store/videoStore'
import { usePipelineStore } from '@/store/pipelineStore'
import { createSSEConnection } from '@/api/endpoints'
import { PipelineStage } from '@/store/pipelineStore'

interface UseSSEConnectionReturn {
  connectSSE: (evaluationId: string, queueVideoId: string, stages: PipelineStage[], retryCount?: number) => void
  disconnectSSE: (key: string) => void
  disconnectAllSSE: () => void
}

// Map evaluation_id -> queue video id for batch processing
const evaluationToVideoMap = new Map<string, string>()

// Map item_id -> queue video id for batch item tracking
const itemIdToVideoMap = new Map<string, string>()

// Batch video updates to prevent flickering
const pendingUpdates = new Map<string, any>()
let updateTimer: NodeJS.Timeout | null = null

const DEFAULT_STAGE_PROGRESS_MAP: Record<string, number> = {
  'ingest_video': 5, 'segment_video': 10, 'yolo26_vision': 18,
  'yoloworld_vision': 24, 'window_mining': 30, 'violence_detection': 38,
  'videomae_violence': 46, 'pose_heuristics': 52, 'nsfw_detection': 58,
  'audio_transcription': 65, 'ocr_extraction': 72, 'text_moderation': 80,
  'policy_fusion': 92, 'report_generation': 100
}

const getStageProgress = (stageId: string, allStages: PipelineStage[]): number => {
  if (DEFAULT_STAGE_PROGRESS_MAP[stageId]) return DEFAULT_STAGE_PROGRESS_MAP[stageId]
  const idx = allStages.findIndex(s => s.id === stageId)
  if (idx < 0) return 50
  return Math.round((idx / allStages.length) * 100)
}

export const useSSEConnection = (): UseSSEConnectionReturn => {
  const { updateVideo } = useVideoStoreActions()
  const addSSEConnection = usePipelineStore(state => state.addSSEConnection)
  const removeSSEConnection = usePipelineStore(state => state.removeSSEConnection)
  const closeAllSSEConnections = usePipelineStore(state => state.closeAllSSEConnections)

  const batchedUpdateVideo = useCallback((videoId: string, updates: any) => {
    pendingUpdates.set(videoId, {
      ...(pendingUpdates.get(videoId) || {}),
      ...updates
    })

    if (updateTimer) clearTimeout(updateTimer)

    updateTimer = setTimeout(() => {
      pendingUpdates.forEach((updates, id) => {
        updateVideo(id, updates)
      })
      pendingUpdates.clear()
      updateTimer = null
    }, 50)
  }, [updateVideo])

  const connectSSE = useCallback((
    evaluationId: string,
    queueVideoId: string,
    stages: PipelineStage[],
    retryCount = 0
  ) => {
    const key = `sse-${evaluationId}`

    // Store mapping
    evaluationToVideoMap.set(evaluationId, queueVideoId)

    // Create SSE connection
    const sse = createSSEConnection(evaluationId)

    sse.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)

        // Find target video
        let targetVideoId = queueVideoId
        if (data.item_id && itemIdToVideoMap.has(data.item_id)) {
          targetVideoId = itemIdToVideoMap.get(data.item_id)!
        }

        // Calculate progress based on stage
        let progress = data.progress || 0
        if (data.current_stage) {
          const stageId = data.current_stage
          const baseProgress = getStageProgress(stageId, stages)

          // Find next stage for range calculation
          const currentIdx = stages.findIndex(s => s.id === stageId || s.backendId === stageId)
          if (currentIdx >= 0 && currentIdx < stages.length - 1) {
            const nextStageProgress = getStageProgress(stages[currentIdx + 1].id, stages)
            const range = nextStageProgress - baseProgress

            // Normalize stage progress if > 1
            const stageProgress = data.progress > 1 ? data.progress / 100 : data.progress
            const normalizedProgress = Math.min(Math.max(stageProgress, 0), 1)

            progress = Math.round(baseProgress + (range * normalizedProgress))
          } else {
            progress = baseProgress
          }
        }

        // Prepare update
        const update: any = {
          progress: Math.min(progress, 100),
        }

        if (data.current_stage) {
          update.currentStage = data.current_stage
        }

        if (data.status) {
          update.status = data.status
        }

        if (data.status_message) {
          update.statusMessage = data.status_message
        }

        if (data.result) {
          update.result = data.result
          update.verdict = data.result.verdict
        }

        // Batch update
        batchedUpdateVideo(targetVideoId, update)

        // Close connection if complete
        if (data.evaluation_complete || data.status === 'completed' || data.status === 'failed') {
          removeSSEConnection(key)
          evaluationToVideoMap.delete(evaluationId)
          if (data.item_id) {
            itemIdToVideoMap.delete(data.item_id)
          }
        }
      } catch (err) {
        console.error('Error parsing SSE event:', err)
      }
    }

    sse.onerror = () => {
      removeSSEConnection(key)

      // Retry with exponential backoff
      if (retryCount < 3) {
        const backoffMs = 2000 * (retryCount + 1)
        setTimeout(() => {
          connectSSE(evaluationId, queueVideoId, stages, retryCount + 1)
        }, backoffMs)
      }
    }

    // Store connection
    addSSEConnection(key, sse)
  }, [addSSEConnection, removeSSEConnection, batchedUpdateVideo])

  const disconnectSSE = useCallback((key: string) => {
    removeSSEConnection(key)
  }, [removeSSEConnection])

  const disconnectAllSSE = useCallback(() => {
    closeAllSSEConnections()
    evaluationToVideoMap.clear()
    itemIdToVideoMap.clear()
  }, [closeAllSSEConnections])

  return {
    connectSSE,
    disconnectSSE,
    disconnectAllSSE,
  }
}

// Export mapping functions for external use
export const addItemIdMapping = (itemId: string, videoId: string) => {
  itemIdToVideoMap.set(itemId, videoId)
}

export const clearItemIdMapping = (itemId: string) => {
  itemIdToVideoMap.delete(itemId)
}
