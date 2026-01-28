/**
 * ProcessedFrames Component
 * 
 * Industry-standard filmstrip viewer for video keyframes:
 * - Uses small thumbnails for fast filmstrip display
 * - Full-size images on preview/expand
 * - Pagination for long videos
 * - Lazy loading for performance
 */
import { useState, useEffect, useCallback } from 'react'
import { evaluations } from '@/api/client'
import type { ProcessedFrame } from '@/types/api'
import { Loader2, ChevronLeft, ChevronRight, X } from 'lucide-react'

interface FramesResponse {
  evaluation_id: string
  item_id: string
  frames: ProcessedFrame[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

interface ProcessedFramesProps {
  evaluationId: string
  itemId: string
  onFrameClick?: (frame: ProcessedFrame, timestamp: number) => void
}

export function ProcessedFrames({ evaluationId, itemId, onFrameClick }: ProcessedFramesProps) {
  const [frames, setFrames] = useState<ProcessedFrame[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedFrame, setSelectedFrame] = useState<ProcessedFrame | null>(null)
  
  // Pagination state
  const [currentPage, setCurrentPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [totalFrames, setTotalFrames] = useState(0)
  const pageSize = 50

  const loadFrames = useCallback(async (page: number = 1) => {
    if (!evaluationId || !itemId) return
    
    setLoading(true)
    setError(null)
    
    try {
      const response = await evaluations.getFrames(evaluationId, itemId, page, pageSize) as FramesResponse
      setFrames(response.frames || [])
      setTotalPages(response.total_pages || 1)
      setTotalFrames(response.total || 0)
      setCurrentPage(response.page || 1)
    } catch (err) {
      console.error('Failed to load frames:', err)
      setError('Failed to load frames')
    } finally {
      setLoading(false)
    }
  }, [evaluationId, itemId, pageSize])

  useEffect(() => {
    loadFrames(1)
  }, [loadFrames])

  const handleFrameClick = (frame: ProcessedFrame) => {
    setSelectedFrame(frame)
    onFrameClick?.(frame, frame.timestamp)
  }

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= totalPages) {
      loadFrames(newPage)
    }
  }

  const formatTimestamp = (seconds: number): string => {
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return mins > 0 ? `${mins}:${secs.toString().padStart(2, '0')}` : `${secs}s`
  }

  // Get thumbnail URL (small image for filmstrip)
  const getThumbnailUrl = (frame: ProcessedFrame): string => {
    return frame.thumbnail_url || evaluations.getThumbnailUrl(evaluationId, frame.id, itemId)
  }

  // Get full-size frame URL (for preview)
  const getFullFrameUrl = (frame: ProcessedFrame): string => {
    return frame.full_url || evaluations.getFrameUrl(evaluationId, frame.id, itemId)
  }

  if (loading && frames.length === 0) {
    return (
      <div className="p-2 bg-gray-900/50">
        <div className="flex items-center gap-2 text-gray-500 text-xs">
          <Loader2 size={12} className="animate-spin" />
          <span>Loading frames...</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-2 bg-gray-900/50">
        <p className="text-red-500 text-xs">{error}</p>
      </div>
    )
  }

  if (totalFrames === 0) {
    return (
      <div className="p-2 bg-gray-900/50">
        <p className="text-gray-600 text-xs text-center">No frames available yet</p>
      </div>
    )
  }

  return (
    <div className="space-y-2 bg-gray-900/50 p-2 border-t border-gray-800">
      {/* Header with count and pagination */}
      <div className="flex items-center justify-between px-1">
        <span className="text-[9px] text-gray-500 uppercase tracking-wide">
          Keyframes ({totalFrames})
        </span>
        
        {/* Pagination controls */}
        {totalPages > 1 && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => handlePageChange(currentPage - 1)}
              disabled={currentPage === 1}
              className="p-0.5 text-gray-500 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <ChevronLeft size={14} />
            </button>
            <span className="text-[9px] text-gray-500">
              {currentPage} / {totalPages}
            </span>
            <button
              onClick={() => handlePageChange(currentPage + 1)}
              disabled={currentPage === totalPages}
              className="p-0.5 text-gray-500 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        )}
        
        {selectedFrame && (
          <button
            onClick={() => setSelectedFrame(null)}
            className="text-[9px] text-gray-600 hover:text-white flex items-center gap-1"
          >
            <X size={10} /> Close preview
          </button>
        )}
      </div>
      
      {/* Frame Gallery/Filmstrip */}
      <div className="relative">
        {loading && (
          <div className="absolute inset-0 bg-gray-900/80 flex items-center justify-center z-10">
            <Loader2 size={16} className="animate-spin text-gray-500" />
          </div>
        )}
        
        <div className="flex gap-1 overflow-x-auto pb-1 scrollbar-thin scrollbar-thumb-gray-700 scrollbar-track-transparent">
          {frames.map((frame) => (
            <button
              key={frame.id}
              onClick={() => handleFrameClick(frame)}
              className={`
                relative flex-shrink-0 overflow-hidden border transition-all
                hover:border-white focus:outline-none
                ${selectedFrame?.id === frame.id 
                  ? 'border-blue-500 ring-1 ring-blue-500' 
                  : 'border-gray-800 hover:border-gray-600'}
              `}
            >
              {/* Thumbnail image (small, fast to load) */}
              <img
                src={getThumbnailUrl(frame)}
                alt={`Frame ${frame.index} at ${formatTimestamp(frame.timestamp)}`}
                className="w-20 h-12 object-cover bg-gray-800"
                loading="lazy"
                onError={(e) => {
                  // Fallback to full frame if thumbnail fails
                  (e.target as HTMLImageElement).src = getFullFrameUrl(frame)
                }}
              />
              
              {/* Timestamp overlay */}
              <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent px-1 py-0.5">
                <span className="text-[8px] text-gray-300">
                  {formatTimestamp(frame.timestamp)}
                </span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Selected Frame Preview (Full-size) */}
      {selectedFrame && (
        <div className="border border-gray-800 bg-black overflow-hidden rounded">
          <div className="p-2 border-b border-gray-800 flex items-center justify-between bg-gray-900">
            <span className="text-[10px] text-gray-400">
              Frame {selectedFrame.index} • {formatTimestamp(selectedFrame.timestamp)}
            </span>
          </div>
          <div className="p-2 flex justify-center">
            <img
              src={getFullFrameUrl(selectedFrame)}
              alt={`Frame ${selectedFrame.index}`}
              className="max-w-full max-h-64 object-contain"
            />
          </div>
        </div>
      )}
    </div>
  )
}
