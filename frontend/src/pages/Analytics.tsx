import { FC, useMemo } from 'react'
import { BarChart3, Video, Shield, AlertTriangle, CheckCircle, XCircle } from 'lucide-react'
import { useVideoStore } from '@/store/videoStore'

const Analytics: FC = () => {
  const { queue } = useVideoStore()

  const stats = useMemo(() => {
    const completed = queue.filter(v => v.status === 'completed')
    const safe = completed.filter(v => v.verdict === 'SAFE')
    const caution = completed.filter(v => v.verdict === 'CAUTION')
    const unsafe = completed.filter(v => v.verdict === 'UNSAFE')
    const needsReview = completed.filter(v => v.verdict === 'NEEDS_REVIEW')

    let avgViolence = 0, avgProfanity = 0, avgDrugs = 0, count = 0

    completed.forEach(v => {
      if (v.result?.criteria || v.result?.criteria_scores) {
        const criteria = v.result.criteria_scores || v.result.criteria || {}
        const getScore = (val: any): number => {
          if (typeof val === 'number') return val
          if (typeof val === 'object' && val !== null) return val.score || val.value || 0
          return 0
        }
        avgViolence += getScore((criteria as any).violence)
        avgProfanity += getScore((criteria as any).profanity)
        avgDrugs += getScore((criteria as any).drugs)
        count++
      }
    })

    if (count > 0) { avgViolence /= count; avgProfanity /= count; avgDrugs /= count }

    return {
      total: queue.length,
      completed: completed.length,
      processing: queue.filter(v => v.status === 'processing').length,
      queued: queue.filter(v => v.status === 'queued').length,
      failed: queue.filter(v => v.status === 'failed').length,
      safe: safe.length, caution: caution.length, unsafe: unsafe.length, needsReview: needsReview.length,
      avgViolence, avgProfanity, avgDrugs,
      safeRate: completed.length > 0 ? (safe.length / completed.length * 100) : 0,
    }
  }, [queue])

  return (
    <div className="h-full flex flex-col bg-black text-white overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-800 flex-shrink-0">
        <span className="text-xs text-gray-500 tracking-widest">BATCH ANALYTICS</span>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {/* Summary Cards */}
        <div className="grid grid-cols-4 gap-4 mb-6">
          <div className="bg-gray-900 border border-gray-800 p-5">
            <div className="flex items-center justify-between mb-3">
              <Video size={20} className="text-gray-500" />
              <span className="text-[10px] text-gray-500 uppercase">Total Videos</span>
            </div>
            <div className="text-3xl font-bold">{stats.total}</div>
            <div className="text-xs text-gray-500 mt-1">{stats.completed} completed, {stats.processing} processing</div>
          </div>

          <div className="bg-gray-900 border border-gray-800 p-5">
            <div className="flex items-center justify-between mb-3">
              <CheckCircle size={20} className="text-green-500" />
              <span className="text-[10px] text-gray-500 uppercase">Safe</span>
            </div>
            <div className="text-3xl font-bold text-green-400">{stats.safe}</div>
            <div className="text-xs text-gray-500 mt-1">{stats.safeRate.toFixed(0)}% pass rate</div>
          </div>

          <div className="bg-gray-900 border border-gray-800 p-5">
            <div className="flex items-center justify-between mb-3">
              <AlertTriangle size={20} className="text-yellow-500" />
              <span className="text-[10px] text-gray-500 uppercase">Caution</span>
            </div>
            <div className="text-3xl font-bold text-yellow-400">{stats.caution}</div>
            <div className="text-xs text-gray-500 mt-1">requires review</div>
          </div>

          <div className="bg-gray-900 border border-gray-800 p-5">
            <div className="flex items-center justify-between mb-3">
              <XCircle size={20} className="text-red-500" />
              <span className="text-[10px] text-gray-500 uppercase">Unsafe</span>
            </div>
            <div className="text-3xl font-bold text-red-400">{stats.unsafe}</div>
            <div className="text-xs text-gray-500 mt-1">flagged for issues</div>
          </div>
        </div>

        {/* Processing Status & Verdict */}
        <div className="grid grid-cols-2 gap-4 mb-6">
          <div className="bg-gray-900 border border-gray-800 p-5">
            <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-4">PROCESSING STATUS</h3>
            <div className="space-y-2">
              {[
                { label: 'Queued', value: stats.queued, color: 'text-gray-400' },
                { label: 'Processing', value: stats.processing, color: 'text-blue-400' },
                { label: 'Completed', value: stats.completed, color: 'text-green-400' },
                { label: 'Failed', value: stats.failed, color: 'text-red-400' },
              ].map(item => (
                <div key={item.label} className="flex items-center justify-between text-sm">
                  <span className={item.color}>{item.label}</span>
                  <span className="font-mono">{item.value}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-gray-900 border border-gray-800 p-5">
            <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-4">VERDICT DISTRIBUTION</h3>
            {stats.completed > 0 ? (
              <div className="space-y-2">
                {[
                  { label: 'SAFE', value: stats.safe, color: 'bg-green-500', textColor: 'text-green-400' },
                  { label: 'CAUTION', value: stats.caution, color: 'bg-yellow-500', textColor: 'text-yellow-400' },
                  { label: 'UNSAFE', value: stats.unsafe, color: 'bg-red-500', textColor: 'text-red-400' },
                  { label: 'NEEDS REVIEW', value: stats.needsReview, color: 'bg-blue-500', textColor: 'text-blue-400' },
                ].map(item => (
                  <div key={item.label}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className={item.textColor}>{item.label}</span>
                      <span>{item.value}</span>
                    </div>
                    <div className="h-1.5 bg-gray-800 rounded">
                      <div className={`h-full ${item.color} rounded`} style={{ width: `${(item.value / stats.completed) * 100}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-gray-500 text-center py-4 text-sm">No completed videos yet</p>
            )}
          </div>
        </div>

        {/* Average Scores */}
        <div className="bg-gray-900 border border-gray-800 p-5">
          <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-4">AVERAGE DETECTION SCORES</h3>
          {stats.completed > 0 ? (
            <div className="grid grid-cols-3 gap-6">
              {[
                { label: 'Violence', value: stats.avgViolence, color: 'bg-red-500' },
                { label: 'Profanity', value: stats.avgProfanity, color: 'bg-yellow-500' },
                { label: 'Drugs', value: stats.avgDrugs, color: 'bg-purple-500' },
              ].map(item => (
                <div key={item.label}>
                  <div className="flex justify-between mb-2 text-sm">
                    <span className="text-gray-400">{item.label}</span>
                    <span className="font-mono">{(item.value * 100).toFixed(1)}%</span>
                  </div>
                  <div className="h-2 bg-gray-800 rounded">
                    <div className={`h-full ${item.color} rounded`} style={{ width: `${item.value * 100}%` }} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-gray-500 text-center py-4 text-sm">Process videos to see average scores</p>
          )}
        </div>

        {/* Empty State */}
        {stats.total === 0 && (
          <div className="text-center py-12 border border-dashed border-gray-800 mt-6">
            <BarChart3 size={36} className="mx-auto mb-3 text-gray-700" />
            <p className="text-gray-500 mb-1 text-sm">No videos processed yet</p>
            <p className="text-xs text-gray-600">Add and process videos to see analytics</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default Analytics
