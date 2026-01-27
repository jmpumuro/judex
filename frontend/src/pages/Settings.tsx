import { FC, useEffect, useState } from 'react'
import { Settings as SettingsIcon, Check, AlertCircle } from 'lucide-react'
import { useSettingsStore, PolicyPreset } from '@/store/settingsStore'
import { policyApi } from '@/api/endpoints'
import toast from 'react-hot-toast'

const PRESET_DESCRIPTIONS: Record<string, string> = {
  strict: 'Maximum safety - flags content at lower thresholds',
  balanced: 'Recommended - balanced between safety and false positives',
  lenient: 'Minimum flagging - only flags high-confidence issues',
  custom: 'Custom thresholds - manually configured',
}

const Settings: FC = () => {
  const { 
    currentPolicy, 
    currentPreset, 
    presets,
    setPresets,
    updateThreshold,
    applyPreset,
  } = useSettingsStore()

  const [isLoading, setIsLoading] = useState(true)
  const [validationResult, setValidationResult] = useState<{ valid: boolean; message: string } | null>(null)

  // Load presets on mount
  useEffect(() => {
    const loadPresets = async () => {
      try {
        const data = await policyApi.getPresets()
        setPresets(data)
        setIsLoading(false)
      } catch (error) {
        console.error('Failed to load presets:', error)
        setIsLoading(false)
      }
    }
    loadPresets()
  }, [setPresets])

  // Validate policy when it changes
  useEffect(() => {
    const validatePolicy = async () => {
      if (!currentPolicy) return
      try {
        const result = await policyApi.validate(currentPolicy)
        setValidationResult({ valid: result.status === 'valid', message: result.message })
      } catch {
        setValidationResult({ valid: false, message: 'Failed to validate policy' })
      }
    }
    validatePolicy()
  }, [currentPolicy])

  const handlePresetChange = (preset: PolicyPreset) => {
    applyPreset(preset)
    toast.success(`Applied ${preset} preset`)
  }

  const handleThresholdChange = (category: 'unsafe' | 'caution', key: string, value: number) => {
    updateThreshold(category, key, value)
  }

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center bg-black text-white">
        <div className="text-center">
          <SettingsIcon size={48} className="mx-auto mb-4 animate-pulse text-gray-600" />
          <p className="text-gray-400">Loading settings...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col bg-black text-white overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-800 flex-shrink-0">
        <span className="text-xs text-gray-500 tracking-widest">POLICY SETTINGS</span>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">

        {/* Presets */}
        <div className="mb-6">
          <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3">PRESETS</h3>
          <div className="grid grid-cols-4 gap-4">
            {(['strict', 'balanced', 'lenient', 'custom'] as PolicyPreset[]).map(preset => (
              <button
                key={preset}
                onClick={() => preset !== 'custom' && handlePresetChange(preset)}
                disabled={preset === 'custom'}
                className={`p-4 text-left border transition-all ${
                  currentPreset === preset 
                    ? 'border-white bg-gray-900' 
                    : 'border-gray-800 hover:border-gray-600'
                } ${preset === 'custom' ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium uppercase text-sm">{preset}</span>
                  {currentPreset === preset && <Check size={16} />}
                </div>
                <p className="text-xs text-gray-500">{PRESET_DESCRIPTIONS[preset]}</p>
              </button>
            ))}
          </div>
        </div>

        {/* Validation Status */}
        {validationResult && (
          <div className={`mb-6 p-4 border ${
            validationResult.valid 
              ? 'border-green-800 bg-green-900/20' 
              : 'border-red-800 bg-red-900/20'
          }`}>
            <div className="flex items-center gap-2">
              {validationResult.valid ? (
                <Check size={16} className="text-green-400" />
              ) : (
                <AlertCircle size={16} className="text-red-400" />
              )}
              <span className={validationResult.valid ? 'text-green-400' : 'text-red-400'}>
                {validationResult.message}
              </span>
            </div>
          </div>
        )}

        {/* Threshold Configuration */}
        {currentPolicy && (
          <div className="space-y-8">
            {/* UNSAFE Thresholds */}
            <div>
              <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3">
                UNSAFE THRESHOLDS
                <span className="ml-2 text-gray-600">(Content marked as UNSAFE if exceeds)</span>
              </h3>
              <div className="space-y-4 bg-gray-900 p-4 border border-gray-800">
                {Object.entries(currentPolicy.thresholds.unsafe).map(([key, value]) => (
                  <div key={key} className="flex items-center gap-4">
                    <label className="w-32 text-sm text-gray-400 uppercase">{key}</label>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={value}
                      onChange={(e) => handleThresholdChange('unsafe', key, parseFloat(e.target.value))}
                      className="flex-1 accent-red-500"
                    />
                    <span className="w-16 text-right font-mono text-sm">
                      {(value * 100).toFixed(0)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* CAUTION Thresholds */}
            <div>
              <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3">
                CAUTION THRESHOLDS
                <span className="ml-2 text-gray-600">(Content marked as CAUTION if exceeds)</span>
              </h3>
              <div className="space-y-4 bg-gray-900 p-4 border border-gray-800">
                {Object.entries(currentPolicy.thresholds.caution).map(([key, value]) => (
                  <div key={key} className="flex items-center gap-4">
                    <label className="w-32 text-sm text-gray-400 uppercase">{key}</label>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.05"
                      value={value}
                      onChange={(e) => handleThresholdChange('caution', key, parseFloat(e.target.value))}
                      className="flex-1 accent-yellow-500"
                    />
                    <span className="w-16 text-right font-mono text-sm">
                      {(value * 100).toFixed(0)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Info */}
            <div className="text-sm text-gray-500 border-t border-gray-800 pt-6">
              <p className="mb-2">
                <strong>How thresholds work:</strong>
              </p>
              <ul className="list-disc list-inside space-y-1">
                <li>Content scoring above <span className="text-red-400">UNSAFE</span> thresholds is marked as unsafe</li>
                <li>Content scoring above <span className="text-yellow-400">CAUTION</span> thresholds (but below unsafe) is marked as caution</li>
                <li>Content below caution thresholds is marked as <span className="text-green-400">SAFE</span></li>
                <li>Ambiguous cases may be marked as <span className="text-blue-400">NEEDS_REVIEW</span></li>
              </ul>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default Settings
