import { FC, useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { 
  Upload, Plus, Video, Play, Trash2,
  RotateCcw, Loader2, Link, Database, Cloud,
  Check, Circle, AlertCircle, X, Eye, ChevronDown, Info
} from 'lucide-react'
import { 
  useVideoStore, 
  useVideoStoreActions, 
  useSelectedVideo, 
  useQueue,
  QueueVideo, 
  VideoStatus 
} from '@/store/videoStore'
import { useSettingsStore } from '@/store/settingsStore'
import { evaluationApi, stageApi, createSSEConnection, api, stagesApi, StageInfo } from '@/api/endpoints'
import { evaluations as evaluationsApi } from '@/api'
import { ProcessedFrames } from '@/components/pipeline/ProcessedFrames'
import PipelineStages, { PipelineStage } from '@/components/pipeline/PipelineStages'
import ReactMarkdown from 'react-markdown'
import toast from 'react-hot-toast'

interface CriteriaPreset {
  id: string
  name: string
  description?: string
  criteria_count: number
}

// PipelineStage interface imported from PipelineStages component
// Default builtin stages
const DEFAULT_PIPELINE_STAGES: PipelineStage[] = [
  { id: 'ingest_video', backendId: 'ingest', name: 'Ingest', number: '01' },
  { id: 'segment_video', backendId: 'segment', name: 'Segment', number: '02' },
  { id: 'yolo26_vision', backendId: 'yolo26', name: 'Vision', number: '03' },
  { id: 'yoloworld_vision', backendId: 'yoloworld', name: 'YOLO-W', number: '04' },
  { id: 'violence_detection', backendId: 'violence', name: 'Violence', number: '05' },
  { id: 'audio_transcription', backendId: 'audio_asr', name: 'Audio', number: '06' },
  { id: 'ocr_extraction', backendId: 'ocr', name: 'OCR', number: '07' },
  { id: 'text_moderation', backendId: 'text_moderation', name: 'Moderate', number: '08' },
  { id: 'policy_fusion', backendId: 'policy_fusion', name: 'Scoring', number: '09' },
  { id: 'report_generation', backendId: 'report', name: 'Report', number: '10' },
]

// Map backend stage types to UI stage ids
const BACKEND_TO_UI_MAP: Record<string, string> = {
  'yolo26': 'yolo26_vision',
  'yoloworld': 'yoloworld_vision',
  'violence': 'violence_detection',
  'whisper': 'audio_transcription',
  'ocr': 'ocr_extraction',
  'text_moderation': 'text_moderation',
}

const DEFAULT_STAGE_PROGRESS_MAP: Record<string, number> = {
  'ingest_video': 5, 'segment_video': 10, 'yolo26_vision': 25,
  'yoloworld_vision': 30, 'violence_detection': 40, 'audio_transcription': 55,
  'ocr_extraction': 65, 'text_moderation': 75, 'policy_fusion': 90,
  'report_generation': 100
}

// Compute progress for any stage (including external ones)
const getStageProgress = (stageId: string, allStages: PipelineStage[]): number => {
  if (DEFAULT_STAGE_PROGRESS_MAP[stageId]) return DEFAULT_STAGE_PROGRESS_MAP[stageId]
  // For external stages, interpolate based on position
  const idx = allStages.findIndex(s => s.id === stageId)
  if (idx < 0) return 50
  return Math.round((idx / allStages.length) * 100)
}

// Minimalist metric component
const Metric = ({ label, value, status }: { label: string, value: string | number, status?: 'ok' | 'warn' | 'bad' }) => (
  <div className="p-2.5">
    <div className="text-[10px] text-gray-600 mb-0.5">{label}</div>
    <div className={`text-base font-medium ${status === 'bad' ? 'text-red-400' : status === 'warn' ? 'text-yellow-400' : 'text-white'}`}>{value}</div>
  </div>
)

// Section label
const Label = ({ children, variant }: { children: React.ReactNode, variant?: 'danger' | 'success' | 'warn' }) => (
  <div className={`text-[10px] uppercase tracking-wider mb-2 ${
    variant === 'danger' ? 'text-red-400' : variant === 'success' ? 'text-green-400' : variant === 'warn' ? 'text-yellow-400' : 'text-gray-500'
  }`}>{children}</div>
)

// Generate stage content matching original index.html data structure
const generateStageContent = (stageName: string, data: any) => {
  if (!data) return <div className="text-gray-500 text-sm italic">No data available</div>
  
  const evidence = data.evidence || {}
  const metadata = data.metadata || {}
  
  // Handle cached stages (from reprocessing) - show full data with cached indicator
  // Industry standard: Display cached data transparently with clear visual indicator
  if (data.status === 'cached' || data.cached === true) {
    const CachedBadge = () => (
      <div className="flex items-center gap-1.5 text-[10px] text-blue-400/70 mb-2">
        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        <span>Cached from previous run</span>
      </div>
    )
    
    // Render cached ingest stage
    if (stageName === 'ingest_video') {
      return (
        <div className="space-y-2">
          <CachedBadge />
          <div className="grid grid-cols-4 divide-x divide-gray-800 bg-blue-900/10 border border-blue-900/20 rounded">
            <Metric label="Duration" value={data.duration ? `${data.duration.toFixed(1)}s` : '—'} />
            <Metric label="Resolution" value={data.width && data.height ? `${data.width}×${data.height}` : '—'} />
            <Metric label="FPS" value={data.fps ? data.fps.toFixed(1) : '—'} />
            <Metric label="Audio" value={data.has_audio ? '✓' : '✗'} status={data.has_audio ? 'ok' : undefined} />
          </div>
        </div>
      )
    }
    
    // Render cached segment stage
    if (stageName === 'segment_video') {
      return (
        <div className="space-y-2">
          <CachedBadge />
          <div className="grid grid-cols-3 divide-x divide-gray-800 bg-blue-900/10 border border-blue-900/20 rounded">
            <Metric label="Frames" value={data.frames_extracted || data.frames_stored || '—'} />
            <Metric label="Sample Rate" value={`${data.sampling_fps || 1.0} fps`} />
            <Metric label="Segments" value={data.segments_count || '—'} />
          </div>
          {data.thumbnails_stored > 0 && (
            <div className="text-[10px] text-gray-500 pl-1">
              {data.thumbnails_stored} thumbnails available in storage
            </div>
          )}
        </div>
      )
    }
    
    // Fallback for other cached stages (shouldn't happen for ingest/segment only)
    return (
      <div className="p-3 bg-blue-900/10 border border-blue-900/20 rounded">
        <CachedBadge />
        <div className="text-sm text-gray-400">Cached data available</div>
      </div>
    )
  }
  
  // Handle skipped stages (disabled, not run)
  if (data.status === 'skipped') {
    return (
      <div className="p-4 bg-gray-900/30 border border-dashed border-gray-700 rounded">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-gray-800 flex items-center justify-center">
            <span className="text-gray-500 text-sm">⏭</span>
          </div>
          <div>
            <div className="text-sm text-gray-400">Stage Skipped</div>
            <div className="text-[10px] text-gray-600 mt-0.5">
              {data.skip_reason || 'Stage was disabled'}
            </div>
          </div>
        </div>
      </div>
    )
  }
  
  switch (stageName) {
    case 'ingest_video': {
      const duration = data.duration || metadata.duration
      const width = data.width || metadata.width
      const height = data.height || metadata.height
      const fps = data.fps || metadata.fps
      const hasAudio = data.has_audio !== undefined ? data.has_audio : metadata.has_audio
      const videoId = data.video_id || metadata.video_id
      const originalMeta = data.original_metadata || {}
      
      return (
        <div className="space-y-2">
          <div className="grid grid-cols-4 divide-x divide-gray-800 bg-gray-900/50 rounded">
            <Metric label="Duration" value={duration ? `${duration.toFixed(1)}s` : '—'} />
            <Metric label="Resolution" value={width && height ? `${width}×${height}` : '—'} />
            <Metric label="FPS" value={fps ? fps.toFixed(1) : '—'} />
            <Metric label="Audio" value={hasAudio ? '✓' : '✗'} status={hasAudio ? 'ok' : undefined} />
          </div>
          {(originalMeta.width || originalMeta.height) && (
            <div className="text-[10px] text-gray-500 pl-1">
              Normalized from {originalMeta.width}×{originalMeta.height} → 720p @ 30fps
            </div>
          )}
        </div>
      )
    }
    
    case 'segment_video': {
      const sampledFrames = data.frames_extracted || data.sampled_frames || metadata.sampled_frames || evidence.frames?.length
      const segments = data.segments_created || data.segments || metadata.segments || evidence.violence_segments?.length
      const samplingFps = data.sampling_fps || data.yolo_sampling_fps || metadata.sampling_fps || 1.0
      
      return (
        <div className="grid grid-cols-3 divide-x divide-gray-800 bg-gray-900/50 rounded">
          <Metric label="Frames" value={Array.isArray(sampledFrames) ? sampledFrames.length : (sampledFrames || '—')} />
          <Metric label="Sample Rate" value={`${samplingFps} fps`} />
          <Metric label="Segments" value={Array.isArray(segments) ? segments.length : (segments || '—')} />
        </div>
      )
    }
    
    // YOLO26 Vision
    case 'yolo26_vision': {
      const visionData = data.detections || evidence.vision || []
      const summary = data.detection_summary || {}
      const objectCounts: Record<string, number> = Object.keys(summary).length > 0 
        ? summary 
        : visionData.reduce((acc: Record<string, number>, d: any) => {
            const label = d.label || d.class || 'unknown'
            acc[label] = (acc[label] || 0) + 1
            return acc
          }, {})
      const topObjects = Object.entries(objectCounts).sort((a, b) => b[1] - a[1]).slice(0, 6)
      const totalDetections = data.total_detections || visionData.length
      
      return (
        <div className="space-y-2">
          <div className="text-sm text-gray-400">
            <span className="text-xl text-white font-light">{totalDetections}</span> detections
          </div>
          {topObjects.length > 0 && (
            <div className="space-y-1">
              {topObjects.map(([label, count]) => (
                <div key={label} className="flex justify-between text-sm py-1 border-b border-gray-800/50 last:border-0">
                  <span className="capitalize text-gray-400">{label}</span>
                  <span className="text-white font-mono">{count}</span>
                </div>
              ))}
            </div>
          )}
          {data.safety_signals && (
            <div className="text-xs text-gray-500 pt-1">
              {data.safety_signals.has_weapons 
                ? <span className="text-red-400">{data.safety_signals.weapon_count} weapons detected</span>
                : <span className="text-green-400">No weapons</span>
              }
            </div>
          )}
        </div>
      )
    }
    
    // YOLO-World Vision
    case 'yoloworld_vision': {
      const yoloworldData = data.detections || evidence.yoloworld || []
      const matchedPrompts = [...new Set(yoloworldData.map((d: any) => d.prompt_match || d.label).filter(Boolean))]
      const yoloworldCounts: Record<string, number> = {}
      yoloworldData.forEach((d: any) => {
        const label = d.prompt_match || d.label
        if (label) yoloworldCounts[label] = (yoloworldCounts[label] || 0) + 1
      })
      const totalDetections = data.total_detections || yoloworldData.length
      
      return (
        <div className="space-y-2">
          <div className="text-sm text-gray-400">
            <span className="text-xl text-white font-light">{totalDetections}</span> from {matchedPrompts.length} prompts
          </div>
          {matchedPrompts.length > 0 && (
            <div className="space-y-1">
              {matchedPrompts.slice(0, 6).map((prompt: string) => (
                <div key={prompt} className="flex justify-between text-sm py-1 border-b border-gray-800/50 last:border-0">
                  <span className="text-gray-400">{prompt}</span>
                  <span className="text-white font-mono">{yoloworldCounts[prompt]}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )
    }
    
    case 'violence_detection': {
      const violenceSegments = data.violence_segments || evidence.violence_segments || evidence.violence || []
      const highViolence = violenceSegments.filter((s: any) => (s.violence_score || s.score || 0) > 0.5)
      const maxScore = Math.max(...violenceSegments.map((s: any) => s.violence_score || s.score || 0), 0)
      
      return (
        <div className="space-y-2">
          <div className="grid grid-cols-3 divide-x divide-gray-800 bg-gray-900/50 rounded">
            <Metric label="Segments" value={violenceSegments.length} />
            <Metric label="Flagged" value={highViolence.length} status={highViolence.length > 0 ? 'bad' : 'ok'} />
            <Metric label="Peak" value={`${(maxScore * 100).toFixed(0)}%`} status={maxScore > 0.5 ? 'bad' : maxScore > 0.3 ? 'warn' : 'ok'} />
          </div>
          {highViolence.length > 0 && (
            <div className="space-y-1 pt-1">
              <Label variant="danger">High Violence</Label>
              {highViolence.slice(0, 3).map((seg: any, i: number) => (
                <div key={i} className="flex justify-between text-xs py-1.5 px-2 bg-red-950/20 rounded">
                  <span className="text-gray-500 font-mono">{seg.start_time?.toFixed(1)}s — {seg.end_time?.toFixed(1)}s</span>
                  <span className="text-red-400">{((seg.violence_score || seg.score) * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )
    }
    
    case 'audio_transcription': {
      const transcript = data.transcript || evidence.transcript || {}
      const chunks = data.chunks || transcript.chunks || evidence.asr || []
      const fullText = data.full_text || transcript.text || ''
      
      return (
        <div className="space-y-2">
          <div className="text-sm text-gray-400">
            <span className="text-xl text-white font-light">{chunks.length}</span> chunks
            {transcript.language && <span className="text-gray-600 ml-2">• {transcript.language}</span>}
          </div>
          
          {fullText && (
            <div className="text-sm text-gray-300 leading-relaxed bg-gray-900/50 p-3 rounded">
              {fullText}
            </div>
          )}
          
          {chunks.length > 0 && !fullText && (
            <div className="space-y-1">
              {chunks.slice(0, 4).map((chunk: any, i: number) => (
                <div key={i} className="text-xs py-1.5 border-b border-gray-800/50 last:border-0">
                  <span className="text-gray-600 font-mono mr-2">
                    {chunk.start_time != null ? `${chunk.start_time.toFixed(1)}s` : '—'}
                  </span>
                  <span className="text-gray-400">{chunk.text}</span>
                </div>
              ))}
              {chunks.length > 4 && (
                <div className="text-[10px] text-gray-600">+{chunks.length - 4} more</div>
              )}
            </div>
          )}
        </div>
      )
    }
    
    case 'ocr_extraction': {
      const ocrResults = evidence.ocr || data.ocr || []
      const textsFromStage = data.texts || []
      const texts = textsFromStage.length > 0 ? textsFromStage : ocrResults.map((o: any) => o.text).filter(Boolean)
      const totalDetections = data.total_detections || ocrResults.length
      
      return (
        <div className="space-y-2">
          <div className="text-sm text-gray-400">
            <span className="text-xl text-white font-light">{totalDetections}</span> text regions
          </div>
          {texts.length > 0 ? (
            <div className="space-y-1">
              {texts.slice(0, 4).map((text: string, i: number) => (
                <div key={i} className="text-xs text-gray-400 py-1 border-b border-gray-800/50 last:border-0 truncate">
                  {text}
                </div>
              ))}
              {texts.length > 4 && (
                <div className="text-[10px] text-gray-600">+{texts.length - 4} more</div>
              )}
            </div>
          ) : (
            <div className="text-gray-600 text-sm">No text detected</div>
          )}
        </div>
      )
    }
    
    // Text Moderation
    case 'text_moderation': {
      const transcriptMod = data.transcript_moderation || evidence.transcript_moderation || []
      const ocrMod = data.ocr_moderation || evidence.ocr_moderation || []
      const flaggedTranscript = data.flagged_transcript || transcriptMod.filter((m: any) => 
        m.profanity_score > 0.3 || m.sexual_score > 0.3 || m.hate_score > 0.3 || m.violence_score > 0.3 || m.drugs_score > 0.3
      )
      const flaggedOcr = data.flagged_ocr || ocrMod.filter((m: any) => 
        m.profanity_score > 0.3 || m.sexual_score > 0.3 || m.hate_score > 0.3 || m.violence_score > 0.3 || m.drugs_score > 0.3
      )
      const transcriptCount = data.transcript_chunks_analyzed || transcriptMod.length
      const ocrCount = data.ocr_items_analyzed || ocrMod.length
      const flaggedTranscriptCount = data.flagged_transcript_count ?? flaggedTranscript.length
      const flaggedOcrCount = data.flagged_ocr_count ?? flaggedOcr.length
      const totalFlagged = flaggedTranscriptCount + flaggedOcrCount
      
      return (
        <div className="space-y-2">
          <div className="grid grid-cols-2 divide-x divide-gray-800 bg-gray-900/50 rounded">
            <Metric label="Transcript" value={transcriptCount} status={flaggedTranscriptCount > 0 ? 'bad' : 'ok'} />
            <Metric label="OCR" value={ocrCount} status={flaggedOcrCount > 0 ? 'bad' : 'ok'} />
          </div>
          
          {totalFlagged > 0 && (
            <div className="space-y-1 pt-1">
              <Label variant="danger">{totalFlagged} Flagged</Label>
              {flaggedTranscript.slice(0, 2).map((mod: any, i: number) => (
                <div key={`t-${i}`} className="text-xs py-1.5 px-2 bg-red-950/20 rounded">
                  <div className="text-gray-400 truncate">"{mod.text || mod.original_text || '—'}"</div>
                  <div className="text-[10px] text-red-400 mt-0.5">
                    {(mod.profanity_score || mod.profanity || 0) > 0.3 && 'profanity '}
                    {(mod.sexual_score || mod.sexual || 0) > 0.3 && 'sexual '}
                    {(mod.hate_score || mod.hate || 0) > 0.3 && 'hate '}
                    {(mod.violence_score || mod.violence || 0) > 0.3 && 'violence'}
                  </div>
                </div>
              ))}
              {flaggedOcr.slice(0, 2).map((mod: any, i: number) => (
                <div key={`o-${i}`} className="text-xs py-1.5 px-2 bg-yellow-950/20 rounded">
                  <div className="text-gray-400 truncate">"{mod.text || '—'}"</div>
                </div>
              ))}
            </div>
          )}
          
          {totalFlagged === 0 && transcriptCount > 0 && (
            <div className="text-xs text-green-400">✓ All content clean</div>
          )}
        </div>
      )
    }
    
    case 'policy_fusion': {
      const scores = data.scores || data.criteria || {}
      const verdict = data.verdict || 'unknown'
      const violations = data.violations || []
      const violationsCount = data.violations_count ?? violations.length
      
      const verdictStyle = verdict === 'UNSAFE' || verdict === 'fail' 
        ? 'text-red-400' 
        : verdict === 'SAFE' || verdict === 'pass' 
          ? 'text-green-400' 
          : 'text-yellow-400'
      
      return (
        <div className="space-y-3">
          {/* Verdict */}
          <div className="text-center py-3">
            <div className="text-[10px] text-gray-600 uppercase tracking-widest mb-1">Verdict</div>
            <div className={`text-3xl font-light uppercase tracking-wide ${verdictStyle}`}>{verdict}</div>
            {violationsCount > 0 && <div className="text-xs text-gray-500 mt-1">{violationsCount} violations</div>}
          </div>
          
          {/* Scores */}
          {Object.keys(scores).length > 0 && (
            <div className="space-y-1">
              {Object.entries(scores).slice(0, 6).map(([key, val]: [string, any]) => {
                const score = typeof val === 'object' ? (val.score || val.value || 0) : (parseFloat(String(val)) || 0)
                const pct = Math.round(score * 100)
                return (
                  <div key={key} className="flex items-center justify-between text-sm py-1">
                    <span className="text-gray-500 capitalize">{key.replace(/_/g, ' ')}</span>
                    <div className="flex items-center gap-2">
                      <div className="w-16 h-1 bg-gray-800 rounded overflow-hidden">
                        <div 
                          className={`h-full ${score > 0.6 ? 'bg-red-400' : score > 0.3 ? 'bg-yellow-400' : 'bg-green-400'}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="text-white font-mono w-8 text-right text-xs">{pct}%</span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
          
          {/* Violations */}
          {violations.length > 0 && (
            <div className="space-y-1 pt-2 border-t border-gray-800">
              {violations.slice(0, 3).map((v: any, i: number) => (
                <div key={i} className="flex justify-between text-xs py-1">
                  <span className="text-gray-400 capitalize">{v.criterion}</span>
                  <span className="text-red-400">{((v.score || 0) * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )
    }
    
    case 'report_generation': {
      const summary = data.report_preview || data.report || data.summary
      const reportType = data.report_type || 'generated'
      
      return (
        <div className="space-y-2">
          <div className="text-[10px] text-gray-600">
            Generated via <span className="text-gray-400">{reportType}</span>
          </div>
          {summary ? (
            <div className="prose prose-sm prose-invert max-w-none max-h-48 overflow-y-auto">
              <ReactMarkdown
                components={{
                  h1: ({children}) => <h1 className="text-base font-semibold text-white mb-2">{children}</h1>,
                  h2: ({children}) => <h2 className="text-sm font-medium text-white mb-1.5">{children}</h2>,
                  h3: ({children}) => <h3 className="text-sm font-medium text-gray-300 mb-1">{children}</h3>,
                  p: ({children}) => <p className="text-xs text-gray-400 mb-2 leading-relaxed">{children}</p>,
                  ul: ({children}) => <ul className="text-xs text-gray-400 list-disc list-inside mb-2 space-y-0.5">{children}</ul>,
                  ol: ({children}) => <ol className="text-xs text-gray-400 list-decimal list-inside mb-2 space-y-0.5">{children}</ol>,
                  li: ({children}) => <li className="text-gray-400">{children}</li>,
                  strong: ({children}) => <strong className="text-white font-medium">{children}</strong>,
                  em: ({children}) => <em className="text-gray-300 italic">{children}</em>,
                  code: ({children}) => <code className="text-[10px] bg-gray-800 px-1 py-0.5 rounded text-gray-300">{children}</code>,
                  blockquote: ({children}) => <blockquote className="border-l-2 border-gray-700 pl-2 text-gray-500 italic text-xs">{children}</blockquote>,
                }}
              >
                {summary}
              </ReactMarkdown>
            </div>
          ) : (
            <div className="text-gray-600 text-sm">Report ready</div>
          )}
        </div>
      )
    }
    
    case 'complete': {
      const verdictStyle = data.verdict === 'SAFE' ? 'text-green-400' 
        : data.verdict === 'UNSAFE' ? 'text-red-400' 
        : 'text-yellow-400'
      return (
        <div className="text-center py-4">
          <div className="text-[10px] text-gray-600 uppercase tracking-widest mb-1">Result</div>
          <div className={`text-3xl font-light uppercase ${verdictStyle}`}>{data.verdict || '—'}</div>
          {data.confidence && (
            <div className="text-sm text-gray-500 mt-1">{(data.confidence * 100).toFixed(0)}% confidence</div>
          )}
        </div>
      )
    }
    
    default: {
      // Handle external stages and unknown stages generically
      const status = data._status || data.status
      const isExternal = stageName.startsWith('external_stage_') || data._is_external || data.is_external || data.endpoint_called
      
      if (isExternal || status) {
        return (
          <div className="space-y-3">
            {/* External stage indicator */}
            <div className="flex items-center gap-2 text-purple-400 text-xs">
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                <polyline points="15 3 21 3 21 9" />
                <line x1="10" y1="14" x2="21" y2="3" />
              </svg>
              External Stage Response
              {data.endpoint_called && <span className="text-green-400 ml-1">✓ Called</span>}
            </div>
            
            {/* Show ALL data from the external stage in a formatted way */}
            <div className="space-y-2">
              {Object.entries(data)
                .filter(([k]) => !['stage', 'timestamp', 'is_external', 'endpoint_called', '_status'].includes(k))
                .map(([key, value]) => {
                  // Handle arrays (like violations)
                  if (Array.isArray(value)) {
                    return (
                      <div key={key} className="space-y-1">
                        <div className="text-[10px] text-gray-500 uppercase flex items-center gap-2">
                          {key.replace(/_/g, ' ')}
                          <span className="text-purple-400">({value.length})</span>
                        </div>
                        {value.length > 0 ? (
                          <div className="space-y-1">
                            {value.slice(0, 5).map((item: any, i: number) => (
                              <div key={i} className="text-xs p-2 bg-gray-900/50 rounded border-l-2 border-purple-500/50">
                                {typeof item === 'object' ? (
                                  <div className="space-y-0.5">
                                    {Object.entries(item).slice(0, 6).map(([k, v]) => (
                                      <div key={k} className="flex gap-2">
                                        <span className="text-gray-500 min-w-[80px]">{k}:</span>
                                        <span className={`${
                                          k.includes('severity') && v === 'high' ? 'text-red-400' :
                                          k.includes('severity') && v === 'medium' ? 'text-yellow-400' :
                                          k.includes('confidence') ? 'text-blue-400' : 'text-gray-300'
                                        }`}>
                                          {typeof v === 'number' ? v.toFixed(2) : String(v)}
                                        </span>
                                      </div>
                                    ))}
                                  </div>
                                ) : (
                                  <span className="text-gray-300">{String(item)}</span>
                                )}
                              </div>
                            ))}
                            {value.length > 5 && (
                              <div className="text-[10px] text-gray-500 pl-2">+{value.length - 5} more...</div>
                            )}
                          </div>
                        ) : (
                          <div className="text-xs text-gray-500 italic pl-2">Empty</div>
                        )}
                      </div>
                    )
                  }
                  
                  // Handle objects
                  if (typeof value === 'object' && value !== null) {
                    return (
                      <div key={key} className="space-y-1">
                        <div className="text-[10px] text-gray-500 uppercase">{key.replace(/_/g, ' ')}</div>
                        <div className="text-xs p-2 bg-gray-900/50 rounded">
                          {Object.entries(value).slice(0, 5).map(([k, v]) => (
                            <div key={k} className="flex gap-2 py-0.5">
                              <span className="text-gray-500">{k}:</span>
                              <span className="text-gray-300">{typeof v === 'number' ? v.toFixed(2) : String(v)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )
                  }
                  
                  // Handle primitives (strings, numbers, booleans)
                  return (
                    <div key={key} className="flex items-center justify-between py-1 border-b border-gray-800/30 last:border-0">
                      <span className="text-[10px] text-gray-500 uppercase">{key.replace(/_/g, ' ')}</span>
                      <span className={`text-sm font-medium ${
                        key.includes('verdict') && (value === 'PASS' || value === 'SAFE') ? 'text-green-400' :
                        key.includes('verdict') && (value === 'FAIL' || value === 'UNSAFE') ? 'text-red-400' :
                        key.includes('verdict') ? 'text-yellow-400' :
                        key.includes('confidence') || key.includes('score') ? 'text-blue-400' :
                        'text-white'
                      }`}>
                        {typeof value === 'number' ? value.toFixed(3) : 
                         typeof value === 'boolean' ? (value ? '✓' : '✗') : 
                         String(value)}
                      </span>
                    </div>
                  )
                })}
            </div>
            
            {/* Timestamp if available */}
            {data.timestamp && (
              <div className="text-[9px] text-gray-600 pt-1">
                {new Date(data.timestamp).toLocaleString()}
              </div>
            )}
          </div>
        )
      }
      
      // Fallback for truly unknown stages - show raw JSON
      return (
        <div className="space-y-2">
          <div className="text-[10px] text-gray-500 uppercase">Raw Output</div>
          <pre className="text-xs bg-gray-900/50 p-2 rounded overflow-auto max-h-48 text-gray-300">
            {JSON.stringify(data, null, 2)}
          </pre>
        </div>
      )
    }
  }
}

const Pipeline: FC = () => {
  // Industry Standard: Select each primitive value individually
  // Creating objects in selectors causes infinite re-render loops
  const selectedVideo = useSelectedVideo()
  const queue = useQueue()
  const { 
    addVideos, updateVideo, removeVideo, selectVideo, 
    setProcessingBatch, getVideoById, getVideoByItemId 
  } = useVideoStoreActions()
  
  // Select primitives individually - NOT as an object
  const selectedVideoId = useVideoStore((state) => state.selectedVideoId)
  const processingBatch = useVideoStore((state) => state.processingBatch)
  
  const currentPolicy = useSettingsStore((state) => state.currentPolicy)
  
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [uploadSource, setUploadSource] = useState<'local' | 'url' | 'storage' | 'database'>('local')
  const [urlInput, setUrlInput] = useState('')
  const [videoType, setVideoType] = useState<'labeled' | 'original'>('original')
  const [selectedStage, setSelectedStage] = useState<string | null>(null)
  const [stageOutput, setStageOutput] = useState<any>(null)
  const [stageLoading, setStageLoading] = useState(false)
  const [completedStages, setCompletedStages] = useState<string[]>([])
  const [videoError, setVideoError] = useState(false)
  const [labeledVideoError, setLabeledVideoError] = useState(false)
  const [presets, setPresets] = useState<CriteriaPreset[]>([])
  const [customCriteria, setCustomCriteria] = useState<CriteriaPreset[]>([])
  const [selectedPreset, setSelectedPreset] = useState<string>('child_safety')
  const [availableStages, setAvailableStages] = useState<StageInfo[]>([])
  
  // Compute pipeline stages including external ones, with enabled status
  const PIPELINE_STAGES = useMemo<PipelineStage[]>(() => {
    // Map backend stage types to their enabled status
    const enabledMap: Record<string, boolean> = {}
    availableStages.forEach(s => {
      enabledMap[s.type] = s.enabled
    })
    
    // Add enabled status to default stages
    const stages = DEFAULT_PIPELINE_STAGES.map(stage => ({
      ...stage,
      // Map backendId to check enabled status (some have different names)
      enabled: enabledMap[stage.backendId] !== false,  // Default to true if not in map
    }))
    
    // Add ALL external stages (enabled and disabled) before policy_fusion
    const externalStages = availableStages.filter(s => s.is_external)
    
    if (externalStages.length > 0) {
      const insertIndex = stages.findIndex(s => s.backendId === 'policy_fusion')
      let externalNumber = 9  // Start numbering after text_moderation (08)
      
      externalStages.forEach((ext, idx) => {
        stages.splice(insertIndex + idx, 0, {
          id: ext.type,
          backendId: ext.type,
          name: ext.display_name,  // Use full name from config
          number: String(externalNumber).padStart(2, '0'),
          isExternal: true,
          displayColor: ext.display_color || '#8B5CF6',  // Purple default
          enabled: ext.enabled,
        })
        externalNumber++
      })
      
      // Renumber remaining stages
      for (let i = insertIndex + externalStages.length; i < stages.length; i++) {
        stages[i] = { ...stages[i], number: String(i + 1).padStart(2, '0') }
      }
    }
    
    return stages
  }, [availableStages])
  const [showPresetDropdown, setShowPresetDropdown] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const sseConnectionsRef = useRef<Map<string, EventSource>>(new Map())
  const dataLoadedRef = useRef(false)

  // LocalStorage cache helpers for stage outputs
  const STAGE_CACHE_KEY = 'judex_stage_outputs'
  const STAGE_CACHE_EXPIRY = 24 * 60 * 60 * 1000 // 24 hours

  const getCachedStageOutput = (videoId: string, stageName: string): any | null => {
    try {
      const cache = JSON.parse(localStorage.getItem(STAGE_CACHE_KEY) || '{}')
      const key = `${videoId}:${stageName}`
      const entry = cache[key]
      if (entry && Date.now() - entry.timestamp < STAGE_CACHE_EXPIRY) {
        return entry.data
      }
      return null
    } catch {
      return null
    }
  }

  const setCachedStageOutput = (videoId: string, stageName: string, data: any) => {
    try {
      const cache = JSON.parse(localStorage.getItem(STAGE_CACHE_KEY) || '{}')
      const key = `${videoId}:${stageName}`
      cache[key] = { data, timestamp: Date.now() }
      // Clean old entries (keep last 100)
      const entries = Object.entries(cache)
      if (entries.length > 100) {
        const sorted = entries.sort((a: any, b: any) => b[1].timestamp - a[1].timestamp)
        const cleaned = Object.fromEntries(sorted.slice(0, 100))
        localStorage.setItem(STAGE_CACHE_KEY, JSON.stringify(cleaned))
      } else {
        localStorage.setItem(STAGE_CACHE_KEY, JSON.stringify(cache))
      }
    } catch {
      // Ignore localStorage errors
    }
  }

  // Load saved results, checkpoints, and criteria presets on mount
  useEffect(() => {
    // Prevent double-loading in React StrictMode
    if (dataLoadedRef.current) return
    dataLoadedRef.current = true
    
    const loadData = async () => {
      try {
        // Load criteria presets, custom criteria, and available stages
        const [presetsRes, customRes, stagesRes] = await Promise.all([
          api.get('/criteria/presets').catch(() => ({ data: [] })),
          api.get('/criteria/custom').catch(() => ({ data: [] })),
          stagesApi.list().catch(() => ({ stages: [] }))
        ])
        setPresets(presetsRes.data || [])
        setCustomCriteria(customRes.data || [])
        setAvailableStages(stagesRes.stages || [])

        // Load recent evaluations and add completed/processing ones to the queue
        const { evaluations } = await evaluationApi.list(20)
        
        // Get current queue state to check for existing items
        const currentQueue = useVideoStore.getState().queue
        const existingItemIds = new Set(currentQueue.map(v => v.itemId).filter(Boolean))
        const existingEvalIds = new Set(currentQueue.map(v => v.evaluationId).filter(Boolean))
        
        // Collect all videos to add (batch add to avoid multiple re-renders)
        const videosToAdd: Omit<QueueVideo, 'id' | 'uploadedAt'>[] = []
        
        // Fetch full details for each evaluation to get items with results
        for (const evalSummary of evaluations) {
          if (evalSummary.status !== 'completed' && evalSummary.status !== 'processing') continue
          
          // Skip if we already have this evaluation in queue
          if (existingEvalIds.has(evalSummary.id)) continue
          
          try {
            const evaluation = await evaluationApi.get(evalSummary.id)
            if (!evaluation.items?.length) continue
            
            evaluation.items.forEach((item: any) => {
              // Skip if already in queue
              if (existingItemIds.has(item.id)) return
              
              videosToAdd.push({
                filename: item.filename,
                file: null,
                status: item.status || evaluation.status,
                source: (item.source_type || 'upload') as 'local' | 'url' | 'storage',
                progress: item.progress || (evaluation.status === 'completed' ? 100 : 0),
                currentStage: item.current_stage || (evaluation.status === 'completed' ? 'report_generation' : undefined),
                verdict: item.result?.verdict,
                result: item.result,
                evaluationId: evaluation.id,
                itemId: item.id,
              })
            })
          } catch (e) {
            console.warn(`Failed to load evaluation ${evalSummary.id}:`, e)
          }
        }
        
        // Add all videos at once
        if (videosToAdd.length > 0) {
          addVideos(videosToAdd)
        }
      } catch (error) {
        console.error('Error loading data:', error)
      }
    }
    loadData()
  }, [])

  // Auto-select first video
  useEffect(() => {
    if (!selectedVideoId && queue.length > 0) {
      const processing = queue.find(v => v.status === 'processing')
      const completed = queue.find(v => v.status === 'completed')
      selectVideo((processing || completed || queue[queue.length - 1]).id)
    }
  }, [queue, selectedVideoId, selectVideo])

  // Ref to track pending updates for batching (prevents flickering)
  const pendingUpdatesRef = useRef<Map<string, any>>(new Map())
  const updateTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  
  // Batch video updates to reduce re-renders (prevents flickering)
  const batchedUpdateVideo = useCallback((videoId: string, updates: any) => {
    // Merge with any pending updates for this video
    const existing = pendingUpdatesRef.current.get(videoId) || {}
    pendingUpdatesRef.current.set(videoId, { ...existing, ...updates })
    
    // Clear existing timeout
    if (updateTimeoutRef.current) {
      clearTimeout(updateTimeoutRef.current)
    }
    
    // Batch updates with 50ms debounce
    updateTimeoutRef.current = setTimeout(() => {
      pendingUpdatesRef.current.forEach((update, vid) => {
        updateVideo(vid, update)
      })
      pendingUpdatesRef.current.clear()
    }, 50)
  }, [updateVideo])

  // SSE connection with retry - evaluationId is used for SSE, queueVideoId is for fallback updates
  const connectSSE = useCallback((evaluationId: string, queueVideoId: string, retryCount = 0) => {
    const maxRetries = 3
    const existing = sseConnectionsRef.current.get(evaluationId)
    if (existing) existing.close()

    const eventSource = createSSEConnection(evaluationId)
    sseConnectionsRef.current.set(evaluationId, eventSource)

    eventSource.onmessage = (event) => {
      try {
        const update = JSON.parse(event.data)
        
        // Find the video to update - SSE may include item_id for batch updates
        let targetVideoId = queueVideoId
        if (update.item_id) {
          // Find queue video by itemId (which maps to item_id from SSE)
          const found = queue.find(v => v.itemId === update.item_id)
          if (found) targetVideoId = found.id
        }
        
        const video = getVideoById(targetVideoId)
        if (!video) return

        let progress = 0
        if (update.stage) {
          // Use computed progress that includes external stages
          const baseProgress = getStageProgress(update.stage, PIPELINE_STAGES)
          const stageIndex = PIPELINE_STAGES.findIndex(s => s.id === update.stage || s.backendId === update.stage)
          if (stageIndex >= 0) {
            const nextStageIndex = stageIndex + 1
            const nextProgress = nextStageIndex < PIPELINE_STAGES.length 
              ? getStageProgress(PIPELINE_STAGES[nextStageIndex].id, PIPELINE_STAGES) 
              : 100
            const range = nextProgress - baseProgress
            const normalizedProgress = update.progress > 1 ? update.progress / 100 : update.progress
            progress = Math.round(baseProgress + (normalizedProgress * range))
          }
        }

        // Use batched update to prevent flickering
        batchedUpdateVideo(targetVideoId, {
          currentStage: update.stage,
          progress: Math.min(progress, 100),
          statusMessage: update.message,
          status: update.stage === 'complete' || (update.stage === 'report' && progress >= 100) ? 'completed' : 'processing'
        })

        // Close SSE when evaluation is complete (not just one item)
        if (update.evaluation_complete || (update.stage === 'complete' && !update.item_id)) {
          eventSource.close()
          sseConnectionsRef.current.delete(evaluationId)
        }
      } catch (e) {
        console.error('SSE parse error:', e)
      }
    }

    eventSource.onerror = () => {
      eventSource.close()
      sseConnectionsRef.current.delete(evaluationId)
      const video = getVideoById(queueVideoId)
      if (video && video.status === 'processing' && retryCount < maxRetries) {
        setTimeout(() => connectSSE(evaluationId, queueVideoId, retryCount + 1), 2000 * (retryCount + 1))
      }
    }
  }, [getVideoById, updateVideo, queue])

  const handleFileSelect = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    const fileArray = Array.from(files).filter(f => f.type.startsWith('video/') || f.name.match(/\.(mp4|avi|mov|mkv|webm)$/i))
    if (fileArray.length === 0) { toast.error('Please select valid video files'); return }

    const ids = addVideos(fileArray.map(file => ({
      filename: file.name, file, status: 'queued' as VideoStatus, source: 'local', progress: 0,
    })))
    toast.success(`Added ${fileArray.length} video(s)`)
    setShowUploadModal(false)
    if (ids.length > 0) selectVideo(ids[0])
  }

  const handleUrlImport = async () => {
    const urls = urlInput.split('\n').filter(u => u.trim())
    if (urls.length === 0) { toast.error('Please enter at least one URL'); return }
    const ids = addVideos(urls.map(url => ({
      filename: url.split('/').pop() || 'video.mp4', file: null, status: 'queued' as VideoStatus, source: 'url', progress: 0,
    })))
    toast.success(`Added ${urls.length} video(s) from URLs`)
    setUrlInput(''); setShowUploadModal(false)
    if (ids.length > 0) selectVideo(ids[0])
  }

  const processSingleVideo = async (videoId: string) => {
    const video = getVideoById(videoId)
    if (!video || !video.file) { toast.error('Video file not available'); return }
    updateVideo(videoId, { status: 'processing', currentStage: 'ingest_video', progress: 0 })

    try {
      const response = await evaluationApi.create({ 
        files: [video.file], 
        criteriaId: selectedPreset || undefined,
        async: true 
      })
      if (response.items?.[0]) {
        const item = response.items[0]
        updateVideo(videoId, { itemId: item.id, evaluationId: response.id })
        // SSE uses evaluation_id, not video_id
        connectSSE(response.id, videoId)
        pollEvaluationStatus(response.id)
      }
    } catch (error: any) {
      updateVideo(videoId, { status: 'failed', error: error.message })
      toast.error('Failed to process video')
    }
  }

  const processAllVideos = async () => {
    const videosToProcess = queue.filter(v => v.status !== 'completed' && v.status !== 'processing' && v.file)
    if (videosToProcess.length === 0) { toast.error('No videos to process'); return }
    setProcessingBatch(true)

    try {
      const files = videosToProcess.map(v => v.file!).filter(Boolean)
      const response = await evaluationApi.create({ 
        files, 
        criteriaId: selectedPreset || undefined,
        async: true 
      })
      const evaluationId = response.id
      response.items?.forEach((item: any) => {
        const queueVideo = queue.find(v => v.filename === item.filename)
        if (queueVideo) {
          updateVideo(queueVideo.id, { itemId: item.id, evaluationId, status: 'processing' })
        }
      })
      // SSE uses evaluation_id for all items
      connectSSE(evaluationId, videosToProcess[0]?.id || '')
      pollEvaluationStatus(evaluationId)
    } catch (error: any) {
      toast.error('Failed to start batch processing'); setProcessingBatch(false)
    }
  }

  const pollEvaluationStatus = (evaluationId: string) => {
    const interval = setInterval(async () => {
      try {
        const data = await evaluationApi.get(evaluationId)
        if (data.items) {
          data.items.forEach((item: any) => {
            const qv = getVideoByItemId(item.id) || queue.find(v => v.filename === item.filename)
            if (qv) {
              updateVideo(qv.id, {
                status: item.status as VideoStatus, 
                progress: item.progress || 0, 
                verdict: item.result?.verdict,
                error: item.error_message || undefined, 
                result: item.result,
                duration: item.result?.processing_time ? `${item.result.processing_time.toFixed(1)}s` : undefined
              })
            }
          })
        }
        if (data.status === 'completed') {
          clearInterval(interval); setProcessingBatch(false)
          // Results are now saved automatically by the backend
        }
      } catch { clearInterval(interval); setProcessingBatch(false) }
    }, 2000)
  }

  const retryVideo = async (videoId: string) => {
    const video = getVideoById(videoId)
    if (!video) return
    if (!video.file && video.evaluationId && video.itemId) {
      try {
        // Fetch original video from evaluation artifacts
        const url = evaluationsApi.getUploadedVideoUrl(video.evaluationId, video.itemId)
        const response = await fetch(url)
        const blob = await response.blob()
        const file = new File([blob], video.filename, { type: 'video/mp4' })
        updateVideo(videoId, { file, status: 'queued', error: undefined })
      } catch { toast.error('Cannot retry: original file not available'); return }
    }
    updateVideo(videoId, { status: 'queued', progress: 0, error: undefined })
    await processSingleVideo(videoId)
  }

  // Delete video from queue and backend
  const handleDeleteVideo = async (videoId: string, video: QueueVideo) => {
    // Remove from local store first
    removeVideo(videoId)
    
    // Delete from backend if it has an evaluation ID
    if (video.evaluationId) {
      try {
        await evaluationsApi.delete(video.evaluationId)
      } catch (e) {
        // Ignore if not found - might be local-only
      }
    }
    toast.success('Video deleted')
  }

  // Reprocess a completed video with current stage settings
  const handleReprocessVideo = async (videoId: string, video: QueueVideo) => {
    if (!video.evaluationId) {
      toast.error('Cannot reprocess - no evaluation ID')
      return
    }
    
    try {
      // Reset the video status to processing
      updateVideo(videoId, { 
        status: 'processing' as VideoStatus, 
        progress: 0,
        result: undefined,
      })
      
      // Clear cached stage outputs
      try {
        const cache = JSON.parse(localStorage.getItem(STAGE_CACHE_KEY) || '{}')
        Object.keys(cache).forEach(key => {
          if (key.startsWith(videoId)) delete cache[key]
        })
        localStorage.setItem(STAGE_CACHE_KEY, JSON.stringify(cache))
      } catch { /* ignore */ }
      
      // Clear selected stage output
      setSelectedStage(null)
      setStageOutput(null)
      setCompletedStages([])
      
      // Call reprocess API (skips ingest/segment stages)
      const result = await evaluationApi.reprocess(video.evaluationId, true)
      toast.success(`Reprocessing started (skipping ingest/segment)`)
      
      // Setup SSE to track progress
      connectSSE(video.evaluationId, videoId)
      pollEvaluationStatus(video.evaluationId)
      
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Reprocess failed'
      toast.error(message)
      
      // Reset status on failure
      updateVideo(videoId, { 
        status: 'failed' as VideoStatus,
      })
    }
  }

  // Clear all videos from queue and backend
  const handleClearAll = async () => {
    if (!confirm('Delete all videos from queue and saved results?')) return
    
    // Get all evaluation IDs before clearing
    const evaluationIds = new Set(queue.filter(v => v.evaluationId).map(v => v.evaluationId!))
    
    // Clear local store
    queue.forEach(v => removeVideo(v.id))
    
    // Delete all evaluations from backend
    for (const evalId of evaluationIds) {
      try {
        await evaluationsApi.delete(evalId)
      } catch (e) {
        // Continue even if some fail
      }
    }
    
    toast.success('All videos cleared')
  }
  
  // Memoize video URLs to prevent flickering on re-renders
  const videoUrls = useMemo(() => {
    if (!selectedVideo) return { original: null, labeled: null }
    
    const evaluationId = selectedVideo.evaluationId
    const itemId = selectedVideo.itemId
    
    // Original video: local file blob URL or backend URL
    let originalUrl: string | null = null
    if (selectedVideo.file) {
      originalUrl = URL.createObjectURL(selectedVideo.file)
    } else if (evaluationId && itemId) {
      originalUrl = evaluationsApi.getUploadedVideoUrl(evaluationId, itemId)
    }
    
    // Labeled video: always from backend
    let labeledUrl: string | null = null
    if (evaluationId && itemId) {
      labeledUrl = evaluationsApi.getLabeledVideoUrl(evaluationId, itemId)
    }
    
    return { original: originalUrl, labeled: labeledUrl }
  }, [selectedVideo?.id, selectedVideo?.file, selectedVideo?.evaluationId, selectedVideo?.itemId])
  
  // Cleanup blob URL on unmount or video change
  useEffect(() => {
    return () => {
      if (videoUrls.original?.startsWith('blob:')) {
        URL.revokeObjectURL(videoUrls.original)
      }
    }
  }, [videoUrls.original])

  // Fetch stage output from backend with localStorage caching
  const fetchStageOutput = async (evaluationId: string, stageName: string, itemId?: string) => {
    setStageLoading(true)
    
    // Use itemId for caching if available, otherwise evaluationId
    const cacheKey = itemId || evaluationId
    
    // Check localStorage cache first
    const cached = getCachedStageOutput(cacheKey, stageName)
    if (cached) {
      console.log('Using cached stage output for:', stageName)
      setStageOutput(cached)
      setStageLoading(false)
      return
    }
    
    try {
      // Use new evaluation API with evaluationId and itemId
      const output = await stageApi.getStageOutput(evaluationId, stageName, itemId)
      if (output && Object.keys(output).length > 0) {
        // Cache the result
        setCachedStageOutput(cacheKey, stageName, output)
        setStageOutput(output)
        setStageLoading(false)
        return
      }
    } catch (error) {
      console.log('Stage output fetch failed, using fallback:', stageName)
    }
    
    // Fallback: derive stage data from video result
    if (selectedVideo?.result) {
      console.log('Deriving stage output from result for:', stageName)
      const derivedOutput = deriveStageOutputFromResult(stageName, selectedVideo.result)
      // Cache the derived output too
      setCachedStageOutput(cacheKey, stageName, derivedOutput)
      setStageOutput(derivedOutput)
    } else {
      console.log('No result data available for fallback')
      setStageOutput(null)
    }
    setStageLoading(false)
  }
  
  // Helper to safely convert evidence to array
  const toArray = (data: any): any[] => {
    if (!data) return []
    if (Array.isArray(data)) return data
    if (typeof data === 'object') {
      // Handle objects with items/texts/results arrays
      if (Array.isArray(data.items)) return data.items
      if (Array.isArray(data.texts)) return data.texts
      if (Array.isArray(data.results)) return data.results
      if (Array.isArray(data.detections)) return data.detections
      // Single object - wrap in array
      return [data]
    }
    return []
  }
  
  // Derive stage-specific output from overall result (for older videos without checkpoint data)
  const deriveStageOutputFromResult = (stageName: string, result: any) => {
    const evidence = result.evidence || {}
    const metadata = result.metadata || {}
    
    // Safely get arrays from evidence
    const visionData = toArray(evidence.vision)
    const yoloworldData = toArray(evidence.yoloworld)
    const violenceData = toArray(evidence.violence_segments || evidence.violence)
    const ocrData = toArray(evidence.ocr)
    const transcriptMod = toArray(evidence.transcript_moderation)
    const ocrMod = toArray(evidence.ocr_moderation)
    
    switch (stageName) {
      case 'ingest':
        return {
          stage: 'ingest',
          duration: metadata.duration,
          fps: metadata.fps,
          width: metadata.width,
          height: metadata.height,
          has_audio: metadata.has_audio
        }
      case 'segment':
        return {
          stage: 'segment',
          frames_extracted: metadata.frames_analyzed || 0,
          segments_created: metadata.segments_analyzed || 0
        }
      case 'yolo26':
        return {
          stage: 'yolo26',
          detections: visionData,
          total_detections: visionData.length
        }
      case 'yoloworld':
        return {
          stage: 'yoloworld',
          detections: yoloworldData,
          total_detections: yoloworldData.length
        }
      case 'violence':
        return {
          stage: 'violence',
          violence_segments: violenceData
        }
      case 'audio_asr':
        return {
          stage: 'audio_asr',
          full_text: result.transcript?.text || evidence.transcription?.text || '',
          chunks: toArray(result.transcript?.chunks || evidence.transcription?.chunks)
        }
      case 'ocr':
        return {
          stage: 'ocr',
          texts: ocrData.map((o: any) => typeof o === 'string' ? o : (o.text || o.content || '')),
          total_detections: ocrData.length
        }
      case 'text_moderation':
        return {
          stage: 'text_moderation',
          transcript_chunks_analyzed: toArray(result.transcript?.chunks).length,
          ocr_items_analyzed: ocrData.length,
          flagged_transcript: transcriptMod,
          flagged_ocr: ocrMod
        }
      case 'policy_fusion':
        return {
          stage: 'policy_fusion',
          verdict: result.verdict,
          scores: Object.fromEntries(
            Object.entries(result.criteria || {}).map(([k, v]: [string, any]) => [k, v?.score || v?.value || v || 0])
          ),
          violations: toArray(result.violations)
        }
      case 'report':
        return {
          stage: 'report',
          report_preview: result.report || result.summary,
          report_type: 'saved'
        }
      // 'finalize' stage removed - results shown in report stage or results panel
      default:
        return result
    }
  }

  // Handle stage click - fetch stage output using evaluation API
  const handleStageClick = async (stageId: string) => {
    if (selectedStage === stageId) {
      setSelectedStage(null)
      setStageOutput(null)
      return
    }
    
    setSelectedStage(stageId)
    
    // Use evaluationId for API call, itemId for specific item within batch
    const evaluationId = selectedVideo?.evaluationId
    const itemId = selectedVideo?.itemId
    const stage = PIPELINE_STAGES.find(s => s.id === stageId)
    
    if (evaluationId && stage) {
      await fetchStageOutput(evaluationId, stage.backendId, itemId)
    } else if (selectedVideo?.result) {
      // Fallback to result data if no evaluationId available
      setStageOutput(selectedVideo.result)
    }
  }

  // Check if a specific stage has completed (for progressive content display)
  const isStageComplete = (stageId: string, video: QueueVideo | null): boolean => {
    if (!video) return false
    if (video.status === 'completed') return true
    if (video.status !== 'processing') return false
    
    const stageIndex = PIPELINE_STAGES.findIndex(s => s.id === stageId)
    const currentIndex = PIPELINE_STAGES.findIndex(s => s.id === video.currentStage)
    return stageIndex < currentIndex
  }
  
  // Video is available after ingest completes
  const isVideoAvailable = (video: QueueVideo | null): boolean => {
    if (!video) return false
    if (video.status === 'completed') return true
    // Video is uploaded during ingest, available after ingest completes
    return isStageComplete('ingest_video', video) || Boolean(video.file)
  }
  
  // Frames are available after segment completes
  const isFramesAvailable = (video: QueueVideo | null): boolean => {
    if (!video) return false
    if (video.status === 'completed') return true
    // Frames are extracted during segment, available after segment completes
    return isStageComplete('segment_video', video)
  }
  
  // Labeled video is available after YOLO26 vision stage completes (annotations are drawn)
  const isLabeledVideoAvailable = (video: QueueVideo | null): boolean => {
    if (!video) return false
    if (video.status === 'completed') return true
    // Labeled video is generated during yolo26_vision stage
    return isStageComplete('yolo26_vision', video)
  }

  // Note: Video URLs are now computed inline in the JSX to properly handle
  // local file vs backend URL fallback (matching index.html behavior)

  return (
    <div className="h-full flex flex-col bg-black text-white overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-4">
          <span className="text-xs text-gray-500 tracking-widest">VIDEO EVALUATOR</span>
          {/* Criteria Selector */}
          <div className="relative">
            <button 
              onClick={() => setShowPresetDropdown(!showPresetDropdown)}
              className="flex items-center gap-2 px-3 py-1.5 text-xs border border-gray-700 hover:border-white transition-all"
            >
              <span className="text-gray-400">Criteria:</span>
              <span className="text-white font-medium">
                {[...presets, ...customCriteria].find(p => p.id === selectedPreset)?.name || selectedPreset}
              </span>
              <ChevronDown size={12} className={`transition-transform ${showPresetDropdown ? 'rotate-180' : ''}`} />
            </button>
            {showPresetDropdown && (
              <div className="absolute top-full left-0 mt-1 bg-gray-900 border border-gray-700 shadow-xl z-50 min-w-[220px] max-h-80 overflow-y-auto">
                {presets.length > 0 && (
                  <>
                    <div className="px-3 py-1.5 text-[9px] text-gray-500 uppercase tracking-wider border-b border-gray-800">
                      Built-in Presets
                    </div>
                    {presets.map(preset => (
                      <button
                        key={preset.id}
                        onClick={() => { setSelectedPreset(preset.id); setShowPresetDropdown(false) }}
                        className={`w-full px-3 py-2 text-left text-xs hover:bg-gray-800 flex items-center justify-between ${
                          selectedPreset === preset.id ? 'bg-gray-800 text-white' : 'text-gray-400'
                        }`}
                      >
                        <div>
                          <div className="font-medium">{preset.name}</div>
                          <div className="text-[10px] text-gray-600">{preset.criteria_count} criteria</div>
                        </div>
                        {selectedPreset === preset.id && <Check size={12} className="text-green-400" />}
                      </button>
                    ))}
                  </>
                )}
                {customCriteria.length > 0 && (
                  <>
                    <div className="px-3 py-1.5 text-[9px] text-gray-500 uppercase tracking-wider border-b border-gray-800 mt-1">
                      Custom Criteria
                    </div>
                    {customCriteria.map(c => (
                      <button
                        key={c.id}
                        onClick={() => { setSelectedPreset(c.id); setShowPresetDropdown(false) }}
                        className={`w-full px-3 py-2 text-left text-xs hover:bg-gray-800 flex items-center justify-between ${
                          selectedPreset === c.id ? 'bg-gray-800 text-white' : 'text-gray-400'
                        }`}
                      >
                        <div>
                          <div className="font-medium">{c.name}</div>
                          <div className="text-[10px] text-gray-600">{c.criteria_count} criteria</div>
                        </div>
                        {selectedPreset === c.id && <Check size={12} className="text-green-400" />}
                      </button>
                    ))}
                  </>
                )}
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowUploadModal(true)} className="p-1.5 border border-gray-700 hover:border-white transition-all" title="Add Video"><Plus size={16} /></button>
          {queue.length > 0 && (
            <button onClick={handleClearAll} className="p-1.5 border border-gray-700 hover:border-red-500 hover:text-red-500 transition-all" title="Clear All">
              <Trash2 size={16} />
            </button>
          )}
          <button onClick={processAllVideos} disabled={processingBatch || queue.filter(v => v.status === 'queued' && v.file).length === 0} className="btn text-xs flex items-center gap-1.5 py-1.5 px-3">
            {processingBatch ? <><Loader2 size={12} className="animate-spin" /> PROCESSING</> : <><Play size={12} /> EVALUATE</>}
          </button>
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        {/* File Tree */}
        <div className="w-56 border-r border-gray-800 flex flex-col flex-shrink-0">
          <div className="flex-1 overflow-y-auto">
            {queue.length === 0 ? (
              <div className="p-4 text-center text-gray-700"><Upload size={20} className="mx-auto mb-1" /><p className="text-[10px]">Add videos</p></div>
            ) : (
              <div className="p-1">
                {queue.map(video => (
                  <div key={video.id} onClick={() => { selectVideo(video.id); setSelectedStage(null); setStageOutput(null); setVideoError(false); setLabeledVideoError(false) }}
                    className={`p-2 cursor-pointer text-xs flex items-center justify-between group ${selectedVideoId === video.id ? 'bg-gray-900 border-l-2 border-white' : 'hover:bg-gray-900/50 border-l-2 border-transparent'}`}>
                    <span className="truncate flex-1 text-gray-400" title={video.filename}>{video.filename}</span>
                    <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100">
                      {video.status === 'queued' && <button onClick={(e) => { e.stopPropagation(); processSingleVideo(video.id) }} className="p-0.5 text-green-500" title="Process"><Play size={10} /></button>}
                      {video.status === 'failed' && <button onClick={(e) => { e.stopPropagation(); retryVideo(video.id) }} className="p-0.5 text-yellow-500" title="Retry"><RotateCcw size={10} /></button>}
                      {video.status === 'completed' && <button onClick={(e) => { e.stopPropagation(); handleReprocessVideo(video.id, video) }} className="p-0.5 text-blue-400 hover:text-blue-300" title="Reprocess with current stage settings"><RotateCcw size={10} /></button>}
                      <button onClick={(e) => { e.stopPropagation(); handleDeleteVideo(video.id, video) }} className="p-0.5 text-red-500 hover:text-red-400" title="Delete"><X size={10} /></button>
                    </div>
                    {video.status === 'processing' && <Loader2 size={10} className="animate-spin text-blue-400 ml-1" />}
                    {video.status === 'completed' && <Check size={10} className="text-green-400 ml-1" />}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Pipeline View */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {selectedVideo ? (
            <>
              {/* Stages - Industry standard: Separate component with granular subscriptions */}
              <PipelineStages
                stages={PIPELINE_STAGES}
                selectedStage={selectedStage}
                onStageClick={handleStageClick}
              />

              {/* Content */}
              <div className="flex-1 grid grid-cols-2 gap-2 p-2 overflow-hidden">
                {/* Video + Frames Container */}
                <div className="flex flex-col bg-gray-900 border border-gray-800 overflow-hidden">
                  {/* Video Player Header */}
                  <div className="p-1.5 border-b border-gray-800 flex items-center justify-between">
                    <span className="text-[9px] text-gray-500 uppercase">
                      {videoType === 'labeled' ? 'Labeled' : 'Original'}
                    </span>
                    {/* Show toggle when video is available - labeled may still be loading */}
                    {isVideoAvailable(selectedVideo) && (
                      <div className="flex text-[9px]">
                        <button onClick={() => { setVideoType('labeled'); setVideoError(false); setLabeledVideoError(false) }} className={`px-1.5 py-0.5 ${videoType === 'labeled' ? 'bg-white text-black' : 'text-gray-600'}`}>LAB</button>
                        <button onClick={() => { setVideoType('original'); setVideoError(false); setLabeledVideoError(false) }} className={`px-1.5 py-0.5 ${videoType === 'original' ? 'bg-white text-black' : 'text-gray-600'}`}>ORI</button>
                      </div>
                    )}
                  </div>
                  
                  {/* Video Player - Show as soon as video is available (after ingest) */}
                  <div className="flex-shrink-0 bg-black flex items-center justify-center" style={{ minHeight: '180px', maxHeight: '280px' }}>
                    {isVideoAvailable(selectedVideo) ? (
                      // Original video error
                      videoType === 'original' && videoError ? (
                        <div className="text-center text-gray-600 p-4">
                          <Video size={24} className="mx-auto mb-2 opacity-50" />
                          <p className="text-xs">Video not available</p>
                        </div>
                      ) : 
                      // Labeled video error or not available
                      videoType === 'labeled' && (labeledVideoError || !isLabeledVideoAvailable(selectedVideo)) ? (
                        <div className="text-center text-gray-600 p-4">
                          <Video size={24} className="mx-auto mb-2 opacity-50" />
                          <p className="text-xs">
                            {labeledVideoError ? 'Video not available' : 'Generating labeled video...'}
                          </p>
                          <button 
                            onClick={() => { setVideoType('original'); setLabeledVideoError(false) }} 
                            className="text-blue-400 text-xs mt-2 underline"
                          >
                            View original
                          </button>
                        </div>
                      ) : (
                        (() => {
                          // Use memoized video URLs to prevent flickering
                          const videoSrc = videoType === 'original' ? videoUrls.original : videoUrls.labeled
                          
                          if (!videoSrc) {
                            return (
                              <div className="text-center text-gray-600 p-4">
                                <Video size={24} className="mx-auto mb-2 opacity-50" />
                                <p className="text-xs">Video not available</p>
                              </div>
                            )
                          }
                          
                          return (
                            <video 
                              controls 
                              className="max-w-full max-h-full" 
                              key={`video-${selectedVideo.itemId || selectedVideo.id}-${videoType}`}
                              src={videoSrc}
                              onError={() => {
                                if (videoType === 'labeled') {
                                  console.log('Labeled video failed to load')
                                  setLabeledVideoError(true)
                                } else {
                                  setVideoError(true)
                                }
                              }}
                            />
                          )
                        })()
                      )
                    ) : selectedVideo.status === 'processing' ? (
                      <div className="text-center">
                        <Loader2 size={24} className="mx-auto mb-1 animate-spin text-gray-700" />
                        <p className="text-[10px] text-gray-600">
                          {selectedVideo.currentStage === 'ingest_video' ? 'Uploading video...' : `${selectedVideo.progress}%`}
                        </p>
                      </div>
                    ) : <Video size={24} className="text-gray-800" />}
                  </div>
                  
                  {/* Processed Frames Gallery - Show as soon as segmentation completes */}
                  {isFramesAvailable(selectedVideo) && selectedVideo.evaluationId && selectedVideo.itemId && (
                    <div className="flex-1 overflow-y-auto border-t border-gray-800 p-1 bg-black">
                      <ProcessedFrames
                        evaluationId={selectedVideo.evaluationId}
                        itemId={selectedVideo.itemId}
                      />
                    </div>
                  )}
                  {/* Show loading indicator during segmentation */}
                  {selectedVideo.status === 'processing' && selectedVideo.currentStage === 'segment_video' && (
                    <div className="flex-shrink-0 border-t border-gray-800 p-2 bg-black">
                      <div className="flex items-center gap-2 text-gray-500 text-xs">
                        <Loader2 size={12} className="animate-spin" />
                        <span>Extracting frames...</span>
                      </div>
                    </div>
                  )}
                </div>

                {/* Stage Output */}
                <div className="flex flex-col bg-gray-900 border border-gray-800 overflow-hidden">
                  <div className="p-1.5 border-b border-gray-800 flex items-center justify-between">
                    <span className="text-[9px] text-gray-500 uppercase">{selectedStage ? PIPELINE_STAGES.find(s => s.id === selectedStage)?.name : 'Results'}</span>
                    {selectedStage && <button onClick={() => { setSelectedStage(null); setStageOutput(null) }} className="text-[9px] text-gray-600 hover:text-white">← Back</button>}
                  </div>
                  <div className="flex-1 overflow-y-auto p-2">
                    {selectedStage && stageLoading ? (
                      <div className="text-center py-6">
                        <Loader2 size={20} className="mx-auto mb-1 animate-spin text-blue-400" />
                        <p className="text-[10px] text-gray-600">Loading stage output...</p>
                      </div>
                    ) : selectedStage && stageOutput ? (
                      generateStageContent(selectedStage, stageOutput)
                    ) : selectedVideo.status === 'completed' && selectedVideo.result ? (
                      <div className="space-y-2">
                        {/* Verdict */}
                        <div className={`p-3 border text-center ${
                          selectedVideo.verdict === 'SAFE' ? 'border-green-700 bg-green-900/20' :
                          selectedVideo.verdict === 'CAUTION' ? 'border-yellow-700 bg-yellow-900/20' :
                          selectedVideo.verdict === 'UNSAFE' ? 'border-red-700 bg-red-900/20' : 'border-blue-700 bg-blue-900/20'
                        }`}>
                          <div className="text-xl font-bold">{selectedVideo.verdict}</div>
                          <div className="text-[10px] text-gray-500">
                            {((selectedVideo.result.confidence || 0) * 100).toFixed(0)}% confidence
                            {(selectedVideo.result as any).spec_id && <span className="ml-2">• {(selectedVideo.result as any).spec_id}</span>}
                          </div>
                        </div>
                        
                        {/* Dynamic Criteria / Violations */}
                        {(selectedVideo.result.criteria_scores || (selectedVideo.result as any).criteria || selectedVideo.result.violations) && (
                          <div className="grid grid-cols-2 gap-1">
                            {/* Use criteria_scores first, fall back to criteria or violations */}
                            {(() => {
                              const criteriaData = selectedVideo.result.criteria_scores || 
                                                   (selectedVideo.result as any).criteria ||
                                                   selectedVideo.result.violations?.reduce((acc: any, v: any) => {
                                                     acc[v.criterion] = { score: v.score, status: v.severity }
                                                     return acc
                                                   }, {})
                              if (!criteriaData) return null
                              return Object.entries(criteriaData).map(([key, val]: [string, any]) => {
                                const score = typeof val === 'object' ? (val.score || val.value || 0) : (parseFloat(val) || 0)
                                const status = typeof val === 'object' ? (val.status || val.verdict) : undefined
                                const borderColor = status === 'violation' || status === 'critical' ? 'border-red-600' :
                                                    status === 'caution' || status === 'high' ? 'border-yellow-600' :
                                                    score > 0.6 ? 'border-red-600' :
                                                    score > 0.3 ? 'border-yellow-600' : 'border-gray-800'
                                return (
                                  <div key={key} className={`bg-black p-2 border ${borderColor}`}>
                                    <div className="text-[9px] text-gray-600 uppercase truncate" title={key}>{key}</div>
                                    <div className={`text-sm font-medium ${
                                      status === 'violation' || status === 'critical' || score > 0.6 ? 'text-red-400' :
                                      status === 'caution' || status === 'high' || score > 0.3 ? 'text-yellow-400' : ''
                                    }`}>
                                      {(score * 100).toFixed(0)}%
                                    </div>
                                  </div>
                                )
                              })
                            })()}
                          </div>
                        )}
                        
                        {/* Explanation */}
                        {(selectedVideo.result as any).explanation && (
                          <div className="bg-gray-900 p-2 border-l-2 border-blue-500">
                            <div className="flex items-center gap-1 mb-1">
                              <Info size={10} className="text-blue-400" />
                              <span className="text-[9px] text-blue-400">Explanation</span>
                            </div>
                            <p className="text-[10px] text-gray-400">{(selectedVideo.result as any).explanation?.summary || (selectedVideo.result as any).explanation}</p>
                          </div>
                        )}
                        
                        {/* Detectors Used */}
                        {(selectedVideo.result as any).metadata?.detectors_run && (
                          <div className="text-[9px] text-gray-600">
                            Detectors: {(selectedVideo.result as any).metadata.detectors_run.join(', ')}
                          </div>
                        )}
                        
                        <p className="text-[9px] text-gray-600 text-center">Click any completed stage above to see its output</p>
                      </div>
                    ) : selectedVideo.status === 'processing' ? (
                      <div className="text-center py-6"><Loader2 size={20} className="mx-auto mb-1 animate-spin text-gray-700" /><p className="text-[10px] text-gray-600">{selectedVideo.currentStage?.replace(/_/g, ' ')} - {selectedVideo.progress}%</p></div>
                    ) : <div className="text-center py-6 text-gray-700"><Circle size={20} className="mx-auto mb-1" /><p className="text-[10px]">Click play</p></div>}
                  </div>
                </div>
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center border border-dashed border-gray-800 m-2"><div className="text-center text-gray-700"><Upload size={24} className="mx-auto mb-1" /><p className="text-[10px]">Select or add videos</p></div></div>
          )}
        </div>
      </div>

      {/* Upload Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 bg-black/90 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-gray-700 w-full max-w-sm">
            <div className="p-2 border-b border-gray-700 flex items-center justify-between"><h3 className="text-xs">ADD VIDEOS</h3><button onClick={() => setShowUploadModal(false)} className="text-gray-500 hover:text-white"><X size={16} /></button></div>
            <div className="p-3">
              <div className="grid grid-cols-4 gap-1 mb-3">
                {[{ id: 'local', icon: Upload, label: 'LOCAL' }, { id: 'url', icon: Link, label: 'URL' }, { id: 'storage', icon: Cloud, label: 'CLOUD' }, { id: 'database', icon: Database, label: 'DB' }].map(source => (
                  <button key={source.id} onClick={() => setUploadSource(source.id as any)} className={`p-2 text-center border transition-all ${uploadSource === source.id ? 'border-white bg-gray-800' : 'border-gray-700'}`}>
                    <source.icon size={14} className="mx-auto mb-0.5" /><div className="text-[9px]">{source.label}</div>
                  </button>
                ))}
              </div>
              {uploadSource === 'local' && (<div><input ref={fileInputRef} type="file" multiple accept="video/*" className="hidden" onChange={(e) => handleFileSelect(e.target.files)} /><button onClick={() => fileInputRef.current?.click()} className="w-full p-4 border border-dashed border-gray-600 hover:border-white transition-all text-center"><Upload size={20} className="mx-auto mb-1 opacity-50" /><p className="text-[10px]">Click or drag</p></button></div>)}
              {uploadSource === 'url' && (<div><textarea value={urlInput} onChange={(e) => setUrlInput(e.target.value)} placeholder="URLs (one per line)" className="w-full h-20 bg-black border border-gray-700 p-2 text-[10px] resize-none focus:border-white outline-none" /><button onClick={handleUrlImport} className="btn w-full mt-2 text-[10px]">IMPORT</button></div>)}
              {(uploadSource === 'storage' || uploadSource === 'database') && (<div className="text-center py-4 text-gray-600"><Cloud size={20} className="mx-auto mb-1 opacity-50" /><p className="text-[10px]">Coming soon</p></div>)}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Pipeline
