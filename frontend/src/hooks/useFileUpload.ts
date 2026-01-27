import { useState, useCallback } from 'react'
import { useVideoStore } from '@/store/videoStore'
import { videoApi } from '@/api/endpoints/videos'
import toast from 'react-hot-toast'

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
      // Create queue entries matching store's expected type
      const queueVideos = files.map(file => ({
        filename: file.name,
        file,
        status: 'queued' as const,
        source: 'local' as const,
        progress: 0,
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
