/**
 * PolicySettings - Fusion/Policy Controls Panel
 * 
 * Industry Standard: Schema-driven UI rendering.
 * Backend provides knob definitions, frontend renders generically.
 */
import { FC, useState, useEffect, useMemo, useCallback } from 'react'
import { 
  ChevronDown, ChevronUp, AlertTriangle, Check, 
  RotateCcw, Save, Eye, Info
} from 'lucide-react'
import { 
  configApi, 
  ConfigKnob, 
  ConfigSchema, 
  FusionSettings, 
  ConfigValidationResult,
  ConfigPreview,
} from '@/api/endpoints'
import toast from 'react-hot-toast'

interface PolicySettingsProps {
  criteriaId: string
  onSave?: () => void
}

// Render a single knob control based on its type
const KnobControl: FC<{
  knob: ConfigKnob
  value: any
  onChange: (value: any) => void
  error?: string
  warning?: string
}> = ({ knob, value, onChange, error, warning }) => {
  const currentValue = value ?? knob.default
  
  switch (knob.type) {
    case 'enum':
      return (
        <div className="space-y-1">
          <label className="text-xs text-gray-400">{knob.label}</label>
          <select
            value={currentValue}
            onChange={(e) => onChange(e.target.value)}
            className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
          >
            {knob.options?.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <p className="text-[10px] text-gray-600">{knob.description}</p>
          {error && <p className="text-[10px] text-red-400">{error}</p>}
          {warning && <p className="text-[10px] text-yellow-400">{warning}</p>}
        </div>
      )
    
    case 'range':
      return (
        <div className="space-y-1">
          <div className="flex justify-between items-center">
            <label className="text-xs text-gray-400">{knob.label}</label>
            <span className="text-xs text-white font-mono">
              {typeof currentValue === 'number' ? currentValue.toFixed(2) : currentValue}
            </span>
          </div>
          <input
            type="range"
            min={knob.min_value ?? 0}
            max={knob.max_value ?? 1}
            step={knob.step ?? 0.01}
            value={currentValue}
            onChange={(e) => onChange(parseFloat(e.target.value))}
            className="w-full accent-blue-500"
          />
          <p className="text-[10px] text-gray-600">{knob.description}</p>
          {error && <p className="text-[10px] text-red-400">{error}</p>}
          {warning && <p className="text-[10px] text-yellow-400">{warning}</p>}
        </div>
      )
    
    case 'number':
      return (
        <div className="space-y-1">
          <label className="text-xs text-gray-400">{knob.label}</label>
          <input
            type="number"
            min={knob.min_value}
            max={knob.max_value}
            step={knob.step ?? 1}
            value={currentValue}
            onChange={(e) => onChange(parseInt(e.target.value, 10))}
            className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
          />
          <p className="text-[10px] text-gray-600">{knob.description}</p>
          {error && <p className="text-[10px] text-red-400">{error}</p>}
          {warning && <p className="text-[10px] text-yellow-400">{warning}</p>}
        </div>
      )
    
    case 'boolean':
      return (
        <div className="flex items-center justify-between py-2">
          <div>
            <label className="text-sm text-white">{knob.label}</label>
            <p className="text-[10px] text-gray-600">{knob.description}</p>
          </div>
          <button
            onClick={() => onChange(!currentValue)}
            className={`w-10 h-5 rounded-full transition-colors ${
              currentValue ? 'bg-blue-500' : 'bg-gray-700'
            }`}
          >
            <div className={`w-4 h-4 rounded-full bg-white transition-transform ${
              currentValue ? 'translate-x-5' : 'translate-x-0.5'
            }`} />
          </button>
        </div>
      )
    
    default:
      return (
        <div className="space-y-1">
          <label className="text-xs text-gray-400">{knob.label}</label>
          <input
            type="text"
            value={currentValue}
            onChange={(e) => onChange(e.target.value)}
            className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
          />
          <p className="text-[10px] text-gray-600">{knob.description}</p>
        </div>
      )
  }
}

export const PolicySettings: FC<PolicySettingsProps> = ({ criteriaId, onSave }) => {
  const [schema, setSchema] = useState<ConfigSchema | null>(null)
  const [settings, setSettings] = useState<FusionSettings>({})
  const [originalSettings, setOriginalSettings] = useState<FusionSettings>({})
  const [validation, setValidation] = useState<ConfigValidationResult | null>(null)
  const [preview, setPreview] = useState<ConfigPreview[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [showPreview, setShowPreview] = useState(false)
  
  // Load schema and current config
  useEffect(() => {
    const load = async () => {
      try {
        const [schemaData, configData] = await Promise.all([
          configApi.getSchema(),
          configApi.getCriteriaConfig(criteriaId),
        ])
        setSchema(schemaData)
        setSettings(configData.fusion_settings || {})
        setOriginalSettings(configData.fusion_settings || {})
      } catch (err) {
        console.error('Failed to load config:', err)
        toast.error('Failed to load configuration')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [criteriaId])
  
  // Validate on settings change
  useEffect(() => {
    const validate = async () => {
      if (Object.keys(settings).length === 0) return
      try {
        const result = await configApi.validateFusion(settings)
        setValidation(result)
      } catch (err) {
        console.error('Validation failed:', err)
      }
    }
    const timeout = setTimeout(validate, 300)
    return () => clearTimeout(timeout)
  }, [settings])
  
  // Calculate if there are changes
  const hasChanges = useMemo(() => {
    return JSON.stringify(settings) !== JSON.stringify(originalSettings)
  }, [settings, originalSettings])
  
  // Group knobs by category
  const groupedKnobs = useMemo(() => {
    if (!schema) return { basic: [], advanced: [] }
    return {
      basic: schema.fusion_knobs.filter(k => k.level === 'basic'),
      advanced: schema.fusion_knobs.filter(k => k.level === 'advanced'),
    }
  }, [schema])
  
  // Handle setting change
  const handleChange = useCallback((knobId: string, value: any) => {
    setSettings(prev => ({ ...prev, [knobId]: value }))
  }, [])
  
  // Preview changes
  const handlePreview = useCallback(async () => {
    try {
      const result = await configApi.previewChanges(criteriaId, { fusion_settings: settings })
      setPreview(result.changes)
      setShowPreview(true)
    } catch (err) {
      console.error('Preview failed:', err)
      toast.error('Failed to preview changes')
    }
  }, [criteriaId, settings])
  
  // Save changes
  const handleSave = useCallback(async () => {
    if (!validation?.valid) {
      toast.error('Please fix validation errors before saving')
      return
    }
    
    setSaving(true)
    try {
      await configApi.updateCriteriaConfig(criteriaId, {
        fusion_settings: settings,
        change_summary: 'Updated fusion settings from UI',
      })
      setOriginalSettings(settings)
      toast.success('Settings saved')
      onSave?.()
    } catch (err: any) {
      console.error('Save failed:', err)
      toast.error(err.response?.data?.detail?.message || 'Failed to save settings')
    } finally {
      setSaving(false)
    }
  }, [criteriaId, settings, validation, onSave])
  
  // Reset to defaults
  const handleReset = useCallback(async () => {
    try {
      await configApi.resetToDefaults(criteriaId)
      // Reload config
      const configData = await configApi.getCriteriaConfig(criteriaId)
      setSettings(configData.fusion_settings || {})
      setOriginalSettings(configData.fusion_settings || {})
      toast.success('Reset to defaults')
    } catch (err) {
      console.error('Reset failed:', err)
      toast.error('Failed to reset')
    }
  }, [criteriaId])
  
  // Get error/warning for a knob
  const getKnobError = (knobId: string) => {
    return validation?.errors.find(e => e.field === knobId)?.message
  }
  const getKnobWarning = (knobId: string) => {
    return validation?.warnings.find(w => w.field === knobId)?.message
  }
  
  if (loading) {
    return (
      <div className="p-4 text-center text-gray-500">
        Loading configuration...
      </div>
    )
  }
  
  if (!schema) {
    return (
      <div className="p-4 text-center text-gray-500">
        Failed to load configuration schema
      </div>
    )
  }
  
  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium text-white">Policy Settings</h3>
          <p className="text-[10px] text-gray-500">Configure verdict strategy and scoring behavior</p>
        </div>
        {hasChanges && (
          <span className="text-[10px] text-yellow-400 flex items-center gap-1">
            <AlertTriangle size={10} />
            Unsaved changes
          </span>
        )}
      </div>
      
      {/* Validation Status */}
      {validation && !validation.valid && (
        <div className="p-2 bg-red-900/20 border border-red-900/50 rounded text-xs text-red-400">
          {validation.errors.map((e, i) => (
            <div key={i}>{e.field}: {e.message}</div>
          ))}
        </div>
      )}
      {validation?.warnings && validation.warnings.length > 0 && (
        <div className="p-2 bg-yellow-900/20 border border-yellow-900/50 rounded text-xs text-yellow-400">
          {validation.warnings.map((w, i) => (
            <div key={i} className="flex items-start gap-1">
              <Info size={10} className="mt-0.5 flex-shrink-0" />
              {w.message}
            </div>
          ))}
        </div>
      )}
      
      {/* Basic Settings */}
      <div className="space-y-3">
        {groupedKnobs.basic.map(knob => (
          <KnobControl
            key={knob.id}
            knob={knob}
            value={settings[knob.id as keyof FusionSettings]}
            onChange={(val) => handleChange(knob.id, val)}
            error={getKnobError(knob.id)}
            warning={getKnobWarning(knob.id)}
          />
        ))}
      </div>
      
      {/* Advanced Settings Toggle */}
      {groupedKnobs.advanced.length > 0 && (
        <div className="border-t border-gray-800 pt-3">
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center gap-2 text-xs text-gray-400 hover:text-white"
          >
            {showAdvanced ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            Advanced Settings
          </button>
          
          {showAdvanced && (
            <div className="mt-3 space-y-3 pl-2 border-l border-gray-800">
              {groupedKnobs.advanced.map(knob => (
                <KnobControl
                  key={knob.id}
                  knob={knob}
                  value={settings[knob.id as keyof FusionSettings]}
                  onChange={(val) => handleChange(knob.id, val)}
                  error={getKnobError(knob.id)}
                  warning={getKnobWarning(knob.id)}
                />
              ))}
            </div>
          )}
        </div>
      )}
      
      {/* Preview Modal */}
      {showPreview && preview.length > 0 && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-4 max-w-md w-full mx-4">
            <h4 className="text-sm font-medium text-white mb-3">Preview Changes</h4>
            <div className="space-y-2 max-h-60 overflow-y-auto">
              {preview.map((change, i) => (
                <div key={i} className="flex justify-between text-xs py-1 border-b border-gray-800">
                  <span className="text-gray-400">{change.label}</span>
                  <div className="text-right">
                    <span className="text-red-400 line-through mr-2">{String(change.current_value)}</span>
                    <span className="text-green-400">{String(change.new_value)}</span>
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setShowPreview(false)}
                className="px-3 py-1.5 text-xs text-gray-400 hover:text-white"
              >
                Close
              </button>
              <button
                onClick={() => { setShowPreview(false); handleSave(); }}
                className="px-3 py-1.5 text-xs bg-blue-600 hover:bg-blue-500 text-white rounded"
              >
                Confirm & Save
              </button>
            </div>
          </div>
        </div>
      )}
      
      {/* Action Buttons */}
      <div className="flex items-center justify-between pt-3 border-t border-gray-800">
        <button
          onClick={handleReset}
          className="flex items-center gap-1 text-xs text-gray-400 hover:text-white"
        >
          <RotateCcw size={12} />
          Reset to Defaults
        </button>
        
        <div className="flex items-center gap-2">
          <button
            onClick={handlePreview}
            disabled={!hasChanges}
            className="flex items-center gap-1 px-3 py-1.5 text-xs text-gray-400 hover:text-white disabled:opacity-50"
          >
            <Eye size={12} />
            Preview
          </button>
          <button
            onClick={handleSave}
            disabled={!hasChanges || !validation?.valid || saving}
            className="flex items-center gap-1 px-3 py-1.5 text-xs bg-blue-600 hover:bg-blue-500 text-white rounded disabled:opacity-50"
          >
            {saving ? (
              <>Saving...</>
            ) : (
              <>
                <Save size={12} />
                Save Changes
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}

export default PolicySettings
