import { FC, useEffect, useState } from 'react'
import { 
  Settings as SettingsIcon, Check, AlertCircle, ChevronDown, ChevronRight,
  Shield, Eye, FileText, Zap, Info, RefreshCw, Upload, Download, Copy,
  Trash2, Plus, Save, Edit3, Code, Sliders
} from 'lucide-react'
import { api } from '@/api/endpoints'
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

const Settings: FC = () => {
  const [presets, setPresets] = useState<Preset[]>([])
  const [customCriteria, setCustomCriteria] = useState<Preset[]>([])
  const [selectedId, setSelectedId] = useState<string>('child_safety')
  const [selectedType, setSelectedType] = useState<'preset' | 'custom'>('preset')
  const [isLoading, setIsLoading] = useState(true)
  
  // Editor state
  const [editMode, setEditMode] = useState(false)
  const [editData, setEditData] = useState<EditableCriteria | null>(null)
  const [showYamlView, setShowYamlView] = useState(false)
  const [yamlContent, setYamlContent] = useState('')
  const [saveName, setSaveName] = useState('')
  const [hasChanges, setHasChanges] = useState(false)
  const [detectors, setDetectors] = useState<string[]>([])

  // Load presets on mount
  useEffect(() => {
    loadData()
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
      
      // Load first preset
      if (presetsRes.data?.length > 0) {
        loadPreset(presetsRes.data[0].id, 'preset')
      }
    } catch (error) {
      console.error('Failed to load criteria:', error)
      toast.error('Failed to load criteria')
    }
    setIsLoading(false)
  }

  const loadPreset = async (id: string, type: 'preset' | 'custom') => {
    setSelectedId(id)
    setSelectedType(type)
    setEditMode(false)
    setHasChanges(false)
    
    try {
      const endpoint = type === 'preset' ? `/criteria/presets/${id}` : `/criteria/custom/${id}`
      const { data } = await api.get<CriteriaDetail>(endpoint)
      
      // Convert to editable format
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
      
      // Also get YAML export
      try {
        const exportEndpoint = type === 'preset' 
          ? `/criteria/presets/${id}/export?format=yaml`
          : `/criteria/custom/${id}/export?format=yaml`
        const yamlRes = await api.get(exportEndpoint)
        setYamlContent(yamlRes.data.content || yamlRes.data)
      } catch (e) {
        // YAML export optional, continue without it
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
    
    // Convert to YAML format
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
      // Convert to YAML string (simple implementation)
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
        // Select the new custom preset
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
      // Switch to first preset
      if (presets.length > 0) {
        loadPreset(presets[0].id, 'preset')
      }
    } catch (error) {
      toast.error('Failed to delete')
    }
  }

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center bg-black text-white">
        <div className="text-center">
          <SettingsIcon size={48} className="mx-auto mb-4 animate-pulse text-gray-600" />
          <p className="text-gray-400">Loading criteria...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col bg-black text-white overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-800 flex-shrink-0">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-xs text-gray-500 tracking-widest">EVALUATION CRITERIA</span>
            <p className="text-[10px] text-gray-600 mt-1">Define what to evaluate in videos</p>
          </div>
          <div className="flex items-center gap-2">
            {editMode && hasChanges && (
              <span className="text-[10px] text-yellow-500">• Unsaved changes</span>
            )}
            <button 
              onClick={() => setShowYamlView(!showYamlView)}
              className={`p-2 transition-colors ${showYamlView ? 'text-blue-400' : 'text-gray-500 hover:text-white'}`}
              title="Toggle YAML view"
            >
              <Code size={16} />
            </button>
            <button 
              onClick={loadData}
              className="p-2 text-gray-500 hover:text-white transition-colors"
              title="Refresh"
            >
              <RefreshCw size={16} />
            </button>
          </div>
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar */}
        <div className="w-56 border-r border-gray-800 flex-shrink-0 overflow-y-auto">
          {/* Built-in Presets */}
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

          {/* Custom Criteria */}
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

        {/* Main Content */}
        <div className="flex-1 overflow-y-auto">
          {editData && (
            <div className="p-6">
              {/* Header with Edit/Save */}
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
                // YAML View
                <div className="bg-gray-900 border border-gray-800 p-4">
                  <pre className="text-xs text-gray-300 font-mono whitespace-pre-wrap overflow-x-auto">
                    {yamlContent || 'Loading...'}
                  </pre>
                </div>
              ) : (
                <>
                  {/* Criteria List */}
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
                          
                          {/* Thresholds */}
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
                            
                            {/* Visual threshold bar */}
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

                  {/* Output Options */}
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

                  {/* Auto-detected Detectors */}
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
    </div>
  )
}

export default Settings
