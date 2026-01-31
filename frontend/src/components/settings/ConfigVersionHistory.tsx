/**
 * ConfigVersionHistory - Version history and rollback UI
 * 
 * Industry Standard: Configuration versioning with audit trail and rollback.
 */
import { FC, useState, useEffect, useCallback } from 'react'
import { History, RotateCcw, Check, Clock } from 'lucide-react'
import { configApi, ConfigVersion } from '@/api/endpoints'
import toast from 'react-hot-toast'

interface ConfigVersionHistoryProps {
  criteriaId: string
  onRollback?: () => void
}

export const ConfigVersionHistory: FC<ConfigVersionHistoryProps> = ({ 
  criteriaId, 
  onRollback 
}) => {
  const [versions, setVersions] = useState<ConfigVersion[]>([])
  const [loading, setLoading] = useState(true)
  const [rollingBack, setRollingBack] = useState<string | null>(null)
  
  // Load version history
  useEffect(() => {
    const load = async () => {
      try {
        const data = await configApi.listVersions(criteriaId)
        setVersions(data)
      } catch (err) {
        console.error('Failed to load versions:', err)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [criteriaId])
  
  // Handle rollback
  const handleRollback = useCallback(async (versionId: string) => {
    setRollingBack(versionId)
    try {
      await configApi.rollback(criteriaId, versionId)
      toast.success('Rolled back successfully')
      // Reload versions
      const data = await configApi.listVersions(criteriaId)
      setVersions(data)
      onRollback?.()
    } catch (err: any) {
      console.error('Rollback failed:', err)
      toast.error(err.response?.data?.detail || 'Failed to rollback')
    } finally {
      setRollingBack(null)
    }
  }, [criteriaId, onRollback])
  
  // Format date
  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr)
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }
  
  if (loading) {
    return (
      <div className="p-4 text-center text-gray-500 text-sm">
        Loading version history...
      </div>
    )
  }
  
  if (versions.length === 0) {
    return (
      <div className="p-4 text-center text-gray-500">
        <History size={24} className="mx-auto mb-2 opacity-50" />
        <p className="text-sm">No version history</p>
        <p className="text-[10px]">Built-in presets don't have versions</p>
      </div>
    )
  }
  
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <History size={14} className="text-gray-400" />
        <h3 className="text-sm font-medium text-white">Version History</h3>
      </div>
      
      <div className="space-y-2 max-h-60 overflow-y-auto">
        {versions.map((version, idx) => (
          <div
            key={version.version_id}
            className={`p-2 rounded border ${
              version.is_current 
                ? 'border-green-900/50 bg-green-900/10' 
                : 'border-gray-800 bg-gray-900/30'
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono text-gray-400">
                    v{versions.length - idx}
                  </span>
                  {version.is_current && (
                    <span className="flex items-center gap-0.5 text-[9px] text-green-400">
                      <Check size={10} />
                      current
                    </span>
                  )}
                </div>
                
                <div className="flex items-center gap-1 text-[10px] text-gray-500 mt-0.5">
                  <Clock size={10} />
                  {formatDate(version.created_at)}
                </div>
                
                {version.change_summary && (
                  <p className="text-[10px] text-gray-400 mt-1 truncate">
                    {version.change_summary}
                  </p>
                )}
              </div>
              
              {!version.is_current && (
                <button
                  onClick={() => handleRollback(version.version_id)}
                  disabled={rollingBack !== null}
                  className="flex items-center gap-1 px-2 py-1 text-[10px] text-gray-400 hover:text-white hover:bg-gray-800 rounded disabled:opacity-50"
                >
                  <RotateCcw size={10} className={rollingBack === version.version_id ? 'animate-spin' : ''} />
                  Rollback
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
      
      <p className="text-[9px] text-gray-600 text-center">
        Showing last {versions.length} versions
      </p>
    </div>
  )
}

export default ConfigVersionHistory
