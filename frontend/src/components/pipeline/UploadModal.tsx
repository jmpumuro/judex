import { FC, useRef, useState } from 'react'
import { Upload, Link, Cloud, Database, X } from 'lucide-react'
import { useVideoStoreActions } from '@/store/videoStore'
import { usePipelineStore } from '@/store/pipelineStore'
import { VideoStatus } from '@/types/api'
import toast from 'react-hot-toast'

interface UploadModalProps {
  onClose: () => void
}

export const UploadModal: FC<UploadModalProps> = ({ onClose }) => {
  const { addVideos, selectVideo } = useVideoStoreActions()
  const uploadSource = usePipelineStore(state => state.uploadSource)
  const setUploadSource = usePipelineStore(state => state.setUploadSource)

  const [urlInput, setUrlInput] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileSelect = async (files: FileList | null) => {
    if (!files || files.length === 0) return

    // Accept both video and image files
    const fileArray = Array.from(files).filter(f =>
      f.type.startsWith('video/') ||
      f.type.startsWith('image/') ||
      f.name.match(/\.(mp4|avi|mov|mkv|webm|jpg|jpeg|png|webp|gif|bmp)$/i)
    )

    if (fileArray.length === 0) {
      toast.error('Please select valid video or image files')
      return
    }

    const ids = addVideos(fileArray.map(file => ({
      filename: file.name,
      file,
      status: 'queued' as VideoStatus,
      source: 'local',
      progress: 0,
    })))

    toast.success(`Added ${fileArray.length} video(s)`)
    onClose()

    if (ids.length > 0) {
      selectVideo(ids[0])
    }
  }

  const handleUrlImport = async () => {
    const urls = urlInput.split('\n').filter(u => u.trim())

    if (urls.length === 0) {
      toast.error('Please enter at least one URL')
      return
    }

    const ids = addVideos(urls.map(url => ({
      filename: url.split('/').pop() || 'video.mp4',
      file: null,
      status: 'queued' as VideoStatus,
      source: 'url',
      progress: 0,
    })))

    toast.success(`Added ${urls.length} video(s) from URLs`)
    setUrlInput('')
    onClose()

    if (ids.length > 0) {
      selectVideo(ids[0])
    }
  }

  return (
    <div className="fixed inset-0 bg-black/90 flex items-center justify-center z-50">
      <div className="bg-gray-900 border border-gray-700 w-full max-w-sm">
        {/* Header */}
        <div className="p-2 border-b border-gray-700 flex items-center justify-between">
          <h3 className="text-xs">ADD VIDEOS</h3>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-white"
          >
            <X size={16} />
          </button>
        </div>

        {/* Content */}
        <div className="p-3">
          {/* Source Selection */}
          <div className="grid grid-cols-4 gap-1 mb-3">
            {[
              { id: 'local', icon: Upload, label: 'LOCAL' },
              { id: 'url', icon: Link, label: 'URL' },
              { id: 'storage', icon: Cloud, label: 'CLOUD' },
              { id: 'database', icon: Database, label: 'DB' }
            ].map(source => (
              <button
                key={source.id}
                onClick={() => setUploadSource(source.id as any)}
                className={`p-2 text-center border transition-all ${
                  uploadSource === source.id
                    ? 'border-white bg-gray-800'
                    : 'border-gray-700'
                }`}
              >
                <source.icon size={14} className="mx-auto mb-0.5" />
                <div className="text-[9px]">{source.label}</div>
              </button>
            ))}
          </div>

          {/* Local Upload */}
          {uploadSource === 'local' && (
            <div>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept="video/*,image/*"
                className="hidden"
                onChange={(e) => handleFileSelect(e.target.files)}
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                className="w-full p-4 border border-dashed border-gray-600 hover:border-white transition-all text-center"
              >
                <Upload size={20} className="mx-auto mb-1 opacity-50" />
                <p className="text-[10px]">Click or drag (video/image)</p>
              </button>
            </div>
          )}

          {/* URL Import */}
          {uploadSource === 'url' && (
            <div>
              <textarea
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
                placeholder="URLs (one per line)"
                className="w-full h-20 bg-black border border-gray-700 p-2 text-[10px] resize-none focus:border-white outline-none"
              />
              <button
                onClick={handleUrlImport}
                className="btn w-full mt-2 text-[10px]"
              >
                IMPORT
              </button>
            </div>
          )}

          {/* Cloud/Database (Coming Soon) */}
          {(uploadSource === 'storage' || uploadSource === 'database') && (
            <div className="text-center py-4 text-gray-600">
              <Cloud size={20} className="mx-auto mb-1 opacity-50" />
              <p className="text-[10px]">Coming soon</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
