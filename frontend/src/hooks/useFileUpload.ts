import { useState, useCallback } from 'react'
import { useVideoStore } from '@/store/videoStore'
import { videoApi } from '@/api/endpoints/videos'
import toast from 'react-hot-toast'
import { QueueVideo } from '@/types'

export const useFileUpload = () => {
  const [isUploading, setIsUploading] = useState(false)
  const addVideos = useVideoStore(state => state.addVideos)

  const uploadFiles = useCallback(async (files: File[]) => {
    if (files.length === 0) {
      toast.error('No files selected')
      return null
    }

    setIsUploading(true)
    const toastId = toast.loading(`Uploading ${files.length} video(s)...`)

    try {
      // Create queue entries
      const queueVideos: QueueVideo[] = files.map(file => ({
        id: `${file.name}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        filename: file.name,
        size: file.size,
        status: 'pending',
        progress: 0,
        file,
        uploaded_at: Date.now(),
      }))

      // Add to queue immediately
      addVideos(queueVideos)

      // Upload to backend
      const response = await videoApi.uploadBatch(files)
      
      toast.success(`${files.length} video(s) uploaded successfully!`, { id: toastId })
      return response
    } catch (error) {
      toast.error('Upload failed', { id: toastId })
      console.error('Upload error:', error)
      throw error
    } finally {
      setIsUploading(false)
    }
  }, [addVideos])

  return { uploadFiles, isUploading }
}
