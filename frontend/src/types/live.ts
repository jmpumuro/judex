export type StreamSource = 'webcam' | 'rtsp' | 'rtmp' | 'http'
export type EventStatus = 'pending' | 'reviewed' | 'dismissed'

export interface LiveStreamConfig {
  source: StreamSource
  url?: string
  deviceId?: string
}

export interface Detection {
  class: string
  confidence: number
  bbox: [number, number, number, number]
}

export interface LiveDetection {
  timestamp: number
  objects: Detection[]
  violence_score: number
}

export interface LiveEvent {
  id: string
  timestamp: number
  thumbnail: string
  detections: LiveDetection
  status: EventStatus
  stream_source: string
}

export interface LiveStats {
  total_frames: number
  total_events: number
  violence_detected: number
  objects_detected: number
  avg_fps: number
}
