import { FC, useEffect } from 'react'
import { QueueVideo, PipelineStage, StageStatus } from '@/types'
import { useSSE } from '@/hooks/useSSE'
import { useVideoStore } from '@/store/videoStore'
import StageProgress from './StageProgress'
import ResultsPanel from './ResultsPanel'
import Spinner from '../common/Spinner'

interface PipelineViewProps {
  video: QueueVideo
}

const stageDefinitions = [
  { id: 'ingest_video', name: 'Ingest' },
  { id: 'segment_video', name: 'Segment' },
  { id: 'yolo26_vision', name: 'YOLO26' },
  { id: 'yoloworld_vision', name: 'YOLO-World' },
  { id: 'violence_detection', name: 'Violence' },
  { id: 'audio_transcription', name: 'Audio' },
  { id: 'ocr_extraction', name: 'OCR' },
  { id: 'text_moderation', name: 'Moderate' },
  { id: 'policy_fusion', name: 'Policy' },
  { id: 'report_generation', name: 'Report' },
  { id: 'finalize', name: 'Finalize' },
]

const PipelineView: FC<PipelineViewProps> = ({ video }) => {
  const { data: sseData } = useSSE(video.status === 'processing' ? video.id : null)
  const updateVideo = useVideoStore(state => state.updateVideo)

  // Handle SSE updates
  useEffect(() => {
    if (!sseData) return

    updateVideo(video.id, { progress: sseData.progress, currentStage: sseData.stage })

    // Check for completion
    if (sseData.stage === 'complete' && sseData.stage_output) {
      updateVideo(video.id, { result: sseData.stage_output, status: 'completed' })
    }
  }, [sseData, video.id, updateVideo])

  // Convert video progress to stage states
  const stages: PipelineStage[] = stageDefinitions.map((stageDef) => {
    let status: StageStatus = 'pending'
    let progress = 0

    if (video.current_stage === stageDef.id) {
      status = 'in_progress'
      progress = video.progress
    } else if (video.result || video.status === 'completed') {
      status = 'completed'
      progress = 100
    } else if (video.status === 'error') {
      status = 'error'
      progress = 0
    } else {
      // Check if this stage is before current stage
      const currentIndex = stageDefinitions.findIndex(s => s.id === video.current_stage)
      const thisIndex = stageDefinitions.findIndex(s => s.id === stageDef.id)
      if (thisIndex < currentIndex) {
        status = 'completed'
        progress = 100
      }
    }

    return {
      id: stageDef.id,
      name: stageDef.name,
      status,
      progress,
      message: sseData?.stage === stageDef.id ? sseData.message : undefined,
    }
  })

  return (
    <div className="h-full flex flex-col">
      {/* Pipeline Stages */}
      <div className="card p-4 mb-4">
        <h3 className="text-sm font-semibold text-gray-400 uppercase mb-4">
          Processing Pipeline
        </h3>
        <StageProgress stages={stages} />
      </div>

      {/* Results or Processing State */}
      {video.status === 'completed' && video.result ? (
        <ResultsPanel result={video.result} videoId={video.id} />
      ) : video.status === 'processing' ? (
        <div className="card p-8 text-center">
          <Spinner size={48} />
          <p className="text-white mt-4 font-medium">Processing video...</p>
          {video.current_stage && (
            <p className="text-gray-400 text-sm mt-2">
              {video.current_stage.replace(/_/g, ' ')} - {video.progress}%
            </p>
          )}
        </div>
      ) : video.status === 'error' ? (
        <div className="card p-8 text-center">
          <p className="text-danger text-lg font-medium">Processing Failed</p>
          <p className="text-gray-400 text-sm mt-2">
            An error occurred while processing this video.
          </p>
        </div>
      ) : (
        <div className="card p-8 text-center">
          <p className="text-gray-400">
            Video is ready to be processed. Click the play icon to start.
          </p>
        </div>
      )}
    </div>
  )
}

export default PipelineView
