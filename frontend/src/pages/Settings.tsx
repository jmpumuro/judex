import { FC, useEffect, useState, useCallback } from 'react'
import { 
  Settings as SettingsIcon, Check, AlertCircle, ChevronDown, ChevronRight,
  Shield, Eye, FileText, Zap, Info, RefreshCw, Upload, Download, Copy,
  Trash2, Plus, Save, Edit3, Code, Sliders, ExternalLink, Play, X,
  CheckCircle, XCircle, Terminal, Power, Lock
} from 'lucide-react'
import { api, stagesApi, ExternalStageConfig, StageInfo, ValidationResult, ToggleStageResponse } from '@/api/endpoints'
import toast from 'react-hot-toast'

interface Preset {
  id: string
  name: string
  description?: string
  criteria_count: number
}

interface CriterionDetail {
  id: string
  label: string
  description?: string
  severity: string
  enabled: boolean
  thresholds: {
    safe: number
    caution: number
    unsafe: number
  }
}

interface CriteriaDetail {
  name: string
  description?: string
  criteria: CriterionDetail[]
  options: {
    generate_report: boolean
    generate_labeled_video: boolean
    explain_verdict: boolean
    max_violations: number
  }
  detectors_required: string[]
}

interface EditableCriterion {
  id: string
  label: string
  description: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  enabled: boolean
  thresholds: {
    safe: number
    caution: number
    unsafe: number
  }
}

interface EditableCriteria {
  name: string
  description: string
  criteria: Record<string, EditableCriterion>
  options: {
    generate_report: boolean
    generate_labeled_video: boolean
    explain_verdict: boolean
  }
}

const SEVERITY_OPTIONS = ['low', 'medium', 'high', 'critical'] as const
const SEVERITY_COLORS: Record<string, string> = {
  low: 'bg-blue-900/30 text-blue-400 border-blue-700',
  medium: 'bg-yellow-900/30 text-yellow-400 border-yellow-700',
  high: 'bg-orange-900/30 text-orange-400 border-orange-700',
  critical: 'bg-red-900/30 text-red-400 border-red-700',
}

// Example YAML template for external stages
const EXAMPLE_YAML = `version: v1
stages:
  - id: customer_policy
    name: "Customer Policy (External)"
    type: external_stage
    endpoint:
      url: "https://your-api.example.com/analyze"
      auth:
        type: bearer
        token: "\${CUSTOMER_API_TOKEN}"
    timeout_ms: 5000
    retries: 2
    input_mapping:
      vision_data: "$.vision_detections"
      transcript: "$.transcript.full_text"
      video_id: "$.video_id"
    output_mapping:
      customer_verdict: "$.verdict"
      customer_evidence: "$.evidence"
`

// Settings page tabs
type SettingsTab = 'criteria' | 'stages' | 'stage-config'

