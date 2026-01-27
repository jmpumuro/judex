import { FC } from 'react'
import { Play, Trash2, Eye, Loader2, RotateCcw } from 'lucide-react'
import { QueueVideo } from '@/types'
import { formatBytes, formatTimestamp } from '@/utils/format'
import Badge from '../common/Badge'

interface FileTreeProps {
  videos: QueueVideo[]
  selectedId: string | null
  onSelect: (id: string) => void
  onProcess: (id: string) => void
  onDelete: (id: string) => void
  onPreview: (id: string) => void
  onRetry: (id: string) => void
}

const FileTree: FC<FileTreeProps> = ({
  videos,
  selectedId,
  onSelect,
  onProcess,
  onDelete,
  onPreview,
  onRetry,
}) => {
  return (
    <div className="space-y-2">
      {videos.map((video) => (
        <div
          key={video.id}
          className={`group relative card p-3 transition-all cursor-pointer ${
            selectedId === video.id
              ? 'ring-2 ring-primary bg-dark-50'
              : 'hover:bg-dark-50'
          }`}
          onClick={() => onSelect(video.id)}
        >
          {/* Video Info */}
          <div className="mb-2">
            <p className="text-sm font-medium text-white truncate pr-16" title={video.filename}>
              {video.filename}
            </p>
            <div className="flex items-center justify-between mt-1">
              <span className="text-xs text-gray-500">
                {formatBytes(video.size)}
              </span>
              <span className="text-xs text-gray-500">
                {formatTimestamp(video.uploaded_at)}
              </span>
            </div>
          </div>

          {/* Status & Progress */}
          <div className="flex items-center justify-between">
            <Badge variant={video.status}>{video.status}</Badge>
            {video.status === 'processing' && (
              <span className="text-xs text-primary font-medium">
                {video.progress}%
              </span>
            )}
          </div>

          {/* Progress Bar */}
          {video.status === 'processing' && (
            <div className="mt-2 h-1 bg-dark-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-primary transition-all duration-300"
                style={{ width: `${video.progress}%` }}
              />
            </div>
          )}

          {/* Current Stage */}
          {video.current_stage && video.status === 'processing' && (
            <p className="text-xs text-gray-500 mt-1">
              {video.current_stage.replace(/_/g, ' ')}
            </p>
          )}

          {/* Action Icons */}
          <div className="absolute top-3 right-3 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            {video.status === 'pending' && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onProcess(video.id)
                }}
                className="p-1.5 bg-primary/20 hover:bg-primary/30 rounded text-primary transition-colors"
                title="Process video"
              >
                <Play size={14} />
              </button>
            )}

            {video.status === 'processing' && (
              <div className="p-1.5 bg-primary/20 rounded">
                <Loader2 size={14} className="animate-spin text-primary" />
              </div>
            )}

            {video.status === 'error' && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onRetry(video.id)
                }}
                className="p-1.5 bg-warning/20 hover:bg-warning/30 rounded text-warning transition-colors"
                title="Retry processing"
              >
                <RotateCcw size={14} />
              </button>
            )}

            {video.status === 'completed' && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onPreview(video.id)
                }}
                className="p-1.5 bg-primary/20 hover:bg-primary/30 rounded text-primary transition-colors"
                title="Preview original video"
              >
                <Eye size={14} />
              </button>
            )}

            <button
              onClick={(e) => {
                e.stopPropagation()
                onDelete(video.id)
              }}
              className="p-1.5 bg-danger/20 hover:bg-danger/30 rounded text-danger transition-colors"
              title="Delete video"
            >
              <Trash2 size={14} />
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}

export default FileTree
