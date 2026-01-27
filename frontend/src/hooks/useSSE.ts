import { useEffect, useRef, useState } from 'react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8012'

interface SSEData {
  stage: string
  progress: number
  message: string
  stage_output?: any
}

export const useSSE = (videoId: string | null) => {
  const [data, setData] = useState<SSEData | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!videoId) {
      return
    }

    console.log(`Connecting SSE for video ${videoId}`)
    const eventSource = new EventSource(`${API_URL}/v1/sse/${videoId}`)
    eventSourceRef.current = eventSource

    eventSource.onopen = () => {
      setIsConnected(true)
      setError(null)
      console.log(`SSE connected for video ${videoId}`)
    }

    eventSource.onmessage = (event) => {
      try {
        const eventData = JSON.parse(event.data) as SSEData
        setData(eventData)
        
        // Close connection when complete
        if (eventData.stage === 'complete') {
          console.log(`SSE complete for video ${videoId}`)
          eventSource.close()
          setIsConnected(false)
        }
      } catch (err) {
        console.error('Error parsing SSE data:', err)
      }
    }

    eventSource.onerror = (err) => {
      console.error(`SSE error for video ${videoId}:`, err)
      setError(new Error('SSE connection error'))
      eventSource.close()
      setIsConnected(false)
    }

    return () => {
      if (eventSource.readyState !== EventSource.CLOSED) {
        console.log(`Closing SSE for video ${videoId}`)
        eventSource.close()
      }
      setIsConnected(false)
    }
  }, [videoId])

  const disconnect = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      setIsConnected(false)
    }
  }

  return { data, isConnected, error, disconnect }
}