const Settings: FC = () => {
  const [activeTab, setActiveTab] = useState<SettingsTab>('criteria')
  
  // Criteria state
  const [presets, setPresets] = useState<Preset[]>([])
  const [customCriteria, setCustomCriteria] = useState<Preset[]>([])
  const [selectedId, setSelectedId] = useState<string>('child_safety')
  const [selectedType, setSelectedType] = useState<'preset' | 'custom'>('preset')
  const [isLoading, setIsLoading] = useState(true)
  const [editMode, setEditMode] = useState(false)
  const [editData, setEditData] = useState<EditableCriteria | null>(null)
  const [showYamlView, setShowYamlView] = useState(false)
  const [yamlContent, setYamlContent] = useState('')
  const [saveName, setSaveName] = useState('')
  const [hasChanges, setHasChanges] = useState(false)
  const [detectors, setDetectors] = useState<string[]>([])

  // Stages state
  const [allStages, setAllStages] = useState<StageInfo[]>([])
  const [externalConfigs, setExternalConfigs] = useState<ExternalStageConfig[]>([])
  const [selectedConfigId, setSelectedConfigId] = useState<string | null>(null)
  const [stageYaml, setStageYaml] = useState('')
  const [stageName, setStageName] = useState('')
  const [stageConfigId, setStageConfigId] = useState('')
  const [stageDescription, setStageDescription] = useState('')
  const [stageValidation, setStageValidation] = useState<ValidationResult | null>(null)
  const [isValidating, setIsValidating] = useState(false)
  const [isSavingStage, setIsSavingStage] = useState(false)
  const [togglingStage, setTogglingStage] = useState<string | null>(null)

  // Load data on mount
  useEffect(() => {
    loadData()
    loadStages()
  }, [])

  const loadData = async () => {
    setIsLoading(true)
    try {
      const [presetsRes, customRes] = await Promise.all([
        api.get('/criteria/presets'),
        api.get('/criteria/custom')
      ])
      setPresets(presetsRes.data || [])
      setCustomCriteria(customRes.data || [])
      
      if (presetsRes.data?.length > 0) {
        loadPreset(presetsRes.data[0].id, 'preset')
      }
    } catch (error) {
      console.error('Failed to load criteria:', error)
      toast.error('Failed to load criteria')
    }
    setIsLoading(false)
  }

  const loadStages = async () => {
    try {
      const [stagesRes, externalRes] = await Promise.all([
        stagesApi.list(),
        stagesApi.listExternal()
      ])
      setAllStages(stagesRes.stages || [])
      setExternalConfigs(externalRes || [])
    } catch (error) {
      console.error('Failed to load stages:', error)
    }
  }

  const loadPreset = async (id: string, type: 'preset' | 'custom') => {
    setSelectedId(id)
    setSelectedType(type)
    setEditMode(false)
    setHasChanges(false)
    
    try {
      const endpoint = type === 'preset' ? `/criteria/presets/${id}` : `/criteria/custom/${id}`
      const { data } = await api.get<CriteriaDetail>(endpoint)
      
      const editable: EditableCriteria = {
        name: data.name,
        description: data.description || '',
        criteria: {},
        options: {
          generate_report: data.options.generate_report,
          generate_labeled_video: data.options.generate_labeled_video,
          explain_verdict: data.options.explain_verdict,
        }
      }
      
      data.criteria.forEach(c => {
        editable.criteria[c.id] = {
          id: c.id,
          label: c.label,
          description: c.description || '',
          severity: c.severity as any,
          enabled: c.enabled,
          thresholds: { ...c.thresholds }
        }
      })
      
      setEditData(editable)
      setDetectors(data.detectors_required)
      setSaveName(type === 'custom' ? id : '')
      
      try {
        const exportEndpoint = type === 'preset' 
          ? `/criteria/presets/${id}/export?format=yaml`
          : `/criteria/custom/${id}/export?format=yaml`
        const yamlRes = await api.get(exportEndpoint)
        setYamlContent(yamlRes.data.content || yamlRes.data)
      } catch {
        console.log('YAML export not available for', id)
      }
    } catch (error) {
      console.error('Failed to load preset:', error)
      toast.error('Failed to load preset')
    }
  }

  const updateCriterion = (criterionId: string, field: string, value: any) => {
    if (!editData) return
    
    setEditData(prev => {
      if (!prev) return prev
      const updated = { ...prev }
      if (field.startsWith('thresholds.')) {
        const thresholdKey = field.split('.')[1] as 'safe' | 'caution' | 'unsafe'
        updated.criteria[criterionId] = {
          ...updated.criteria[criterionId],
          thresholds: {
            ...updated.criteria[criterionId].thresholds,
            [thresholdKey]: value
          }
        }
      } else {
        updated.criteria[criterionId] = {
          ...updated.criteria[criterionId],
          [field]: value
        }
      }
      return updated
    })
    setHasChanges(true)
  }

  const addCriterion = () => {
    if (!editData) return
    
    const newId = `criterion_${Date.now()}`
    setEditData(prev => {
      if (!prev) return prev
      return {
        ...prev,
        criteria: {
          ...prev.criteria,
          [newId]: {
            id: newId,
            label: 'New Criterion',
            description: '',
            severity: 'medium',
            enabled: true,
            thresholds: { safe: 0.3, caution: 0.6, unsafe: 0.7 }
          }
        }
      }
    })
    setHasChanges(true)
  }

  const removeCriterion = (criterionId: string) => {
    if (!editData) return
    
    setEditData(prev => {
      if (!prev) return prev
      const { [criterionId]: removed, ...rest } = prev.criteria
      return { ...prev, criteria: rest }
    })
    setHasChanges(true)
  }

  const updateOptions = (field: string, value: any) => {
    if (!editData) return
    
    setEditData(prev => {
      if (!prev) return prev
      return {
        ...prev,
        [field.includes('.') ? field.split('.')[0] : field]: 
          field.includes('.') 
            ? { ...prev.options, [field.split('.')[1]]: value }
            : value
      }
    })
    setHasChanges(true)
  }

  const saveAsCustom = async () => {
    if (!editData || !saveName.trim()) {
      toast.error('Please enter a name')
      return
    }
    
    const yamlData = {
      name: editData.name,
      version: '1.0',
      description: editData.description,
      criteria: Object.fromEntries(
        Object.entries(editData.criteria).map(([id, c]) => [
          id,
          {
            label: c.label,
            description: c.description,
            severity: c.severity,
            enabled: c.enabled,
            thresholds: c.thresholds
          }
        ])
      ),
      options: editData.options
    }
    
    try {
      const yaml = `name: ${yamlData.name}
version: "1.0"
description: ${yamlData.description || ''}

criteria:
${Object.entries(yamlData.criteria).map(([id, c]: [string, any]) => `  ${id}:
    label: ${c.label}
    description: ${c.description || ''}
    severity: ${c.severity}
    enabled: ${c.enabled}
    thresholds:
      safe: ${c.thresholds.safe}
      caution: ${c.thresholds.caution}
      unsafe: ${c.thresholds.unsafe}`).join('\n')}

options:
  generate_report: ${yamlData.options.generate_report}
  generate_labeled_video: ${yamlData.options.generate_labeled_video}
  explain_verdict: ${yamlData.options.explain_verdict}
`
      
      const blob = new Blob([yaml], { type: 'text/yaml' })
      const formData = new FormData()
      formData.append('file', blob, `${saveName}.yaml`)
      formData.append('save_as', saveName.trim().toLowerCase().replace(/\s+/g, '_'))
      
      const { data } = await api.post('/criteria/upload', formData)
      
      if (data.status === 'valid') {
        toast.success(`Saved as "${data.saved_as}"`)
        setHasChanges(false)
        setEditMode(false)
        loadData()
        setTimeout(() => loadPreset(data.saved_as, 'custom'), 500)
      }
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to save')
    }
  }

  const deleteCustom = async (id: string) => {
    if (!confirm(`Delete "${id}"?`)) return
    
    try {
      await api.delete(`/criteria/custom/${id}`)
      toast.success('Deleted')
      loadData()
      if (presets.length > 0) {
        loadPreset(presets[0].id, 'preset')
      }
    } catch {
      toast.error('Failed to delete')
    }
  }

  // ===== EXTERNAL STAGES FUNCTIONS =====

  const validateStageYaml = useCallback(async (yaml: string) => {
    if (!yaml.trim()) {
      setStageValidation(null)
      return
    }
    
    setIsValidating(true)
    try {
      const result = await stagesApi.validateYaml(yaml)
      setStageValidation(result)
    } catch (error) {
      setStageValidation({ valid: false, error: 'Validation request failed', stages: [] })
    }
    setIsValidating(false)
  }, [])

  // Debounced validation
  useEffect(() => {
    const timer = setTimeout(() => {
      if (stageYaml) validateStageYaml(stageYaml)
    }, 500)
    return () => clearTimeout(timer)
  }, [stageYaml, validateStageYaml])

  const loadExternalConfig = (config: ExternalStageConfig) => {
    setSelectedConfigId(config.id)
    setStageConfigId(config.id)
    setStageName(config.name)
    setStageDescription(config.description || '')
    setStageYaml(config.yaml_content)
    setStageValidation({
      valid: config.validated,
      error: config.validation_error,
      stages: config.stage_ids.map(id => ({ id, name: id, endpoint: '' }))
    })
  }

  const createNewStageConfig = () => {
    setSelectedConfigId(null)
    setStageConfigId('')
    setStageName('')
    setStageDescription('')
    setStageYaml(EXAMPLE_YAML)
    setStageValidation(null)
  }

  const saveExternalConfig = async () => {
    if (!stageConfigId.trim() || !stageName.trim() || !stageYaml.trim()) {
      toast.error('Please fill in all required fields')
      return
    }
    
    if (!stageValidation?.valid) {
      toast.error('Please fix validation errors before saving')
      return
    }
    
    setIsSavingStage(true)
    try {
      await stagesApi.createExternal({
        id: stageConfigId.toLowerCase().replace(/\s+/g, '_'),
        name: stageName,
        description: stageDescription,
        yaml_content: stageYaml,
        enabled: true
      })
      toast.success('External stage saved and registered')
      loadStages()
      setSelectedConfigId(stageConfigId)
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to save')
    }
    setIsSavingStage(false)
  }

  const deleteExternalConfig = async (configId: string) => {
    if (!confirm(`Delete external stage "${configId}"?`)) return
    
    try {
      await stagesApi.deleteExternal(configId)
      toast.success('Deleted')
      loadStages()
      if (selectedConfigId === configId) {
        createNewStageConfig()
      }
    } catch {
      toast.error('Failed to delete')
    }
  }

  const toggleExternalConfig = async (configId: string, enabled: boolean) => {
    try {
      await stagesApi.toggleExternal(configId, enabled)
      toast.success(enabled ? 'Stage enabled' : 'Stage disabled')
      loadStages()
    } catch {
      toast.error('Failed to toggle')
    }
  }

  const toggleStage = async (stageId: string, enabled: boolean) => {
    setTogglingStage(stageId)
    try {
      const result = await stagesApi.toggleStage(stageId, enabled)
      
      if (result.warning) {
        toast(result.warning, { icon: '⚠️', duration: 5000 })
      }
      
      toast.success(
        enabled 
          ? `${stageId} enabled` 
          : `${stageId} disabled - will be skipped in evaluations`
      )
      loadStages()
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Failed to toggle stage'
      toast.error(message)
    }
    setTogglingStage(null)
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
      {/* Header with tabs */}
      <div className="px-6 py-4 border-b border-gray-800 flex-shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-6">
            <div>
              <span className="text-xs text-gray-500 tracking-widest">SETTINGS</span>
            </div>
            <div className="flex border border-gray-800 rounded overflow-hidden">
              <button
                onClick={() => setActiveTab('criteria')}
                className={`px-4 py-1.5 text-xs transition-colors ${
                  activeTab === 'criteria' 
                    ? 'bg-white text-black' 
                    : 'hover:bg-gray-900'
                }`}
              >
                <Shield size={12} className="inline mr-1.5" />
                Criteria
              </button>
              <button
                onClick={() => setActiveTab('stages')}
                className={`px-4 py-1.5 text-xs transition-colors ${
                  activeTab === 'stages' 
                    ? 'bg-white text-black' 
                    : 'hover:bg-gray-900'
                }`}
              >
                <Power size={12} className="inline mr-1.5" />
                Stages
              </button>
              <button
                onClick={() => setActiveTab('stage-config')}
                className={`px-4 py-1.5 text-xs transition-colors ${
                  activeTab === 'stage-config' 
                    ? 'bg-white text-black' 
                    : 'hover:bg-gray-900'
                }`}
              >
                <ExternalLink size={12} className="inline mr-1.5" />
                External Config
              </button>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {activeTab === 'criteria' && editMode && hasChanges && (
              <span className="text-[10px] text-yellow-500">• Unsaved changes</span>
            )}
            <button 
              onClick={() => { loadData(); loadStages() }}
              className="p-2 text-gray-500 hover:text-white transition-colors"
              title="Refresh"
            >
              <RefreshCw size={16} />
            </button>
          </div>
        </div>
      </div>

      {/* CRITERIA TAB */}
      {activeTab === 'criteria' && (
        <div className="flex-1 flex overflow-hidden">
          {/* Sidebar */}
          <div className="w-56 border-r border-gray-800 flex-shrink-0 overflow-y-auto">
            <div className="p-3">
              <h3 className="text-[9px] text-gray-500 uppercase tracking-wider mb-2 px-1">PRESETS</h3>
              <div className="space-y-0.5">
                {presets.map(preset => (
                  <button
                    key={preset.id}
                    onClick={() => loadPreset(preset.id, 'preset')}
                    className={`w-full p-2.5 text-left transition-all rounded ${
                      selectedId === preset.id && selectedType === 'preset'
                        ? 'bg-gray-800 border-l-2 border-white' 
                        : 'hover:bg-gray-900/50 border-l-2 border-transparent'
                    }`}
                  >
                    <div className="font-medium text-sm">{preset.name}</div>
                    <div className="text-[10px] text-gray-500">{preset.criteria_count} criteria</div>
                  </button>
                ))}
              </div>
            </div>

            <div className="p-3 border-t border-gray-800">
              <div className="flex items-center justify-between mb-2 px-1">
                <h3 className="text-[9px] text-gray-500 uppercase tracking-wider">CUSTOM</h3>
              </div>
              {customCriteria.length === 0 ? (
                <p className="text-[10px] text-gray-600 p-2 text-center">
                  Edit a preset and save as custom
                </p>
              ) : (
                <div className="space-y-0.5">
                  {customCriteria.map(c => (
                    <div
                      key={c.id}
                      className={`p-2.5 transition-all rounded group relative ${
                        selectedId === c.id && selectedType === 'custom'
                          ? 'bg-gray-800 border-l-2 border-white' 
                          : 'hover:bg-gray-900/50 border-l-2 border-transparent'
                      }`}
                    >
                      <button
                        onClick={() => loadPreset(c.id, 'custom')}
                        className="w-full text-left"
                      >
                        <div className="font-medium text-sm">{c.name}</div>
                        <div className="text-[10px] text-gray-500">{c.criteria_count} criteria</div>
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); deleteCustom(c.id) }}
                        className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 p-1 text-red-500 hover:text-red-400"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Main Content - Criteria Editor */}
          <div className="flex-1 overflow-y-auto">
            {editData && (
              <div className="p-6">
                <div className="flex items-start justify-between mb-6">
                  <div className="flex-1">
                    {editMode ? (
                      <input
                        type="text"
                        value={editData.name}
                        onChange={(e) => { setEditData({ ...editData, name: e.target.value }); setHasChanges(true) }}
                        className="text-xl font-medium bg-transparent border-b border-gray-700 focus:border-white outline-none w-full max-w-md"
                      />
                    ) : (
                      <h2 className="text-xl font-medium">{editData.name}</h2>
                    )}
                    {editMode ? (
                      <input
                        type="text"
                        value={editData.description}
                        onChange={(e) => { setEditData({ ...editData, description: e.target.value }); setHasChanges(true) }}
                        placeholder="Description..."
                        className="text-xs text-gray-500 mt-1 bg-transparent border-b border-gray-800 focus:border-gray-600 outline-none w-full max-w-md"
                      />
                    ) : (
                      editData.description && <p className="text-xs text-gray-500 mt-1">{editData.description}</p>
                    )}
                  </div>
                  
                  <div className="flex items-center gap-2">
                    <button 
                      onClick={() => setShowYamlView(!showYamlView)}
                      className={`p-2 transition-colors ${showYamlView ? 'text-blue-400' : 'text-gray-500 hover:text-white'}`}
                      title="Toggle YAML view"
                    >
                      <Code size={16} />
                    </button>
                    {editMode ? (
                      <>
                        <input
                          type="text"
                          value={saveName}
                          onChange={(e) => setSaveName(e.target.value)}
                          placeholder="Save as..."
                          className="px-3 py-1.5 text-xs bg-black border border-gray-700 focus:border-white outline-none w-32"
                        />
                        <button
                          onClick={saveAsCustom}
                          disabled={!saveName.trim()}
                          className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-white text-black hover:bg-gray-200 disabled:opacity-50"
                        >
                          <Save size={12} />
                          Save
                        </button>
                        <button
                          onClick={() => { setEditMode(false); loadPreset(selectedId, selectedType) }}
                          className="px-3 py-1.5 text-xs border border-gray-700 hover:border-white"
                        >
                          Cancel
                        </button>
                      </>
                    ) : (
                      <button
                        onClick={() => { setEditMode(true); setSaveName(selectedType === 'custom' ? selectedId : `${selectedId}_custom`) }}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-gray-700 hover:border-white"
                      >
                        <Edit3 size={12} />
                        Edit
                      </button>
                    )}
                  </div>
                </div>

                {showYamlView ? (
                  <div className="bg-gray-900 border border-gray-800 p-4">
                    <pre className="text-xs text-gray-300 font-mono whitespace-pre-wrap overflow-x-auto">
                      {yamlContent || 'Loading...'}
                    </pre>
                  </div>
                ) : (
                  <>
                    <div className="mb-8">
                      <div className="flex items-center justify-between mb-3">
                        <h3 className="text-xs text-gray-500 uppercase tracking-wider flex items-center gap-2">
                          <Shield size={12} />
                          CRITERIA ({Object.keys(editData.criteria).length})
                        </h3>
                        {editMode && (
                          <button
                            onClick={addCriterion}
                            className="flex items-center gap-1 text-[10px] text-blue-400 hover:text-blue-300"
                          >
                            <Plus size={12} />
                            Add Criterion
                          </button>
                        )}
                      </div>
                      
                      <div className="space-y-3">
                        {Object.entries(editData.criteria).map(([id, criterion]) => (
                          <div key={id} className="border border-gray-800 bg-gray-900/30 p-4">
                            <div className="flex items-start justify-between mb-3">
                              <div className="flex-1">
                                {editMode ? (
                                  <div className="space-y-2">
                                    <div className="flex items-center gap-2">
                                      <input
                                        type="text"
                                        value={id}
                                        disabled
                                        className="text-[10px] text-gray-600 bg-black px-2 py-0.5 border border-gray-800 w-24"
                                        title="Criterion ID (cannot be changed)"
                                      />
                                      <input
                                        type="text"
                                        value={criterion.label}
                                        onChange={(e) => updateCriterion(id, 'label', e.target.value)}
                                        className="font-medium text-sm bg-transparent border-b border-gray-700 focus:border-white outline-none flex-1"
                                      />
                                    </div>
                                    <input
                                      type="text"
                                      value={criterion.description}
                                      onChange={(e) => updateCriterion(id, 'description', e.target.value)}
                                      placeholder="Description..."
                                      className="text-[10px] text-gray-500 bg-transparent border-b border-gray-800 focus:border-gray-600 outline-none w-full"
                                    />
                                  </div>
                                ) : (
                                  <>
                                    <div className="font-medium text-sm">{criterion.label}</div>
                                    {criterion.description && (
                                      <div className="text-[10px] text-gray-500">{criterion.description}</div>
                                    )}
                                  </>
                                )}
                              </div>
                              
                              <div className="flex items-center gap-2 ml-4">
                                {editMode ? (
                                  <>
                                    <select
                                      value={criterion.severity}
                                      onChange={(e) => updateCriterion(id, 'severity', e.target.value)}
                                      className={`text-[10px] px-2 py-1 border rounded bg-transparent ${SEVERITY_COLORS[criterion.severity]}`}
                                    >
                                      {SEVERITY_OPTIONS.map(s => (
                                        <option key={s} value={s} className="bg-black">{s.toUpperCase()}</option>
                                      ))}
                                    </select>
                                    <label className="flex items-center gap-1 text-[10px] text-gray-500">
                                      <input
                                        type="checkbox"
                                        checked={criterion.enabled}
                                        onChange={(e) => updateCriterion(id, 'enabled', e.target.checked)}
                                        className="accent-green-500"
                                      />
                                      Enabled
                                    </label>
                                    <button
                                      onClick={() => removeCriterion(id)}
                                      className="p-1 text-red-500 hover:text-red-400"
                                    >
                                      <Trash2 size={12} />
                                    </button>
                                  </>
                                ) : (
                                  <>
                                    <span className={`text-[10px] px-2 py-0.5 border rounded ${SEVERITY_COLORS[criterion.severity]}`}>
                                      {criterion.severity.toUpperCase()}
                                    </span>
                                    {!criterion.enabled && (
                                      <span className="text-[10px] text-gray-600">Disabled</span>
                                    )}
                                  </>
                                )}
                              </div>
                            </div>
                            
                            <div className="mt-3 pt-3 border-t border-gray-800">
                              <div className="grid grid-cols-3 gap-4">
                                {['safe', 'caution', 'unsafe'].map((level) => (
                                  <div key={level}>
                                    <div className={`text-[10px] mb-1 ${
                                      level === 'safe' ? 'text-green-400' :
                                      level === 'caution' ? 'text-yellow-400' : 'text-red-400'
                                    }`}>
                                      {level.toUpperCase()}
                                    </div>
                                    {editMode ? (
                                      <div className="flex items-center gap-2">
                                        <input
                                          type="range"
                                          min="0"
                                          max="1"
                                          step="0.05"
                                          value={criterion.thresholds[level as keyof typeof criterion.thresholds]}
                                          onChange={(e) => updateCriterion(id, `thresholds.${level}`, parseFloat(e.target.value))}
                                          className={`flex-1 h-1 ${
                                            level === 'safe' ? 'accent-green-500' :
                                            level === 'caution' ? 'accent-yellow-500' : 'accent-red-500'
                                          }`}
                                        />
                                        <span className="text-xs font-mono w-10 text-right">
                                          {(criterion.thresholds[level as keyof typeof criterion.thresholds] * 100).toFixed(0)}%
                                        </span>
                                      </div>
                                    ) : (
                                      <div className="text-sm font-mono">
                                        {level === 'safe' ? '<' : level === 'unsafe' ? '≥' : ''}
                                        {(criterion.thresholds[level as keyof typeof criterion.thresholds] * 100).toFixed(0)}%
                                      </div>
                                    )}
                                  </div>
                                ))}
                              </div>
                              
                              <div className="mt-2">
                                <div className="h-1.5 flex rounded-full overflow-hidden">
                                  <div className="bg-green-600" style={{ width: `${criterion.thresholds.safe * 100}%` }} />
                                  <div className="bg-yellow-600" style={{ width: `${(criterion.thresholds.unsafe - criterion.thresholds.safe) * 100}%` }} />
                                  <div className="bg-red-600" style={{ width: `${(1 - criterion.thresholds.unsafe) * 100}%` }} />
                                </div>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="mb-8">
                      <h3 className="text-xs text-gray-500 uppercase tracking-wider mb-3 flex items-center gap-2">
                        <Sliders size={12} />
                        OUTPUT OPTIONS
                      </h3>
                      <div className="flex flex-wrap gap-3">
                        {[
                          { key: 'generate_report', label: 'AI Report' },
                          { key: 'generate_labeled_video', label: 'Labeled Video' },
                          { key: 'explain_verdict', label: 'Explanation' },
                        ].map(opt => (
                          <label
                            key={opt.key}
                            className={`flex items-center gap-2 px-3 py-2 border rounded cursor-pointer transition-all ${
                              editData.options[opt.key as keyof typeof editData.options]
                                ? 'border-green-700 bg-green-900/20 text-green-400'
                                : 'border-gray-700 bg-gray-900/20 text-gray-500'
                            } ${editMode ? 'hover:border-gray-500' : ''}`}
                          >
                            <input
                              type="checkbox"
                              checked={editData.options[opt.key as keyof typeof editData.options]}
                              onChange={(e) => editMode && updateOptions(`options.${opt.key}`, e.target.checked)}
                              disabled={!editMode}
                              className="accent-green-500"
                            />
                            <span className="text-xs">{opt.label}</span>
                          </label>
                        ))}
                      </div>
                    </div>

                    <div className="p-4 bg-gray-900/50 border border-gray-800 rounded">
                      <div className="flex items-center gap-2 mb-2">
                        <Zap size={12} className="text-blue-400" />
                        <span className="text-xs text-gray-500 uppercase">Auto-Selected Detectors</span>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {detectors.map(d => (
                          <span key={d} className="px-2 py-1 text-[10px] bg-blue-900/30 text-blue-400 border border-blue-800 rounded">
                            {d}
                          </span>
                        ))}
                      </div>
                      <p className="text-[10px] text-gray-600 mt-2">
                        Based on your criteria, these detectors will automatically analyze videos.
                      </p>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* STAGES ENABLE/DISABLE TAB */}
      {activeTab === 'stages' && (
        <div className="flex-1 flex overflow-hidden">
          {/* Sidebar - Stage list */}
          <div className="w-64 border-r border-gray-800 flex-shrink-0 flex flex-col overflow-hidden">
            <div className="p-3 border-b border-gray-800">
              <div className="text-[9px] text-gray-600 uppercase tracking-wider">
                Toggle stages on/off. Disabled stages are skipped.
              </div>
            </div>
            
            <div className="flex-1 overflow-y-auto">
              {/* Builtin */}
              <div className="p-3">
                <h3 className="text-[9px] text-gray-500 uppercase tracking-wider mb-2 px-1">
                  BUILTIN ({allStages.filter(s => s.is_builtin).length})
                </h3>
                <div className="space-y-0.5">
                  {allStages.filter(s => s.is_builtin).map(stage => (
                    <div 
                      key={stage.type}
                      className={`flex items-center justify-between p-2 rounded transition-all ${
                        stage.enabled ? 'hover:bg-gray-900/50' : 'opacity-40'
                      }`}
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                          stage.enabled ? 'bg-green-500' : 'bg-gray-600'
                        }`} />
                        <span className="text-sm truncate">{stage.display_name}</span>
                      </div>
                      <button
                        onClick={() => toggleStage(stage.type, !stage.enabled)}
                        disabled={stage.required || stage.impact === 'critical' || togglingStage === stage.type}
                        className={`w-8 h-4 rounded-full transition-colors flex-shrink-0 ${
                          stage.enabled ? 'bg-green-600' : 'bg-gray-700'
                        } ${(stage.required || stage.impact === 'critical') ? 'opacity-30 cursor-not-allowed' : 'cursor-pointer'}`}
                      >
                        <div className={`w-3 h-3 rounded-full bg-white transition-transform mt-0.5 ${
                          stage.enabled ? 'translate-x-4.5 ml-0.5' : 'translate-x-0.5'
                        }`} style={{ marginLeft: stage.enabled ? '17px' : '2px' }} />
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              {/* External */}
              {allStages.filter(s => s.is_external).length > 0 && (
                <div className="p-3 border-t border-gray-800">
                  <h3 className="text-[9px] text-gray-500 uppercase tracking-wider mb-2 px-1">
                    EXTERNAL ({allStages.filter(s => s.is_external).length})
                  </h3>
                  <div className="space-y-0.5">
                    {allStages.filter(s => s.is_external).map(stage => (
                      <div 
                        key={stage.type}
                        className={`flex items-center justify-between p-2 rounded transition-all ${
                          stage.enabled ? 'hover:bg-gray-900/50' : 'opacity-40'
                        }`}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                            stage.enabled ? 'bg-purple-500' : 'bg-gray-600'
                          }`} />
                          <span className="text-sm truncate">{stage.display_name}</span>
                        </div>
                        <button
                          onClick={() => toggleStage(stage.type, !stage.enabled)}
                          disabled={togglingStage === stage.type}
                          className={`w-8 h-4 rounded-full transition-colors flex-shrink-0 cursor-pointer ${
                            stage.enabled ? 'bg-purple-600' : 'bg-gray-700'
                          }`}
                        >
                          <div className={`w-3 h-3 rounded-full bg-white transition-transform mt-0.5`} 
                            style={{ marginLeft: stage.enabled ? '17px' : '2px' }} />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Main content - Stage details */}
          <div className="flex-1 overflow-y-auto p-6">
            <div className="max-w-2xl">
              <h3 className="text-[9px] text-gray-500 uppercase tracking-wider mb-4">STAGE DETAILS</h3>
              
              <div className="space-y-1">
                {allStages.map(stage => (
                  <div 
                    key={stage.type}
                    className={`flex items-center justify-between py-2.5 border-b border-gray-800/50 ${
                      !stage.enabled ? 'opacity-40' : ''
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <div className={`w-2 h-2 rounded-full ${
                        stage.enabled 
                          ? stage.is_external ? 'bg-purple-500' : 'bg-green-500'
                          : 'bg-gray-600'
                      }`} />
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-sm">{stage.display_name}</span>
                          <span className={`text-[9px] px-1 py-px rounded ${
                            stage.impact === 'critical' ? 'bg-red-900/30 text-red-500' :
                            stage.impact === 'supporting' ? 'bg-yellow-900/30 text-yellow-500' :
                            'bg-gray-800 text-gray-500'
                          }`}>
                            {stage.impact}
                          </span>
                          {stage.is_external && (
                            <span className="text-[9px] px-1 py-px bg-purple-900/30 text-purple-400 rounded">
                              external
                            </span>
                          )}
                          {stage.required && (
                            <Lock size={10} className="text-gray-600" />
                          )}
                        </div>
                        <div className="text-[10px] text-gray-600 mt-0.5">
                          {stage.type}
                        </div>
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-4">
                      {!stage.enabled && (
                        <span className="text-[10px] text-yellow-600">skipped</span>
                      )}
                      <span className="text-[10px] text-gray-600">
                        {stage.enabled ? 'enabled' : 'disabled'}
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              {/* Info */}
              <div className="mt-8 text-[10px] text-gray-600 space-y-1">
                <p>• <span className="text-yellow-600">supporting</span> stages affect confidence when disabled</p>
                <p>• <span className="text-red-500">critical</span> stages cannot be disabled</p>
                <p>• Skipped stages are recorded in evaluation history</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* EXTERNAL STAGES CONFIG TAB */}
      {activeTab === 'stage-config' && (
        <div className="flex-1 flex overflow-hidden">
          {/* Sidebar - External configs list */}
          <div className="w-64 border-r border-gray-800 flex-shrink-0 flex flex-col">
            <div className="p-3 border-b border-gray-800">
              <button
                onClick={createNewStageConfig}
                className="w-full flex items-center justify-center gap-2 px-3 py-2 text-xs bg-purple-600 hover:bg-purple-500 text-white rounded transition-colors"
              >
                <Plus size={14} />
                New External Stage
              </button>
            </div>
            
            <div className="flex-1 overflow-y-auto">
              {/* Builtin stages info */}
              <div className="p-3">
                <h3 className="text-[9px] text-gray-500 uppercase tracking-wider mb-2 px-1">
                  BUILTIN STAGES ({allStages.filter(s => s.is_builtin).length})
                </h3>
                <div className="space-y-1">
                  {allStages.filter(s => s.is_builtin).map(stage => (
                    <div key={stage.type} className="px-2 py-1.5 text-xs text-gray-500 flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full bg-blue-500"></div>
                      {stage.display_name}
                    </div>
                  ))}
                </div>
              </div>

              {/* External configs */}
              <div className="p-3 border-t border-gray-800">
                <h3 className="text-[9px] text-gray-500 uppercase tracking-wider mb-2 px-1">
                  EXTERNAL STAGES ({externalConfigs.length})
                </h3>
                {externalConfigs.length === 0 ? (
                  <p className="text-[10px] text-gray-600 p-2 text-center">
                    No external stages configured.<br/>
                    Create one to integrate external APIs.
                  </p>
                ) : (
                  <div className="space-y-1">
                    {externalConfigs.map(config => (
                      <div
                        key={config.id}
                        className={`p-2.5 rounded transition-all cursor-pointer group ${
                          selectedConfigId === config.id
                            ? 'bg-gray-800 border-l-2 border-purple-400'
                            : 'hover:bg-gray-900/50 border-l-2 border-transparent'
                        }`}
                        onClick={() => loadExternalConfig(config)}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <div className={`w-2 h-2 rounded-full ${config.enabled ? 'bg-purple-500' : 'bg-gray-600'}`}></div>
                            <span className="font-medium text-sm">{config.name}</span>
                          </div>
                          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100">
                            <button
                              onClick={(e) => { e.stopPropagation(); toggleExternalConfig(config.id, !config.enabled) }}
                              className={`p-1 ${config.enabled ? 'text-green-500' : 'text-gray-500'} hover:text-white`}
                              title={config.enabled ? 'Disable' : 'Enable'}
                            >
                              {config.enabled ? <CheckCircle size={12} /> : <XCircle size={12} />}
                            </button>
                            <button
                              onClick={(e) => { e.stopPropagation(); deleteExternalConfig(config.id) }}
                              className="p-1 text-red-500 hover:text-red-400"
                            >
                              <Trash2 size={12} />
                            </button>
                          </div>
                        </div>
                        <div className="text-[10px] text-gray-500 mt-1">
                          {config.stage_ids.length} stage{config.stage_ids.length !== 1 ? 's' : ''}
                          {!config.validated && <span className="text-yellow-500 ml-2">• Invalid</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Main Content - YAML Editor */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Config header */}
            <div className="p-4 border-b border-gray-800 flex-shrink-0">
              <div className="flex items-center justify-between">
                <div className="flex-1 grid grid-cols-3 gap-4">
                  <div>
                    <label className="text-[10px] text-gray-500 uppercase block mb-1">Config ID *</label>
                    <input
                      type="text"
                      value={stageConfigId}
                      onChange={(e) => setStageConfigId(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ''))}
                      placeholder="customer_policy_v1"
                      className="w-full px-3 py-1.5 text-sm bg-black border border-gray-700 focus:border-purple-500 outline-none rounded"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-gray-500 uppercase block mb-1">Display Name *</label>
                    <input
                      type="text"
                      value={stageName}
                      onChange={(e) => setStageName(e.target.value)}
                      placeholder="Customer Policy"
                      className="w-full px-3 py-1.5 text-sm bg-black border border-gray-700 focus:border-purple-500 outline-none rounded"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] text-gray-500 uppercase block mb-1">Description</label>
                    <input
                      type="text"
                      value={stageDescription}
                      onChange={(e) => setStageDescription(e.target.value)}
                      placeholder="Optional description..."
                      className="w-full px-3 py-1.5 text-sm bg-black border border-gray-700 focus:border-purple-500 outline-none rounded"
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* YAML Editor + Validation */}
            <div className="flex-1 flex overflow-hidden">
              {/* Editor */}
              <div className="flex-1 flex flex-col p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Terminal size={14} className="text-purple-400" />
                    <span className="text-xs text-gray-500 uppercase">Stage Definition (YAML)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {isValidating && (
                      <span className="text-[10px] text-gray-500">Validating...</span>
                    )}
                    {stageValidation && (
                      <span className={`text-[10px] flex items-center gap-1 ${stageValidation.valid ? 'text-green-400' : 'text-red-400'}`}>
                        {stageValidation.valid ? <CheckCircle size={12} /> : <AlertCircle size={12} />}
                        {stageValidation.valid ? 'Valid' : 'Invalid'}
                      </span>
                    )}
                  </div>
                </div>
                <textarea
                  value={stageYaml}
                  onChange={(e) => setStageYaml(e.target.value)}
                  placeholder="Paste your YAML stage definition here..."
                  className="flex-1 w-full px-4 py-3 text-sm font-mono bg-gray-900 border border-gray-800 focus:border-purple-500 outline-none rounded resize-none"
                  spellCheck={false}
                />
              </div>

              {/* Validation Results & Help */}
              <div className="w-72 border-l border-gray-800 flex flex-col overflow-hidden">
                {/* Validation results */}
                <div className="p-4 border-b border-gray-800">
                  <h4 className="text-[10px] text-gray-500 uppercase mb-2">Validation Result</h4>
                  {!stageValidation ? (
                    <p className="text-xs text-gray-600">Enter YAML to validate</p>
                  ) : stageValidation.valid ? (
                    <div className="space-y-2">
                      <div className="text-xs text-green-400 flex items-center gap-1">
                        <CheckCircle size={14} />
                        YAML is valid
                      </div>
                      {stageValidation.stages.length > 0 && (
                        <div className="mt-2">
                          <span className="text-[10px] text-gray-500">Stages found:</span>
                          {stageValidation.stages.map(s => (
                            <div key={s.id} className="mt-1 px-2 py-1 bg-purple-900/20 border border-purple-800 rounded text-xs">
                              <div className="font-medium text-purple-400">{s.name || s.id}</div>
                              {s.endpoint && (
                                <div className="text-[10px] text-gray-500 truncate">{s.endpoint}</div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="text-xs text-red-400">
                      <div className="flex items-start gap-1">
                        <AlertCircle size={14} className="flex-shrink-0 mt-0.5" />
                        <span>{stageValidation.error}</span>
                      </div>
                    </div>
                  )}
                </div>

                {/* Help */}
                <div className="flex-1 overflow-y-auto p-4">
                  <h4 className="text-[10px] text-gray-500 uppercase mb-2">YAML Schema Help</h4>
                  <div className="space-y-3 text-[11px] text-gray-400">
                    <div>
                      <span className="text-gray-300 font-medium">version:</span> v1 (required)
                    </div>
                    <div>
                      <span className="text-gray-300 font-medium">stages:</span> List of stage definitions
                    </div>
                    <div className="pl-2 space-y-1">
                      <div><span className="text-purple-400">id:</span> unique identifier (lowercase)</div>
                      <div><span className="text-purple-400">name:</span> display name for UI</div>
                      <div><span className="text-purple-400">endpoint.url:</span> HTTP endpoint to call</div>
                      <div><span className="text-purple-400">endpoint.auth:</span> bearer/basic/api_key</div>
                      <div><span className="text-purple-400">input_mapping:</span> map state → request</div>
                      <div><span className="text-purple-400">output_mapping:</span> map response → state</div>
                    </div>
                    <div className="pt-2 border-t border-gray-800">
                      <span className="text-gray-300 font-medium">Environment Variables:</span>
                      <p className="mt-1">Use <code className="text-purple-400">${'{'}VAR_NAME{'}'}</code> to reference environment variables securely.</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Footer actions */}
            <div className="p-4 border-t border-gray-800 flex items-center justify-end gap-3 flex-shrink-0">
              <button
                onClick={createNewStageConfig}
                className="px-4 py-2 text-xs border border-gray-700 hover:border-white rounded transition-colors"
              >
                Reset
              </button>
              <button
                onClick={saveExternalConfig}
                disabled={!stageValidation?.valid || !stageConfigId.trim() || !stageName.trim() || isSavingStage}
                className="flex items-center gap-2 px-4 py-2 text-xs bg-purple-600 hover:bg-purple-500 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded transition-colors"
                title={`Valid: ${stageValidation?.valid}, ID: "${stageConfigId}", Name: "${stageName}"`}
              >
                <Save size={14} />
                {isSavingStage ? 'Saving...' : selectedConfigId ? 'Update Stage' : 'Save Stage'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Settings
