import { FC, useState, useMemo } from 'react'
import { Eye, Trash2, RefreshCw, Camera, X, Check, AlertTriangle } from 'lucide-react'
import { useLiveEventsStore, LiveEvent } from '@/store/liveEventsStore'
import toast from 'react-hot-toast'

const LiveEvents: FC = () => {
  const { events, removeEvent, markReviewed, clearEvents, getEvent } = useLiveEventsStore()
  
  const [filter, setFilter] = useState<'all' | 'violations' | 'high-violence' | 'weapons' | 'safe'>('all')
  const [streamFilter, setStreamFilter] = useState<string>('all')
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null)
  
  // Get unique streams for filter dropdown
  const uniqueStreams = useMemo(() => {
    const streams = new Set(events.map(e => e.stream_id))
    return Array.from(streams)
  }, [events])
  
  // Filter events
  const filteredEvents = useMemo(() => {
    return events.filter(event => {
      // Stream filter
      if (streamFilter !== 'all' && event.stream_id !== streamFilter) return false
      
      // Severity filter (like index.html)
      const hasWeapon = event.objects.some(o => o.category === 'weapon')
      
      switch (filter) {
        case 'violations':
          return event.violence_score >= 0.4 || hasWeapon
        case 'high-violence':
          return event.violence_score >= 0.7
        case 'weapons':
          return hasWeapon
        case 'safe':
          return event.violence_score < 0.4 && !hasWeapon
        default:
          return true
      }
    }).sort((a, b) => b.timestamp - a.timestamp) // Newest first
  }, [events, filter, streamFilter])
  
  // Calculate stats
  const stats = useMemo(() => {
    const total = events.length
    const violations = events.filter(e => e.violence_score >= 0.4 || e.objects.some(o => o.category === 'weapon')).length
    const safe = events.filter(e => e.violence_score < 0.4 && !e.objects.some(o => o.category === 'weapon')).length
    const avgViolence = total > 0 
      ? Math.round((events.reduce((sum, e) => sum + e.violence_score, 0) / total) * 100)
      : 0
    return { total, violations, safe, avgViolence }
  }, [events])
  
  const selectedEvent = selectedEventId ? getEvent(selectedEventId) : null
  
  const handleDelete = (frameId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    removeEvent(frameId)
    if (selectedEventId === frameId) setSelectedEventId(null)
    toast.success('Event deleted')
  }
  
  const handleMarkReviewed = (verdict: 'safe' | 'violation') => {
    if (selectedEventId) {
      markReviewed(selectedEventId, verdict)
      toast.success(`Marked as ${verdict}`)
    }
  }
  
  const getStatusBadge = (event: LiveEvent) => {
    const violencePercent = Math.round(event.violence_score * 100)
    if (event.reviewed) {
      return event.manual_verdict === 'safe' 
        ? { text: 'REVIEWED (SAFE)', color: 'bg-green-500/20 text-green-400' }
        : { text: 'REVIEWED (VIOLATION)', color: 'bg-red-500/20 text-red-400' }
    }
    return violencePercent > 40 
      ? { text: 'VIOLATION', color: 'bg-red-500/20 text-red-400' }
      : { text: 'SAFE', color: 'bg-green-500/20 text-green-400' }
  }

  return (
    <div className="h-full flex flex-col bg-black text-white overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-800 flex-shrink-0">
        <span className="text-xs text-gray-500 tracking-widest">LIVE EVENTS</span>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {/* Filters */}
        <div className="bg-gray-900 border border-gray-800 p-4 mb-6">
          <div className="flex flex-wrap gap-4 items-end">
            <div className="flex-1 min-w-[200px]">
              <label className="block text-xs text-gray-500 uppercase tracking-wider mb-2">Filter by Severity</label>
              <select 
                value={filter} 
                onChange={(e) => setFilter(e.target.value as any)}
                className="w-full bg-black border border-gray-700 px-3 py-2 text-sm"
              >
                <option value="all">All Events</option>
                <option value="violations">Violations Only</option>
                <option value="high-violence">High Violence (&gt;70%)</option>
                <option value="weapons">Weapons Detected</option>
                <option value="safe">Safe Only</option>
              </select>
            </div>
            <div className="flex-1 min-w-[200px]">
              <label className="block text-xs text-gray-500 uppercase tracking-wider mb-2">Stream</label>
              <select 
                value={streamFilter} 
                onChange={(e) => setStreamFilter(e.target.value)}
                className="w-full bg-black border border-gray-700 px-3 py-2 text-sm"
              >
                <option value="all">All Streams</option>
                {uniqueStreams.map(stream => (
                  <option key={stream} value={stream}>{stream}</option>
                ))}
              </select>
            </div>
            <div className="flex gap-2">
              <button 
                onClick={() => window.location.reload()} 
                className="btn flex items-center gap-2 text-sm"
              >
                <RefreshCw size={14} /> Refresh
              </button>
              {events.length > 0 && (
                <button 
                  onClick={() => { clearEvents(); toast.success('Events cleared') }} 
                  className="btn flex items-center gap-2 text-sm bg-red-900/50 border-red-800 hover:bg-red-800"
                >
                  <Trash2 size={14} /> Clear All
                </button>
              )}
            </div>
          </div>
        </div>
        
        {/* Stats */}
        <div className="grid grid-cols-4 gap-4 mb-6">
          <div className="bg-gray-900 border border-gray-800 p-4 text-center">
            <div className="text-3xl font-light mb-1">{stats.total}</div>
            <div className="text-xs text-gray-500 uppercase tracking-wider">Total Events</div>
          </div>
          <div className="bg-gray-900 border border-gray-800 p-4 text-center">
            <div className="text-3xl font-light mb-1 text-red-400">{stats.violations}</div>
            <div className="text-xs text-gray-500 uppercase tracking-wider">Violations</div>
          </div>
          <div className="bg-gray-900 border border-gray-800 p-4 text-center">
            <div className="text-3xl font-light mb-1 text-green-400">{stats.safe}</div>
            <div className="text-xs text-gray-500 uppercase tracking-wider">Safe</div>
          </div>
          <div className="bg-gray-900 border border-gray-800 p-4 text-center">
            <div className="text-3xl font-light mb-1">{stats.avgViolence}%</div>
            <div className="text-xs text-gray-500 uppercase tracking-wider">Avg Violence</div>
          </div>
        </div>
        
        {/* Events Table */}
        <div className="bg-gray-900 border border-gray-800">
          <div className="p-4 border-b border-gray-800 flex items-center justify-between">
            <h2 className="text-sm font-semibold tracking-wider">CAPTURED EVENTS</h2>
            <span className="text-sm text-gray-500">{filteredEvents.length} events</span>
          </div>
          
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-800 text-left text-xs text-gray-500 uppercase">
                  <th className="p-3 w-24">Thumbnail</th>
                  <th className="p-3">Time</th>
                  <th className="p-3">Stream</th>
                  <th className="p-3">Violence</th>
                  <th className="p-3">Objects</th>
                  <th className="p-3">Status</th>
                  <th className="p-3 text-center">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredEvents.length > 0 ? (
                  filteredEvents.map(event => {
                    const violencePercent = Math.round(event.violence_score * 100)
                    const status = getStatusBadge(event)
                    
                    return (
                      <tr 
                        key={event.frame_id} 
                        className="border-b border-gray-800 hover:bg-gray-800/50 cursor-pointer"
                        onClick={() => setSelectedEventId(event.frame_id)}
                      >
                        <td className="p-3">
                          <div className="w-20 h-14 bg-black rounded overflow-hidden">
                            {event.thumbnail ? (
                              <img src={event.thumbnail} alt="" className="w-full h-full object-cover" />
                            ) : (
                              <div className="w-full h-full flex items-center justify-center text-gray-600">
                                <Camera size={16} />
                              </div>
                            )}
                          </div>
                        </td>
                        <td className="p-3 text-sm">
                          {new Date(event.timestamp).toLocaleTimeString()}
                          <div className="text-xs text-gray-500">
                            {new Date(event.timestamp).toLocaleDateString()}
                          </div>
                        </td>
                        <td className="p-3 text-sm">{event.stream_id}</td>
                        <td className="p-3">
                          <span className={`font-mono ${
                            violencePercent > 70 ? 'text-red-400' : 
                            violencePercent > 40 ? 'text-yellow-400' : 'text-green-400'
                          }`}>
                            {violencePercent}%
                          </span>
                        </td>
                        <td className="p-3 text-sm">{event.objects.length}</td>
                        <td className="p-3">
                          <span className={`px-2 py-1 rounded text-xs ${status.color}`}>
                            {status.text}
                          </span>
                        </td>
                        <td className="p-3">
                          <div className="flex items-center justify-center gap-2">
                            <button 
                              onClick={(e) => { e.stopPropagation(); setSelectedEventId(event.frame_id) }}
                              className="p-1.5 hover:bg-gray-700 rounded"
                              title="View Details"
                            >
                              <Eye size={16} />
                            </button>
                            <button 
                              onClick={(e) => handleDelete(event.frame_id, e)}
                              className="p-1.5 hover:bg-gray-700 rounded text-red-400"
                              title="Delete"
                            >
                              <Trash2 size={16} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })
                ) : (
                  <tr>
                    <td colSpan={7} className="p-12 text-center text-gray-500">
                      <Camera size={32} className="mx-auto mb-3 opacity-50" />
                      <div className="text-lg mb-1">No events match your filters</div>
                      <div className="text-sm">Try adjusting the filters or start a live feed</div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Event Detail Modal */}
      {selectedEvent && (
        <div className="fixed inset-0 bg-black/90 flex items-center justify-center z-50" onClick={() => setSelectedEventId(null)}>
          <div className="bg-gray-900 border border-gray-700 w-full max-w-3xl max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="p-4 border-b border-gray-700 flex items-center justify-between">
              <h3 className="text-sm font-semibold tracking-wider">LIVE EVENT DETAILS</h3>
              <button onClick={() => setSelectedEventId(null)} className="text-gray-400 hover:text-white">
                <X size={20} />
              </button>
            </div>
            
            <div className="p-6 grid grid-cols-2 gap-6">
              {/* Left: Frame Image */}
              <div>
                <label className="block text-xs text-gray-500 uppercase tracking-wider mb-2">Captured Frame</label>
                <div className="bg-black rounded overflow-hidden">
                  {selectedEvent.thumbnail ? (
                    <img src={selectedEvent.thumbnail} alt="" className="w-full h-auto" />
                  ) : (
                    <div className="aspect-video flex items-center justify-center text-gray-600">
                      <Camera size={32} />
                    </div>
                  )}
                </div>
              </div>
              
              {/* Right: Details */}
              <div className="space-y-4">
                <div>
                  <label className="block text-xs text-gray-500 uppercase tracking-wider mb-2">Event Info</label>
                  <div className="bg-black p-3 space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-400">Time</span>
                      <span>{new Date(selectedEvent.timestamp).toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Stream</span>
                      <span>{selectedEvent.stream_id}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Violence Score</span>
                      <span className={`${
                        selectedEvent.violence_score > 0.7 ? 'text-red-400' : 
                        selectedEvent.violence_score > 0.4 ? 'text-yellow-400' : 'text-green-400'
                      }`}>
                        {Math.round(selectedEvent.violence_score * 100)}%
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Objects Detected</span>
                      <span>{selectedEvent.objects.length}</span>
                    </div>
                  </div>
                </div>
                
                {selectedEvent.objects.length > 0 && (
                  <div>
                    <label className="block text-xs text-gray-500 uppercase tracking-wider mb-2">Detected Objects</label>
                    <div className="bg-black p-3 space-y-2">
                      {selectedEvent.objects.map((obj, idx) => (
                        <div key={idx} className="flex justify-between text-sm">
                          <span className="capitalize">{obj.label}</span>
                          <span className="text-gray-500">{Math.round(obj.confidence * 100)}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                
                {/* Manual Review */}
                <div>
                  <label className="block text-xs text-gray-500 uppercase tracking-wider mb-2">Manual Review</label>
                  <div className="flex gap-2">
                    <button 
                      onClick={() => handleMarkReviewed('safe')}
                      className="flex-1 btn flex items-center justify-center gap-2 bg-green-600 border-green-600 hover:bg-green-700"
                    >
                      <Check size={16} /> SAFE
                    </button>
                    <button 
                      onClick={() => handleMarkReviewed('violation')}
                      className="flex-1 btn flex items-center justify-center gap-2 bg-red-600 border-red-600 hover:bg-red-700"
                    >
                      <AlertTriangle size={16} /> VIOLATION
                    </button>
                  </div>
                  {selectedEvent.reviewed && (
                    <div className="mt-2 text-center text-sm text-gray-400">
                      Marked as: <span className={selectedEvent.manual_verdict === 'safe' ? 'text-green-400' : 'text-red-400'}>
                        {selectedEvent.manual_verdict?.toUpperCase()}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default LiveEvents
