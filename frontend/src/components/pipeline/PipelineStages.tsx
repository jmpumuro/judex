/**
 * PipelineStages - Industry standard component for pipeline stage visualization.
 * 
 * Key optimizations:
 * 1. Uses granular Zustand selectors to only subscribe to stage-relevant data
 * 2. Memoized individual stage nodes with stable references
 * 3. CSS-based transitions instead of React re-renders for visual updates
 * 4. Separated from parent component to isolate re-renders
 */
import { memo, useCallback, useMemo } from 'react'
import { Check, Loader2, AlertCircle, X } from 'lucide-react'
import { useSelectedVideoStageInfo, VideoStageInfo } from '@/store/videoStore'

/**
 * Stage definition interface.
 * Re-exported from PipelineStages component for use by parent components.
 */
export interface PipelineStage {
  id: string
  backendId: string
  name: string
  number: string
  isExternal?: boolean
  displayColor?: string
  enabled?: boolean
  hasOverrides?: boolean  // Indicates stage has custom config overrides
}

interface PipelineStagesProps {
  stages: PipelineStage[]
  selectedStage: string | null
  onStageClick: (stageId: string) => void
}

// Individual stage node - memoized with custom comparison
interface StageNodeProps {
  stage: PipelineStage
  status: 'pending' | 'active' | 'completed' | 'error'
  isSelected: boolean
  isLast: boolean
  onClick: () => void
  clickable: boolean
}

const StageNode = memo<StageNodeProps>(({ 
  stage, 
  status, 
  isSelected, 
  isLast, 
  onClick, 
  clickable 
}) => {
  const isExternal = stage.isExternal
  const isDisabled = stage.enabled === false
  
  // Disabled stages
  if (isDisabled) {
    return (
      <div className="flex items-center gap-2 opacity-30">
        <div className="flex flex-col items-center">
          <div className="w-9 h-9 rounded-full border border-dashed border-gray-700 flex items-center justify-center text-[10px] text-gray-600">
            <X size={12} />
          </div>
          <span className="text-[9px] mt-1 text-gray-600 line-through">
            {stage.name}
          </span>
        </div>
        {!isLast && <div className="w-4 h-px bg-gray-800 opacity-50" />}
      </div>
    )
  }
  
  // Compute styles based on status - using CSS variables for smooth transitions
  const nodeStyles = useMemo(() => {
    if (isSelected) {
      return isExternal 
        ? 'border-purple-400 bg-purple-400 text-black ring-2 ring-purple-400/50'
        : 'border-blue-400 bg-blue-400 text-black ring-2 ring-blue-400/50'
    }
    if (status === 'completed') {
      return isExternal 
        ? 'border-purple-400 bg-purple-400 text-black'
        : 'border-white bg-white text-black'
    }
    if (status === 'active') {
      return isExternal 
        ? 'border-purple-400 bg-purple-400 text-black'
        : 'border-white bg-white text-black'
    }
    if (status === 'error') {
      return 'border-red-500 text-red-400'
    }
    return isExternal 
      ? 'border-purple-700 text-purple-400'
      : 'border-gray-700 text-gray-600'
  }, [isSelected, status, isExternal])
  
  const textStyles = useMemo(() => {
    if (isSelected) return isExternal ? 'text-purple-400' : 'text-blue-400'
    if (status === 'completed') return isExternal ? 'text-purple-400' : 'text-white'
    return isExternal ? 'text-purple-400' : 'text-gray-600'
  }, [isSelected, status, isExternal])
  
  const connectorColor = useMemo(() => {
    if (status !== 'completed') return 'bg-gray-800'
    return isExternal ? 'bg-purple-400' : 'bg-white'
  }, [status, isExternal])
  
  // Render icon based on status
  const icon = useMemo(() => {
    if (status === 'completed') return <Check size={14} />
    if (status === 'active') return <Loader2 size={14} className="animate-spin" />
    if (status === 'error') return <AlertCircle size={14} />
    return stage.number
  }, [status, stage.number])
  
  return (
    <div className="flex items-center gap-2">
      <button 
        onClick={onClick} 
        disabled={!clickable} 
        className="flex flex-col items-center group relative"
      >
        {/* Config overrides indicator badge */}
        {stage.hasOverrides && (
          <div 
            className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 bg-yellow-500 rounded-full border border-gray-950"
            title="Stage has custom settings"
          />
        )}
        {/* Use CSS transition for smooth visual updates */}
        <div 
          className={`w-9 h-9 rounded-full border-2 flex items-center justify-center text-xs transition-all duration-200 ${nodeStyles} ${clickable ? 'cursor-pointer hover:opacity-80' : 'cursor-default'}`}
        >
          {icon}
        </div>
        <span className={`text-[9px] mt-1 transition-colors duration-200 ${textStyles}`}>
          {stage.name}
          {isExternal && <span className="ml-0.5 opacity-50">●</span>}
        </span>
      </button>
      {!isLast && <div className={`w-4 h-px transition-colors duration-200 ${connectorColor}`} />}
    </div>
  )
}, (prevProps, nextProps) => {
  // Custom comparison - only re-render if these specific values change
  return (
    prevProps.stage.id === nextProps.stage.id &&
    prevProps.stage.enabled === nextProps.stage.enabled &&
    prevProps.stage.hasOverrides === nextProps.stage.hasOverrides &&
    prevProps.status === nextProps.status &&
    prevProps.isSelected === nextProps.isSelected &&
    prevProps.isLast === nextProps.isLast &&
    prevProps.clickable === nextProps.clickable
  )
})

