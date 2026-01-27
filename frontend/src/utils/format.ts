export const formatBytes = (bytes: number): string => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`
}

export const formatDuration = (seconds: number): string => {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  
  if (h > 0) {
    return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
  }
  return `${m}:${s.toString().padStart(2, '0')}`
}

export const formatTimestamp = (timestamp: number): string => {
  const date = new Date(timestamp)
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export const formatPercent = (value: number): string => {
  return `${Math.round(value * 100)}%`
}

export const getVerdictColor = (verdict: string): string => {
  const colors = {
    SAFE: 'text-success',
    CAUTION: 'text-warning',
    UNSAFE: 'text-danger',
    NEEDS_REVIEW: 'text-primary',
  }
  return colors[verdict as keyof typeof colors] || 'text-gray-400'
}

export const getStatusColor = (status: string): string => {
  const colors = {
    pending: 'text-gray-400',
    processing: 'text-primary',
    completed: 'text-success',
    error: 'text-danger',
  }
  return colors[status as keyof typeof colors] || 'text-gray-400'
}
