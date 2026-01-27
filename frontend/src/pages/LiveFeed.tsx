import { FC, useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Video, Play, Square, Camera, AlertTriangle, Shield, Activity, Radio } from 'lucide-react'
import { liveApi } from '@/api/endpoints'
import { useLiveEventsStore, LiveEvent } from '@/store/liveEventsStore'
import toast from 'react-hot-toast'

interface DetectedObject {
  label: string
  category?: string
  confidence: number
  bbox: { x1: number; y1: number; x2: number; y2: number } | [number, number, number, number]
}

interface AnalysisResult {
  objects?: DetectedObject[]
  detections?: DetectedObject[]
  violence_score?: number
  frame_id?: string
  timestamp?: number
}

const LiveFeed: FC = () => {
  const navigate = useNavigate()
  const addEvent = useLiveEventsStore(state => state.addEvent)
  
  const [isStreaming, setIsStreaming] = useState(false)
  const [feedType, setFeedType] = useState<'webcam' | 'rtsp' | 'http'>('webcam')
  const [streamUrl, setStreamUrl] = useState('')
  const [analysisInterval, setAnalysisInterval] = useState(2)
  const [autoSaveEvents, setAutoSaveEvents] = useState(true)
  
  const [stats, setStats] = useState({
    framesAnalyzed: 0,
    violenceScore: 0,
    objectCount: 0,
  })
  
  const [latestDetections, setLatestDetections] = useState<DetectedObject[]>([])
  
  const [recentEvents, setRecentEvents] = useState<Array<{
    id: string
    timestamp: number
    violenceScore: number
    objectCount: number
    thumbnail?: string
  }>>([])

  const videoRef = useRef<HTMLVideoElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const overlayCanvasRef = useRef<HTMLCanvasElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const analysisIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Start webcam
  const startWebcam = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 1280, height: 720 },
        audio: false,
      })
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play()
        
        videoRef.current.onloadedmetadata = () => {
          const video = videoRef.current!
          if (canvasRef.current) {
            canvasRef.current.width = video.videoWidth
            canvasRef.current.height = video.videoHeight
          }
          if (overlayCanvasRef.current) {
            overlayCanvasRef.current.width = video.videoWidth
            overlayCanvasRef.current.height = video.videoHeight
          }
        }
      }
      setIsStreaming(true)
      startAnalysis()
      toast.success('Camera started')
    } catch (error) {
      toast.error('Failed to access camera')
      console.error('Webcam error:', error)
    }
  }

  // Stop streaming and navigate to Live Events
  const stopStream = () => {
    if (analysisIntervalRef.current) {
      clearInterval(analysisIntervalRef.current)
      analysisIntervalRef.current = null
    }
    
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop())
      streamRef.current = null
    }
    
    if (videoRef.current) {
      videoRef.current.srcObject = null
    }
    
    if (overlayCanvasRef.current) {
      const ctx = overlayCanvasRef.current.getContext('2d')
      if (ctx) {
        ctx.clearRect(0, 0, overlayCanvasRef.current.width, overlayCanvasRef.current.height)
      }
    }
    
    setIsStreaming(false)
    setStats({ framesAnalyzed: 0, violenceScore: 0, objectCount: 0 })
    setLatestDetections([])
    
    toast.success('Feed stopped')
    navigate('/live-events')
  }

  // Draw bounding boxes on overlay canvas
  const drawBoundingBoxes = useCallback((objects: DetectedObject[]) => {
    const canvas = overlayCanvasRef.current
    const video = videoRef.current
    
    if (!canvas || !video) return
    
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    
    if (canvas.width === 0 || canvas.height === 0) {
      canvas.width = video.videoWidth || 640
      canvas.height = video.videoHeight || 480
    }
    
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    
    if (!objects || objects.length === 0) return
    
    const displayWidth = video.clientWidth
    const displayHeight = video.clientHeight
    
    canvas.style.width = `${displayWidth}px`
    canvas.style.height = `${displayHeight}px`
    
    objects.forEach(obj => {
      let x1, y1, x2, y2
      
      if (Array.isArray(obj.bbox)) {
        [x1, y1, x2, y2] = obj.bbox
      } else if (obj.bbox) {
        x1 = obj.bbox.x1; y1 = obj.bbox.y1; x2 = obj.bbox.x2; y2 = obj.bbox.y2
      } else {
        return
      }
      
      const width = x2 - x1
      const height = y2 - y1
      
      const category = obj.category || obj.label?.toLowerCase() || ''
      let color: string
      if (category === 'weapon' || category === 'knife' || category === 'gun') {
        color = '#FF0000'
      } else if (category === 'substance') {
        color = '#FFA500'
      } else if (category === 'person') {
        color = '#00FFFF'
      } else {
        color = '#00FF00'
      }
      
      ctx.strokeStyle = color
      ctx.lineWidth = 3
      ctx.strokeRect(x1, y1, width, height)
      
      const label = obj.label || 'object'
      const confidence = Math.round((obj.confidence || 0) * 100)
      const labelText = `${label} ${confidence}%`
      ctx.font = 'bold 14px sans-serif'
      const textWidth = ctx.measureText(labelText).width
      
      ctx.fillStyle = color
      ctx.fillRect(x1, y1 - 22, textWidth + 10, 22)
      
      ctx.fillStyle = '#000000'
      ctx.fillText(labelText, x1 + 5, y1 - 6)
    })
  }, [])

  // Analyze current frame
  const analyzeFrame = useCallback(async () => {
    if (!videoRef.current || !canvasRef.current) return
    
    const video = videoRef.current
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    if (!ctx || video.readyState < 2) return

    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    ctx.drawImage(video, 0, 0)
    
    const imageData = canvas.toDataURL('image/jpeg', 0.8)
    
    try {
      const result: AnalysisResult = await liveApi.analyzeFrame(imageData, 'webcam')
      const objects = result.objects || result.detections || []
      
      setStats(prev => ({
        framesAnalyzed: prev.framesAnalyzed + 1,
        violenceScore: result.violence_score || 0,
        objectCount: objects.length,
      }))
      
      setLatestDetections(objects)
      drawBoundingBoxes(objects)
      
      const createThumbnail = (): string | undefined => {
        try {
          const thumbCanvas = document.createElement('canvas')
          thumbCanvas.width = 120
          thumbCanvas.height = 68
          const thumbCtx = thumbCanvas.getContext('2d')
          if (!thumbCtx) return undefined
          
          thumbCtx.drawImage(video, 0, 0, 120, 68)
          
          const scaleX = 120 / video.videoWidth
          const scaleY = 68 / video.videoHeight
          objects.forEach(obj => {
            if (!obj.bbox) return
            let x1, y1, x2, y2
            if (Array.isArray(obj.bbox)) {
              [x1, y1, x2, y2] = obj.bbox
            } else {
              x1 = obj.bbox.x1; y1 = obj.bbox.y1; x2 = obj.bbox.x2; y2 = obj.bbox.y2
            }
            
            const category = obj.category || obj.label?.toLowerCase() || ''
            thumbCtx.strokeStyle = category.includes('weapon') ? '#FF0000' : '#00FF00'
            thumbCtx.lineWidth = 1
            thumbCtx.strokeRect(x1 * scaleX, y1 * scaleY, (x2 - x1) * scaleX, (y2 - y1) * scaleY)
          })
          
          return thumbCanvas.toDataURL('image/jpeg', 0.5)
        } catch {
          return undefined
        }
      }
      
      const frameId = result.frame_id || `evt_${Date.now()}`
      const thumbnail = createThumbnail()
      
      if (result.frame_id || objects.length > 0 || (result.violence_score || 0) > 0) {
        setRecentEvents(prev => [{
          id: frameId,
          timestamp: Date.now(),
          violenceScore: result.violence_score || 0,
          objectCount: objects.length,
          thumbnail,
        }, ...prev.slice(0, 19)])
        
        if (autoSaveEvents) {
          const liveEvent: LiveEvent = {
            frame_id: frameId,
            timestamp: Date.now(),
            stream_id: feedType === 'webcam' ? 'webcam' : streamUrl || 'stream',
            violence_score: result.violence_score || 0,
            objects: objects.map(obj => ({
              label: obj.label,
              category: obj.category,
              confidence: obj.confidence,
              bbox: obj.bbox,
            })),
            thumbnail,
          }
          addEvent(liveEvent)
        }
      }
    } catch (error) {
      console.error('Frame analysis error:', error)
    }
  }, [drawBoundingBoxes, autoSaveEvents, addEvent, feedType, streamUrl])

  const startAnalysis = () => {
    if (analysisIntervalRef.current) {
      clearInterval(analysisIntervalRef.current)
    }
    analysisIntervalRef.current = setInterval(analyzeFrame, analysisInterval * 1000)
  }

  const handleStart = () => {
    if (feedType === 'webcam') {
      startWebcam()
    } else {
      toast.error('External streams not yet supported')
    }
  }

  useEffect(() => {
    return () => {
      if (analysisIntervalRef.current) {
        clearInterval(analysisIntervalRef.current)
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop())
      }
    }
  }, [])

  const getCategoryColor = (category?: string, label?: string): string => {
    const cat = category || label?.toLowerCase() || ''
    if (cat === 'weapon' || cat === 'knife' || cat === 'gun') return 'border-l-red-500'
    if (cat === 'substance') return 'border-l-orange-500'
    if (cat === 'person') return 'border-l-cyan-400'
    return 'border-l-green-500'
  }

  return (
    <div className="h-full flex bg-black text-white overflow-hidden">
      {/* Main Video Section */}
      <div className="flex-1 flex flex-col border-r border-gray-800">
        {/* Header */}
        <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-2">
            <Video size={16} className="text-gray-500" />
            <span className="text-xs text-gray-500 tracking-widest">VIDEO FEED</span>
          </div>
          {isStreaming && (
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 bg-red-500 rounded-full animate-pulse" />
              <span className="text-xs text-red-400 font-medium">LIVE</span>
            </div>
          )}
        </div>

        {/* Video Container */}
        <div className="flex-1 relative bg-black flex items-center justify-center">
          <video
            ref={videoRef}
            className="max-w-full max-h-full object-contain"
            playsInline
            muted
          />
          <canvas ref={canvasRef} className="hidden" />
          <canvas
            ref={overlayCanvasRef}
            className="absolute top-0 left-0 w-full h-full pointer-events-none"
            style={{ objectFit: 'contain' }}
          />
          
          {!isStreaming && (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-center">
                <Camera size={48} className="mx-auto mb-4 text-gray-700" />
                <p className="text-gray-500 text-sm">Select a feed source and click Start</p>
              </div>
            </div>
          )}
        </div>

        {/* Controls */}
        <div className="px-4 py-3 border-t border-gray-800 flex items-center gap-3 flex-shrink-0">
          <select
            value={feedType}
            onChange={(e) => setFeedType(e.target.value as any)}
            disabled={isStreaming}
            className="bg-black border border-gray-800 px-3 py-1.5 text-xs"
          >
            <option value="webcam">Webcam</option>
            <option value="rtsp">RTSP Stream</option>
            <option value="http">HTTP/HLS</option>
          </select>

          {feedType !== 'webcam' && (
            <input
              type="text"
              value={streamUrl}
              onChange={(e) => setStreamUrl(e.target.value)}
              placeholder="Enter stream URL..."
              disabled={isStreaming}
              className="flex-1 bg-black border border-gray-800 px-3 py-1.5 text-xs"
            />
          )}

          <div className="flex items-center gap-2 text-xs text-gray-500">
            <span>Interval:</span>
            <select
              value={analysisInterval}
              onChange={(e) => setAnalysisInterval(Number(e.target.value))}
              className="bg-black border border-gray-800 px-2 py-1.5 text-xs"
            >
              <option value={1}>1s</option>
              <option value={2}>2s</option>
              <option value={5}>5s</option>
            </select>
          </div>

          <label className="flex items-center gap-1.5 text-xs text-gray-500 cursor-pointer">
            <input
              type="checkbox"
              checked={autoSaveEvents}
              onChange={(e) => setAutoSaveEvents(e.target.checked)}
              className="accent-white w-3 h-3"
            />
            Auto-save
          </label>

          <div className="flex-1" />

          {!isStreaming ? (
            <button onClick={handleStart} className="flex items-center gap-2 bg-white text-black px-4 py-1.5 text-xs font-medium hover:bg-gray-200 transition-colors">
              <Play size={12} /> START
            </button>
          ) : (
            <button onClick={stopStream} className="flex items-center gap-2 bg-red-600 text-white px-4 py-1.5 text-xs font-medium hover:bg-red-700 transition-colors">
              <Square size={12} /> STOP
            </button>
          )}
        </div>
      </div>

      {/* Right Panel */}
      <div className="w-80 flex flex-col overflow-hidden">
        {/* Live Stats */}
        <div className="p-4 border-b border-gray-800">
          <h3 className="text-[10px] text-gray-600 tracking-widest mb-3">LIVE STATS</h3>
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-500 flex items-center gap-2">
                <Radio size={12} /> Status
              </span>
              <span className={isStreaming ? 'text-green-400' : 'text-gray-600'}>
                {isStreaming ? 'STREAMING' : 'STOPPED'}
              </span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-500">Frames Analyzed</span>
              <span className="font-mono">{stats.framesAnalyzed}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-500 flex items-center gap-2">
                <AlertTriangle size={12} /> Violence
              </span>
              <span className={`font-mono ${
                stats.violenceScore > 0.5 ? 'text-red-400' : 
                stats.violenceScore > 0.3 ? 'text-yellow-400' : 'text-green-400'
              }`}>
                {(stats.violenceScore * 100).toFixed(0)}%
              </span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-500 flex items-center gap-2">
                <Shield size={12} /> Objects
              </span>
              <span className="font-mono">{stats.objectCount}</span>
            </div>
          </div>
        </div>

        {/* Latest Detections */}
        <div className="p-4 border-b border-gray-800">
          <h3 className="text-[10px] text-gray-600 tracking-widest mb-3">LATEST DETECTIONS</h3>
          {latestDetections.length > 0 ? (
            <div className="space-y-1.5">
              {latestDetections.slice(0, 5).map((obj, idx) => (
                <div 
                  key={idx} 
                  className={`p-2 bg-gray-900 border-l-2 ${getCategoryColor(obj.category, obj.label)}`}
                >
                  <div className="font-medium text-sm">{obj.label}</div>
                  <div className="text-[10px] text-gray-500">
                    Confidence: {Math.round(obj.confidence * 100)}%
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-gray-600 text-center py-3">No detections</p>
          )}
        </div>

        {/* Recent Events */}
        <div className="flex-1 p-4 overflow-hidden flex flex-col">
          <h3 className="text-[10px] text-gray-600 tracking-widest mb-3 flex-shrink-0">RECENT EVENTS</h3>
          {recentEvents.length > 0 ? (
            <div className="flex-1 overflow-y-auto space-y-1.5">
              {recentEvents.map(event => (
                <div key={event.id} className="flex items-center gap-2 p-2 bg-gray-900">
                  {event.thumbnail ? (
                    <img 
                      src={event.thumbnail} 
                      alt="" 
                      className="w-14 h-8 object-cover bg-black flex-shrink-0"
                    />
                  ) : (
                    <div className="w-14 h-8 bg-black flex items-center justify-center flex-shrink-0">
                      <Camera size={10} className="text-gray-700" />
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="text-[10px] text-gray-600">
                      {new Date(event.timestamp).toLocaleTimeString()}
                    </div>
                    <div className="text-xs">
                      {event.objectCount} obj, {(event.violenceScore * 100).toFixed(0)}%
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-gray-600 text-center py-3">No events captured yet</p>
          )}
        </div>
      </div>
    </div>
  )
}

export default LiveFeed
