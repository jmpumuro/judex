/**
 * StageSettings - Advanced Stage/Model Knobs Panel
 * 
 * Industry Standard: Schema-driven UI rendering for per-stage configuration.
 * Only exposes safe, bounded parameters - no raw model internals.
 */
import { FC, useState, useEffect, useMemo, useCallback } from 'react'
import { 
  ChevronDown, ChevronRight, AlertTriangle, 
  Save, RotateCcw, Settings2,
  // Stage icons
  Crosshair, Search, Flame, Zap, Film, 
  Activity, ShieldAlert, Mic, FileText, Filter,
  LucideIcon
} from 'lucide-react'
import { 
  configApi, 
  ConfigKnob, 
  StageKnobs, 
  ConfigValidationResult,
} from '@/api/endpoints'
import toast from 'react-hot-toast'

interface StageSettingsProps {
  criteriaId: string
  activeStages: string[]  // Currently used stages in the pipeline
  onSave?: () => void
}

// Render a knob control
const KnobControl: FC<{
  knob: ConfigKnob
  value: any
  onChange: (value: any) => void
  error?: string
}> = ({ knob, value, onChange, error }) => {
  const currentValue = value ?? knob.default
  
  switch (knob.type) {
    case 'enum':
      return (
        <div className="flex items-center justify-between py-1.5">
          <div className="flex-1">
            <span className="text-xs text-gray-400">{knob.label}</span>
            <p className="text-[9px] text-gray-600">{knob.description}</p>
          </div>
          <select
            value={currentValue}
            onChange={(e) => onChange(e.target.value)}
            className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-white focus:border-blue-500 focus:outline-none"
          >
            {knob.options?.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      )
    
    case 'range':
      return (
        <div className="py-1.5">
          <div className="flex justify-between items-center mb-1">
            <span className="text-xs text-gray-400">{knob.label}</span>
            <span className="text-xs text-white font-mono bg-gray-800 px-1.5 py-0.5 rounded">
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
            className="w-full accent-purple-500 h-1"
          />
          <p className="text-[9px] text-gray-600 mt-0.5">{knob.description}</p>
          {error && <p className="text-[9px] text-red-400">{error}</p>}
        </div>
      )
    
    case 'number':
      return (
        <div className="flex items-center justify-between py-1.5">
          <div className="flex-1">
            <span className="text-xs text-gray-400">{knob.label}</span>
            <p className="text-[9px] text-gray-600">{knob.description}</p>
          </div>
          <input
            type="number"
            min={knob.min_value}
            max={knob.max_value}
            step={knob.step ?? 1}
            value={currentValue}
            onChange={(e) => onChange(parseInt(e.target.value, 10))}
            className="w-20 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-white text-right focus:border-purple-500 focus:outline-none"
          />
        </div>
      )
    
    case 'string_list':
      return (
        <div className="py-1.5">
          <span className="text-xs text-gray-400">{knob.label}</span>
          <input
            type="text"
            value={Array.isArray(currentValue) ? currentValue.join(', ') : ''}
            onChange={(e) => onChange(e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
            placeholder="Enter comma-separated values"
            className="w-full mt-1 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-white focus:border-purple-500 focus:outline-none"
          />
          <p className="text-[9px] text-gray-600 mt-0.5">{knob.description}</p>
        </div>
      )
    
    default:
      return null
  }
}

// Stage card component with icons and descriptions
const StageCard: FC<{
  stageType: string
  stageName: string
  knobs: ConfigKnob[]
  values: StageKnobs
  onChange: (values: StageKnobs) => void
  validation?: ConfigValidationResult
}> = ({ stageType, stageName, knobs, values, onChange, validation }) => {
  const [expanded, setExpanded] = useState(false)
  
  // Filter knobs supported by this stage
  const supportedKnobs = useMemo(() => {
    return knobs.filter(k => !k.stage_types || k.stage_types.includes(stageType))
  }, [knobs, stageType])
  
  const handleKnobChange = (knobId: string, value: any) => {
    onChange({ ...values, [knobId]: value })
  }
  
  const hasOverrides = Object.keys(values).length > 0
  const StageIcon = STAGE_ICONS[stageType] || Settings2
  const stageDescription = STAGE_DESCRIPTIONS[stageType] || ''
  
  return (
    <div className="border border-gray-800 rounded-lg overflow-hidden hover:border-gray-700 transition-colors">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-3 py-2.5 bg-gray-900/50 hover:bg-gray-900 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center">
            <StageIcon size={16} className="text-purple-400" />
          </div>
          <div className="text-left">
            <div className="flex items-center gap-2">
              {expanded ? <ChevronDown size={12} className="text-gray-500" /> : <ChevronRight size={12} className="text-gray-500" />}
              <span className="text-sm text-white font-medium">{stageName}</span>
              {hasOverrides && (
                <span className="px-1.5 py-0.5 bg-purple-900/50 text-purple-400 text-[9px] rounded-full">
                  customized
                </span>
              )}
            </div>
            {!expanded && stageDescription && (
              <p className="text-[10px] text-gray-500 mt-0.5 ml-5">{stageDescription}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {supportedKnobs.length > 0 && (
            <span className="text-[9px] text-gray-600">{supportedKnobs.length} settings</span>
          )}
          <Settings2 size={12} className="text-gray-600" />
        </div>
      </button>
      
      {expanded && (
        <div className="px-3 py-3 space-y-2 border-t border-gray-800 bg-gray-950/50">
          {stageDescription && (
            <p className="text-[10px] text-gray-500 pb-2 border-b border-gray-800/50">{stageDescription}</p>
          )}
          {supportedKnobs.length === 0 ? (
            <p className="text-xs text-gray-500 italic py-2">No configurable settings for this stage</p>
          ) : (
            supportedKnobs.map(knob => (
              <KnobControl
                key={knob.id}
                knob={knob}
                value={values[knob.id as keyof StageKnobs]}
                onChange={(val) => handleKnobChange(knob.id, val)}
                error={validation?.errors.find(e => e.field === knob.id)?.message}
              />
            ))
          )}
          
          {hasOverrides && (
            <button
              onClick={() => onChange({})}
              className="text-[10px] text-gray-500 hover:text-white mt-2 flex items-center gap-1"
            >
              <RotateCcw size={10} />
              Clear overrides
            </button>
          )}
        </div>
      )}
    </div>
  )
}

// Stage name mappings for display - includes all pipeline models
const STAGE_NAMES: Record<string, string> = {
  // Object Detection
  yolo26: 'Object Detection (YOLO26)',
  yoloworld: 'Threat Scanning (YOLO-World)',
  
  // Violence Detection Stack
  window_mining: 'Hotspot Mining',
  violence: 'Action Analysis (X-CLIP)',
  xclip: 'Action Analysis (X-CLIP)',
  videomae_violence: 'Violence Detection (VideoMAE)',
  pose_heuristics: 'Body Language Analysis',
  
  // Content Moderation
  nsfw_detection: 'Adult Content Detection',
  whisper: 'Speech Transcription (Whisper)',
  ocr: 'Text Recognition (OCR)',
  text_moderation: 'Language Filter',
}

// Stage descriptions for tooltips
const STAGE_DESCRIPTIONS: Record<string, string> = {
  yolo26: 'Detects objects like weapons, people, and items in video frames',
  yoloworld: 'Open-vocabulary scanning for threats and suspicious items',
  window_mining: 'Identifies suspicious segments with motion and person interactions',
  violence: 'Analyzes video actions to detect violent behavior patterns',
  xclip: 'Analyzes video actions to detect violent behavior patterns',
  videomae_violence: 'Specialist transformer model for violence recognition',
  pose_heuristics: 'Analyzes body poses to detect physical interactions',
  nsfw_detection: 'Detects visual adult/sexual content in frames',
  whisper: 'Transcribes speech to text for content analysis',
  ocr: 'Extracts on-screen text from video frames',
  text_moderation: 'Filters harmful language in speech and text',
}

// Stage icons for visual identification - using Lucide icons
const STAGE_ICONS: Record<string, LucideIcon> = {
  yolo26: Crosshair,
  yoloworld: Search,
  window_mining: Flame,
  violence: Zap,
  xclip: Zap,
  videomae_violence: Film,
  pose_heuristics: Activity,
  nsfw_detection: ShieldAlert,
  whisper: Mic,
  ocr: FileText,
  text_moderation: Filter,
}

export const StageSettings: FC<StageSettingsProps> = ({ 
  criteriaId, 
  activeStages,
  onSave 
}) => {
  const [knobs, setKnobs] = useState<ConfigKnob[]>([])
  const [supportedStages, setSupportedStages] = useState<string[]>([])
  const [overrides, setOverrides] = useState<Record<string, StageKnobs>>({})
  const [originalOverrides, setOriginalOverrides] = useState<Record<string, StageKnobs>>({})
  const [validations, setValidations] = useState<Record<string, ConfigValidationResult>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  
  // Load schema and current config
  useEffect(() => {
    const load = async () => {
      try {
        const [schemaData, configData] = await Promise.all([
          configApi.getStageSchema(),
          configApi.getCriteriaConfig(criteriaId),
        ])
        setKnobs(schemaData.knobs)
        setSupportedStages(schemaData.supported_stages)
        setOverrides(configData.stage_overrides || {})
        setOriginalOverrides(configData.stage_overrides || {})
      } catch (err) {
        console.error('Failed to load stage config:', err)
        toast.error('Failed to load stage settings')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [criteriaId])
  
  // Validate overrides when they change
  useEffect(() => {
    const validate = async () => {
      const newValidations: Record<string, ConfigValidationResult> = {}
      for (const [stageType, stageKnobs] of Object.entries(overrides)) {
        if (Object.keys(stageKnobs).length > 0) {
          try {
            const result = await configApi.validateStage(stageType, stageKnobs)
            newValidations[stageType] = result
          } catch (err) {
            console.error(`Validation failed for ${stageType}:`, err)
          }
        }
      }
      setValidations(newValidations)
    }
    const timeout = setTimeout(validate, 300)
    return () => clearTimeout(timeout)
  }, [overrides])
  
  // Calculate changes
  const hasChanges = useMemo(() => {
    return JSON.stringify(overrides) !== JSON.stringify(originalOverrides)
  }, [overrides, originalOverrides])
  
  // Filter to show only active stages that support knobs
  const configurableStages = useMemo(() => {
    return activeStages.filter(s => supportedStages.includes(s))
  }, [activeStages, supportedStages])
  
  // Handle override change for a stage
  const handleStageChange = useCallback((stageType: string, values: StageKnobs) => {
    setOverrides(prev => ({
      ...prev,
      [stageType]: values,
    }))
  }, [])
  
  // Save changes
  const handleSave = useCallback(async () => {
    // Check all validations pass
    const hasErrors = Object.values(validations).some(v => !v.valid)
    if (hasErrors) {
      toast.error('Please fix validation errors before saving')
      return
    }
    
    setSaving(true)
    try {
      await configApi.updateCriteriaConfig(criteriaId, {
        stage_overrides: overrides,
        change_summary: 'Updated stage settings from UI',
      })
      setOriginalOverrides(overrides)
      toast.success('Stage settings saved')
      onSave?.()
    } catch (err: any) {
      console.error('Save failed:', err)
      toast.error(err.response?.data?.detail?.message || 'Failed to save settings')
    } finally {
      setSaving(false)
    }
  }, [criteriaId, overrides, validations, onSave])
  
  // Reset all overrides
  const handleReset = useCallback(() => {
    setOverrides({})
  }, [])
  
  if (loading) {
    return (
      <div className="p-4 text-center text-gray-500">
        Loading stage settings...
      </div>
    )
  }
  
  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium text-white">Stage Settings</h3>
          <p className="text-[10px] text-gray-500">Fine-tune detection sensitivity and behavior per stage</p>
        </div>
        {hasChanges && (
          <span className="text-[10px] text-yellow-400 flex items-center gap-1">
            <AlertTriangle size={10} />
            Unsaved changes
          </span>
        )}
      </div>
      
      {/* Info Banner */}
      <div className="p-2 bg-purple-900/10 border border-purple-900/30 rounded text-[10px] text-purple-300">
        These settings override the default behavior for each stage. 
        Leave empty to use preset defaults.
      </div>
      
      {/* Stage Cards */}
      {configurableStages.length === 0 ? (
        <div className="text-center py-4 text-gray-500 text-sm">
          No configurable stages in current pipeline
        </div>
      ) : (
        <div className="space-y-2">
          {configurableStages.map(stageType => (
            <StageCard
              key={stageType}
              stageType={stageType}
              stageName={STAGE_NAMES[stageType] || stageType}
              knobs={knobs}
              values={overrides[stageType] || {}}
              onChange={(values) => handleStageChange(stageType, values)}
              validation={validations[stageType]}
            />
          ))}
        </div>
      )}
      
      {/* Action Buttons */}
      <div className="flex items-center justify-between pt-3 border-t border-gray-800">
        <button
          onClick={handleReset}
          disabled={Object.keys(overrides).length === 0}
          className="flex items-center gap-1 text-xs text-gray-400 hover:text-white disabled:opacity-50"
        >
          <RotateCcw size={12} />
          Clear All Overrides
        </button>
        
        <button
          onClick={handleSave}
          disabled={!hasChanges || saving}
          className="flex items-center gap-1 px-3 py-1.5 text-xs bg-purple-600 hover:bg-purple-500 text-white rounded disabled:opacity-50"
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
  )
}

export default StageSettings
