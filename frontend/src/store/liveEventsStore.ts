import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface LiveEvent {
  frame_id: string
  timestamp: number
  stream_id: string
  violence_score: number
  objects: Array<{
    label: string
    category?: string
    confidence: number
    bbox?: { x1: number; y1: number; x2: number; y2: number } | [number, number, number, number]
  }>
  thumbnail?: string
  reviewed?: boolean
  manual_verdict?: 'safe' | 'violation'
}

interface LiveEventsState {
  events: LiveEvent[]
  addEvent: (event: LiveEvent) => void
  removeEvent: (frameId: string) => void
  clearEvents: () => void
  markReviewed: (frameId: string, verdict: 'safe' | 'violation') => void
  getEvent: (frameId: string) => LiveEvent | undefined
}

// Max events to keep in storage to avoid quota issues
const MAX_EVENTS = 100

export const useLiveEventsStore = create<LiveEventsState>()(
  persist(
    (set, get) => ({
      events: [],
      
      addEvent: (event) => set((state) => {
        // Add to front, keep max events
        const newEvents = [event, ...state.events].slice(0, MAX_EVENTS)
        return { events: newEvents }
      }),
      
      removeEvent: (frameId) => set((state) => ({
        events: state.events.filter(e => e.frame_id !== frameId)
      })),
      
      clearEvents: () => set({ events: [] }),
      
      markReviewed: (frameId, verdict) => set((state) => ({
        events: state.events.map(e => 
          e.frame_id === frameId 
            ? { ...e, reviewed: true, manual_verdict: verdict }
            : e
        )
      })),
      
      getEvent: (frameId) => get().events.find(e => e.frame_id === frameId),
    }),
    {
      name: 'live-events-storage',
      // Only store essential data, compress thumbnails
      partialize: (state) => ({
        events: state.events.map(e => ({
          ...e,
          // Truncate thumbnail if too large
          thumbnail: e.thumbnail && e.thumbnail.length > 10000 
            ? e.thumbnail.substring(0, 10000) 
            : e.thumbnail
        }))
      }),
    }
  )
)
