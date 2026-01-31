/**
 * usePipelineProcessing Hook - Handles video processing operations
 *
 * Manages:
 * - Single and batch video processing
 * - Video retry and reprocessing
 * - Polling for evaluation status
 * - Stage output fetching with caching
 */
import { useCallback, useRef } from 'react'
import { useVideoStoreActions, QueueVideo } from '@/store/videoStore'
import { usePipelineStore } from '@/store/pipelineStore'
import { evaluationApi, stageApi } from '@/api/endpoints'
import { useSSEConnection, addItemIdMapping } from './useSSEConnection'
import toast from 'react-hot-toast'

interface UsePipelineProcessingReturn {
  processSingleVideo: (videoId: string, file: File) => Promise<void>
  processAllVideos: (videos: QueueVideo[], criteriaId?: string) => Promise<void>
  retryVideo: (videoId: string) => Promise<void>
  reprocessVideo: (evaluationId: string, videoId: string) => Promise<void>
  fetchStageOutput: (evaluationId: string, itemId: string, stageId: string, videoId: string) => Promise<any>
  pollEvaluationStatus: (evaluationId: string, videoId: string) => void
}

const CACHE_DURATION = 24 * 60 * 60 * 1000 // 24 hours

export const usePipelineProcessing = (): UsePipelineProcessingReturn => {
  const { updateVideo, getVideoById } = useVideoStoreActions()
  const selectedPreset = usePipelineStore(state => state.selectedPreset)
  const availableStages = usePipelineStore(state => state.availableStages)
  const setStageOutput = usePipelineStore(state => state.setStageOutput)
  const setStageLoading = usePipelineStore(state => state.setStageLoading)
  const clearStageOutput = usePipelineStore(state => state.clearStageOutput)
  const setSelectedStage = usePipelineStore(state => state.setSelectedStage)
  const clearCompletedStages = usePipelineStore(state => state.clearCompletedStages)

  const { connectSSE } = useSSEConnection()
  const pollingTimersRef = useRef<Map<string, NodeJS.Timeout>>(new Map())

  // Cache helpers
  const getCachedStageOutput = useCallback((key: string): any => {
    try {
      const cached = localStorage.getItem(`stage_output_${key}`)
      if (!cached) return null

      const { data, timestamp } = JSON.parse(cached)
      if (Date.now() - timestamp > CACHE_DURATION) {
        localStorage.removeItem(`stage_output_${key}`)
        return null
      }
      return data
    } catch {
      return null
    }
  }, [])

  const setCachedStageOutput = useCallback((key: string, data: any) => {
    try {
      localStorage.setItem(`stage_output_${key}`, JSON.stringify({
        data,
        timestamp: Date.now()
      }))
    } catch (err) {
      console.warn('Failed to cache stage output:', err)
    }
  }, [])

  const clearCachedStageOutputs = useCallback((keys: string[]) => {
    keys.forEach(key => {
      try {
        localStorage.removeItem(`stage_output_${key}`)
      } catch (err) {
        console.warn('Failed to clear cache:', err)
      }
    })
  }, [])

  // Fetch stage output with caching
  const fetchStageOutput = useCallback(async (
    evaluationId: string,
    itemId: string,
    stageId: string,
    videoId: string
  ): Promise<any> => {
    const cacheKey = `${evaluationId}_${itemId}_${stageId}`

    // Check cache first
    const cached = getCachedStageOutput(cacheKey)
    if (cached) {
      setStageOutput(`${videoId}-${stageId}`, { data: cached, timestamp: Date.now() })
      return cached
    }

    // Fetch from backend
    setStageLoading(true)
    try {
      const data = await stageApi.getStageOutput(evaluationId, stageId, itemId)
      setCachedStageOutput(cacheKey, data)
      setStageOutput(`${videoId}-${stageId}`, { data, timestamp: Date.now() })
      return data
    } catch (err: any) {
      console.error('Error fetching stage output:', err)
      throw err
    } finally {
      setStageLoading(false)
    }
  }, [getCachedStageOutput, setCachedStageOutput, setStageOutput, setStageLoading])

  // Poll evaluation status
  const pollEvaluationStatus = useCallback((evaluationId: string, videoId: string) => {
    // Clear existing timer
    const existingTimer = pollingTimersRef.current.get(evaluationId)
    if (existingTimer) {
      clearInterval(existingTimer)
    }

    const timer = setInterval(async () => {
      try {
        const evaluation = await evaluationApi.get(evaluationId)

        if (evaluation.status === 'completed' || evaluation.status === 'failed') {
          clearInterval(timer)
          pollingTimersRef.current.delete(evaluationId)

          // Find result for this video's item
          const item = evaluation.items?.find((i: any) => {
            const video = getVideoById(videoId)
            return video && i.id === video.itemId
          })

          updateVideo(videoId, {
            status: evaluation.status,
            progress: 100,
            result: item?.result,
            verdict: item?.result?.verdict
          })
        }
      } catch (err) {
        console.error('Error polling evaluation:', err)
      }
    }, 2000)

    pollingTimersRef.current.set(evaluationId, timer)
  }, [updateVideo])

  // Process single video
  const processSingleVideo = useCallback(async (videoId: string, file: File) => {
    try {
      updateVideo(videoId, { status: 'processing', progress: 0 })

      const response = await evaluationApi.create({
        files: [file],
        criteriaId: selectedPreset || undefined,
        async: true
      })

      const evaluationId = response.id
      const itemId = response.items?.[0]?.id

      updateVideo(videoId, {
        evaluationId,
        itemId,
        status: 'processing'
      })

      // Map item_id to video for SSE
      if (itemId) {
        addItemIdMapping(itemId, videoId)
      }

      // Connect SSE and start polling
      connectSSE(evaluationId, videoId, availableStages)
      pollEvaluationStatus(evaluationId, videoId)

      toast.success('Processing started')
    } catch (err: any) {
      console.error('Error processing video:', err)
      updateVideo(videoId, {
        status: 'failed',
        error: err.response?.data?.detail || err.message
      })
      toast.error('Failed to process video')
    }
  }, [updateVideo, selectedPreset, connectSSE, pollEvaluationStatus, availableStages])

  // Process all queued videos
  const processAllVideos = useCallback(async (videos: QueueVideo[], criteriaId?: string) => {
    const files = videos.map(v => v.file).filter(Boolean) as File[]
    if (files.length === 0) {
      toast.error('No videos to process')
      return
    }

    try {
      // Update all to processing
      videos.forEach(v => {
        updateVideo(v.id, { status: 'processing', progress: 0 })
      })

      const response = await evaluationApi.create({
        files,
        criteriaId: criteriaId || selectedPreset || undefined,
        async: true
      })

      const evaluationId = response.id

      // Map items to videos
      if (response.items) {
        response.items.forEach((item, idx) => {
          const videoId = videos[idx]?.id
          if (videoId) {
            updateVideo(videoId, {
              evaluationId,
              itemId: item.id,
              status: 'processing'
            })
            addItemIdMapping(item.id, videoId)
          }
        })
      }

      // Connect SSE for batch
      connectSSE(evaluationId, videos[0].id, availableStages)
      videos.forEach(v => pollEvaluationStatus(evaluationId, v.id))

      toast.success(`Processing ${files.length} video${files.length > 1 ? 's' : ''}`)
    } catch (err: any) {
      console.error('Error processing videos:', err)
      videos.forEach(v => {
        updateVideo(v.id, {
          status: 'failed',
          error: err.response?.data?.detail || err.message
        })
      })
      toast.error('Failed to process videos')
    }
  }, [updateVideo, selectedPreset, connectSSE, pollEvaluationStatus, availableStages])

  // Retry failed video
  const retryVideo = useCallback(async (videoId: string) => {
    const video = getVideoById(videoId)
    if (!video) return

    let file = video.file

    // If no local file, try to fetch from backend
    if (!file && video.evaluationId && video.itemId) {
      try {
        // Fetch the uploaded video as artifact
        const blob = await evaluationApi.getArtifact(video.evaluationId, 'uploaded_video', video.itemId)
        file = new File([blob], video.filename, { type: blob.type || 'video/mp4' })
      } catch (err) {
        console.error('Failed to fetch video from backend:', err)
        toast.error('Cannot retry: video file not found')
        return
      }
    }

    if (!file) {
      toast.error('Cannot retry: no file available')
      return
    }

    updateVideo(videoId, { status: 'queued', error: undefined })
    await processSingleVideo(videoId, file)
  }, [getVideoById, updateVideo, processSingleVideo])

  // Reprocess video with new settings
  const reprocessVideo = useCallback(async (evaluationId: string, videoId: string) => {
    try {
      const video = getVideoById(videoId)
      if (!video || !video.itemId) {
        toast.error('Cannot reprocess: video not found')
        return
      }

      // Clear cached outputs
      const itemId = video.itemId
      const cacheKeys = [
        `${evaluationId}_${itemId}_yolo26_vision`,
        `${evaluationId}_${itemId}_violence_detection`,
        `${evaluationId}_${itemId}_audio_transcription`,
        `${evaluationId}_${itemId}_text_moderation`,
        `${evaluationId}_${itemId}_policy_fusion`,
        `${evaluationId}_${itemId}_report_generation`,
      ]
      clearCachedStageOutputs(cacheKeys)
      clearStageOutput(videoId)

      // Reset UI state
      setSelectedStage(null)
      clearCompletedStages()

      // Update video state
      updateVideo(videoId, {
        status: 'processing',
        progress: 0,
        currentStage: 'ingest_video'
      })

      // Call reprocess API
      const response = await evaluationApi.reprocess(evaluationId, true)

      // Reconnect SSE and polling
      connectSSE(evaluationId, videoId, availableStages)
      pollEvaluationStatus(evaluationId, videoId)

      toast.success('Reprocessing started')
    } catch (err: any) {
      console.error('Error reprocessing video:', err)
      updateVideo(videoId, { status: 'failed', error: err.message })
      toast.error('Failed to reprocess video')
    }
  }, [
    getVideoById,
    updateVideo,
    clearStageOutput,
    setSelectedStage,
    clearCompletedStages,
    clearCachedStageOutputs,
    connectSSE,
    pollEvaluationStatus,
    availableStages
  ])

  return {
    processSingleVideo,
    processAllVideos,
    retryVideo,
    reprocessVideo,
    fetchStageOutput,
    pollEvaluationStatus,
  }
}