StageNode.displayName = 'StageNode'

// Main pipeline stages component
const PipelineStages = memo<PipelineStagesProps>(({ 
  stages, 
  selectedStage, 
  onStageClick 
}) => {
  // Use granular selector - only subscribes to stage-relevant video data
  const videoStageInfo = useSelectedVideoStageInfo()
  
  // Compute stage status based on video progress
  const getStageStatus = useCallback((stageId: string): 'pending' | 'active' | 'completed' | 'error' => {
    if (!videoStageInfo) return 'pending'
    if (videoStageInfo.status === 'completed') return 'completed'
    if (videoStageInfo.status === 'failed') return 'error'
    
    const stageIndex = stages.findIndex(s => s.id === stageId)
    const currentIndex = stages.findIndex(s => 
      s.id === videoStageInfo.currentStage || s.backendId === videoStageInfo.currentStage
    )
    
    if (stageIndex < currentIndex) return 'completed'
    if (stageIndex === currentIndex) return 'active'
    return 'pending'
  }, [videoStageInfo, stages])
  
  // Determine if a stage is clickable (completed stages can be clicked to view output)
  const isStageClickable = useCallback((stageId: string): boolean => {
    if (!videoStageInfo) return false
    const status = getStageStatus(stageId)
    return status === 'completed' || status === 'active'
  }, [videoStageInfo, getStageStatus])
  
  // Memoize click handlers to prevent recreating on every render
  const handleStageClick = useCallback((stageId: string) => {
    if (isStageClickable(stageId)) {
      onStageClick(stageId)
    }
  }, [isStageClickable, onStageClick])
  
  if (!videoStageInfo) {
    return (
      <div className="p-2 border-b border-gray-800 bg-gray-900/30">
        <div className="text-xs text-gray-600 text-center">Select a video to view pipeline</div>
      </div>
    )
  }
  
  return (
    <div className="p-2 border-b border-gray-800 bg-gray-900/30 overflow-x-auto flex-shrink-0">
      <div className="flex items-center gap-1.5 min-w-max">
        {stages.map((stage, idx) => (
          <StageNode
            key={stage.id}
            stage={stage}
            status={getStageStatus(stage.id)}
            isSelected={selectedStage === stage.id}
            isLast={idx === stages.length - 1}
            onClick={() => handleStageClick(stage.id)}
            clickable={isStageClickable(stage.id)}
          />
        ))}
      </div>
    </div>
  )
})

PipelineStages.displayName = 'PipelineStages'

export default PipelineStages
