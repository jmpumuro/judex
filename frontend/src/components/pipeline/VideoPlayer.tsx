import { FC, useState, useRef, useEffect } from 'react'

interface VideoPlayerProps {
  videoUrl: string
  violenceSegments?: Array<{ start_time: number; end_time: number }>
  className?: string
}

const VideoPlayer: FC<VideoPlayerProps> = ({ videoUrl, violenceSegments = [], className = '' }) => {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [duration, setDuration] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)

  useEffect(() => {
    const video = videoRef.current
    if (!video) return

    const handleLoadedMetadata = () => {
      setDuration(video.duration)
    }

    const handleTimeUpdate = () => {
      setCurrentTime(video.currentTime)
    }

    const handlePlay = () => setIsPlaying(true)
    const handlePause = () => setIsPlaying(false)

    video.addEventListener('loadedmetadata', handleLoadedMetadata)
    video.addEventListener('timeupdate', handleTimeUpdate)
    video.addEventListener('play', handlePlay)
    video.addEventListener('pause', handlePause)

    return () => {
      video.removeEventListener('loadedmetadata', handleLoadedMetadata)
      video.removeEventListener('timeupdate', handleTimeUpdate)
      video.removeEventListener('play', handlePlay)
      video.removeEventListener('pause', handlePause)
    }
  }, [])

  const handleSeek = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const pos = (e.clientX - rect.left) / rect.width
    if (videoRef.current) {
      videoRef.current.currentTime = pos * duration
    }
  }

  return (
    <div className={`bg-black rounded-lg overflow-hidden ${className}`}>
      {/* Video Element */}
      <video
        ref={videoRef}
        src={videoUrl}
        controls
        className="w-full h-full object-contain"
        style={{ maxHeight: '450px' }}
      />

      {/* Custom Timeline with Violence Markers */}
      {violenceSegments.length > 0 && duration > 0 && (
        <div className="relative px-4 py-2 bg-dark-100">
          {/* Timeline */}
          <div
            className="relative h-2 bg-dark-200 rounded-full cursor-pointer overflow-visible"
            onClick={handleSeek}
          >
            {/* Progress */}
            <div
              className="absolute h-full bg-primary rounded-full"
              style={{ width: `${(currentTime / duration) * 100}%` }}
            />

            {/* Violence Markers */}
            {violenceSegments.map((segment, index) => {
              const startPercent = (segment.start_time / duration) * 100
              const widthPercent = ((segment.end_time - segment.start_time) / duration) * 100

              return (
                <div
                  key={index}
                  className="absolute top-0 h-full bg-danger shadow-lg shadow-danger/50 z-10"
                  style={{
                    left: `${startPercent}%`,
                    width: `${Math.max(widthPercent, 0.5)}%`,
                    minWidth: '3px',
                  }}
                  title={`Violence detected: ${segment.start_time.toFixed(1)}s - ${segment.end_time.toFixed(1)}s`}
                />
              )
            })}

            {/* Playhead */}
            <div
              className="absolute top-1/2 -translate-y-1/2 w-3 h-3 bg-white rounded-full shadow-lg z-20"
              style={{ left: `${(currentTime / duration) * 100}%` }}
            />
          </div>

          {/* Time Display */}
          <div className="flex justify-between text-xs text-gray-400 mt-2">
            <span>{formatTime(currentTime)}</span>
            <span>{formatTime(duration)}</span>
          </div>
        </div>
      )}
    </div>
  )
}

const formatTime = (seconds: number): string => {
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

export default VideoPlayer
