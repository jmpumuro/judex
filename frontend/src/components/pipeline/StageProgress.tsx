import { FC } from 'react'
import { Check, Loader2, Circle, AlertCircle } from 'lucide-react'
import { StageStatus } from '@/types'

interface StageProgressProps {
  stages: Array<{
    id: string
    name: string
    status: StageStatus
    progress: number
    message?: string
  }>
}

const stageIcons: Record<string, string> = {
  ingest_video: '📥',
  segment_video: '✂️',
  yolo26_vision: '👁️',
  yoloworld_vision: '🌍',
  violence_detection: '⚠️',
  audio_transcription: '🎤',
  ocr_extraction: '📝',
  text_moderation: '🔍',
  policy_fusion: '⚖️',
  report_generation: '📊',
  finalize: '✅',
}

const StageProgress: FC<StageProgressProps> = ({ stages }) => {
  const getStatusIcon = (status: StageStatus, progress: number) => {
    switch (status) {
      case 'completed':
        return <Check size={20} className="text-success" />
      case 'in_progress':
        return <Loader2 size={20} className="text-primary animate-spin" />
      case 'error':
        return <AlertCircle size={20} className="text-danger" />
      default:
        return <Circle size={20} className="text-gray-600" />
    }
  }

  return (
    <div className="flex items-center gap-4 overflow-x-auto pb-4">
      {stages.map((stage, index) => (
        <div key={stage.id} className="flex items-center gap-4">
          {/* Stage */}
          <div className="flex flex-col items-center min-w-[80px]">
            {/* Icon */}
            <div
              className={`relative w-14 h-14 rounded-full flex items-center justify-center border-2 transition-all ${
                stage.status === 'completed'
                  ? 'bg-success/20 border-success'
                  : stage.status === 'in_progress'
                  ? 'bg-primary/20 border-primary'
                  : stage.status === 'error'
                  ? 'bg-danger/20 border-danger'
                  : 'bg-dark-50 border-gray-700'
              }`}
            >
              <span className="text-2xl">{stageIcons[stage.id] || '⚙️'}</span>
              
              {/* Status indicator */}
              <div className="absolute -bottom-1 -right-1 bg-dark-100 rounded-full p-0.5">
                {getStatusIcon(stage.status, stage.progress)}
              </div>

              {/* Progress ring for in_progress */}
              {stage.status === 'in_progress' && (
                <svg className="absolute inset-0 w-full h-full -rotate-90">
                  <circle
                    cx="28"
                    cy="28"
                    r="26"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    className="text-primary opacity-30"
                  />
                  <circle
                    cx="28"
                    cy="28"
                    r="26"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    className="text-primary transition-all duration-300"
                    strokeDasharray={`${2 * Math.PI * 26}`}
                    strokeDashoffset={`${2 * Math.PI * 26 * (1 - stage.progress / 100)}`}
                    strokeLinecap="round"
                  />
                </svg>
              )}
            </div>

            {/* Stage Name */}
            <p className="text-xs font-medium text-gray-300 text-center mt-2 max-w-[80px]">
              {stage.name}
            </p>

            {/* Progress/Status */}
            {stage.status === 'in_progress' && (
              <p className="text-xs text-primary mt-1">{stage.progress}%</p>
            )}
          </div>

          {/* Connector Line */}
          {index < stages.length - 1 && (
            <div
              className={`w-8 h-0.5 ${
                stage.status === 'completed' ? 'bg-success' : 'bg-gray-700'
              }`}
            />
          )}
        </div>
      ))}
    </div>
  )
}

export default StageProgress
