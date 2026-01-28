import { FC, useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { 
  Upload, Plus, Video, Play, Trash2,
  RotateCcw, Loader2, Link, Database, Cloud,
  Check, Circle, AlertCircle, X, Eye, ChevronDown, Info
} from 'lucide-react'
import { useVideoStore, QueueVideo, VideoStatus } from '@/store/videoStore'
import { useSettingsStore } from '@/store/settingsStore'
import { evaluationApi, stageApi, createSSEConnection, api } from '@/api/endpoints'
import { evaluations as evaluationsApi } from '@/api'
import { ProcessedFrames } from '@/components/pipeline/ProcessedFrames'
import toast from 'react-hot-toast'

interface CriteriaPreset {
  id: string
  name: string
  description?: string
  criteria_count: number
}

// Pipeline stage definitions
// 'id' is used for UI tracking, 'backendId' is used for API calls
const PIPELINE_STAGES = [
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

const STAGE_PROGRESS_MAP: Record<string, number> = {
  'ingest_video': 5, 'segment_video': 10, 'yolo26_vision': 25,
  'yoloworld_vision': 30, 'violence_detection': 40, 'audio_transcription': 55,
  'ocr_extraction': 65, 'text_moderation': 75, 'policy_fusion': 90,
  'report_generation': 100
}

// Generate stage content matching original index.html data structure
const generateStageContent = (stageName: string, data: any) => {
  if (!data) return <div className="text-gray-500 text-sm">No data available</div>
  
  const evidence = data.evidence || {}
  const metadata = data.metadata || {}
  
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
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-black p-3 border border-gray-800">
              <div className="text-[10px] text-gray-500 mb-1">DURATION</div>
              <div className="text-lg font-medium">{duration ? `${duration.toFixed(1)}s` : 'N/A'}</div>
            </div>
            <div className="bg-black p-3 border border-gray-800">
              <div className="text-[10px] text-gray-500 mb-1">RESOLUTION</div>
              <div className="text-lg font-medium">{width && height ? `${width}×${height}` : 'N/A'}</div>
            </div>
            <div className="bg-black p-3 border border-gray-800">
              <div className="text-[10px] text-gray-500 mb-1">FPS</div>
              <div className="text-lg font-medium">{fps ? fps.toFixed(1) : 'N/A'}</div>
            </div>
            <div className="bg-black p-3 border border-gray-800">
              <div className="text-[10px] text-gray-500 mb-1">AUDIO</div>
              <div className="text-lg font-medium">{hasAudio !== undefined ? (hasAudio ? '✓ Yes' : '✗ No') : 'N/A'}</div>
            </div>
          </div>
          {(originalMeta.width || originalMeta.height) && (
            <div className="bg-gray-900 p-2 border-l-2 border-blue-500 text-xs text-gray-400">
              Original: {originalMeta.width}×{originalMeta.height} @ {originalMeta.fps?.toFixed(1)} fps
              <div className="text-blue-400 mt-1">✓ Normalized to 720p @ 30fps</div>
            </div>
          )}
          {videoId && (
            <div className="text-[10px] text-gray-600">
              ID: <code className="bg-black px-1">{videoId}</code>
            </div>
          )}
        </div>
      )
    }
    
    case 'segment_video': {
      // Stage output uses frames_extracted and segments_created
      const sampledFrames = data.frames_extracted || data.sampled_frames || metadata.sampled_frames || evidence.frames?.length
      const segments = data.segments_created || data.segments || metadata.segments || evidence.violence_segments?.length
      const samplingFps = data.sampling_fps || data.yolo_sampling_fps || metadata.sampling_fps || 1.0
      const videomaeConfig = data.videomae_config || {}
      const overlapPct = data.segment_overlap_percent
      
      return (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-2">
            <div className="bg-black p-3 border border-gray-800">
              <div className="text-[10px] text-gray-500 mb-1">FRAMES</div>
              <div className="text-lg font-medium">{Array.isArray(sampledFrames) ? sampledFrames.length : (sampledFrames || 'N/A')}</div>
            </div>
            <div className="bg-black p-3 border border-gray-800">
              <div className="text-[10px] text-gray-500 mb-1">RATE</div>
              <div className="text-lg font-medium">{samplingFps} fps</div>
            </div>
            <div className="bg-black p-3 border border-gray-800">
              <div className="text-[10px] text-gray-500 mb-1">SEGMENTS</div>
              <div className="text-lg font-medium">{Array.isArray(segments) ? segments.length : (segments || 'N/A')}</div>
            </div>
          </div>
          {(videomaeConfig.segment_duration || overlapPct !== undefined) && (
            <div className="bg-gray-900 p-2 border-l-2 border-blue-500 text-xs text-gray-400">
              {videomaeConfig.segment_duration && (
                <>VideoMAE: {videomaeConfig.segment_duration}s window, {videomaeConfig.stride}s stride</>
              )}
              {overlapPct !== undefined && (
                <div className="text-blue-400 mt-1">✓ Segment overlap: {overlapPct}%</div>
              )}
            </div>
          )}
        </div>
      )
    }
    
    // YOLO26 Vision - uses detections from stage output or evidence.vision
    case 'yolo26_vision': {
      // Stage output has detections at top level, final result has evidence.vision
      const visionData = data.detections || evidence.vision || []
      const summary = data.detection_summary || {}
      const objectCounts: Record<string, number> = Object.keys(summary).length > 0 
        ? summary 
        : visionData.reduce((acc: Record<string, number>, d: any) => {
            const label = d.label || d.class || 'unknown'
            acc[label] = (acc[label] || 0) + 1
            return acc
          }, {})
      const topObjects = Object.entries(objectCounts).sort((a, b) => b[1] - a[1]).slice(0, 8)
      const totalDetections = data.total_detections || visionData.length
      
      return (
        <div className="space-y-3">
          <div className="text-sm">
            <strong>{totalDetections}</strong> objects detected across <strong>{Object.keys(objectCounts).length}</strong> categories
          </div>
          {topObjects.length > 0 ? (
            <div className="grid grid-cols-2 gap-2">
              {topObjects.map(([label, count]) => (
                <div key={label} className="bg-black p-2 border border-gray-800 flex justify-between text-sm">
                  <span className="capitalize text-gray-300">{label}</span>
                  <span className="text-gray-500 font-mono">{count}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-gray-500 text-sm">No objects detected</div>
          )}
          {data.safety_signals && (
            <div className="mt-2 pt-2 border-t border-gray-800 text-xs text-gray-400">
              <span className={data.safety_signals.has_weapons ? 'text-red-400' : 'text-green-400'}>
                {data.safety_signals.has_weapons ? `⚠️ ${data.safety_signals.weapon_count} weapons` : '✓ No weapons'}
              </span>
              {' • '}
              <span>{data.safety_signals.person_count} persons detected</span>
            </div>
          )}
        </div>
      )
    }
    
    // YOLO-World Vision - uses evidence.yoloworld with prompt matching
    case 'yoloworld_vision': {
      // Stage output has detections at top level, final result has evidence.yoloworld
      const yoloworldData = data.detections || evidence.yoloworld || []
      const matchedPrompts = [...new Set(yoloworldData.map((d: any) => d.prompt_match || d.label).filter(Boolean))]
      const yoloworldCounts: Record<string, number> = {}
      yoloworldData.forEach((d: any) => {
        const label = d.prompt_match || d.label
        if (label) yoloworldCounts[label] = (yoloworldCounts[label] || 0) + 1
      })
      const totalDetections = data.total_detections || yoloworldData.length
      
      return (
        <div className="space-y-3">
          <div className="text-sm">
            <strong>{totalDetections}</strong> detections from <strong>{matchedPrompts.length}</strong> prompts
          </div>
          {matchedPrompts.length > 0 ? (
            <div className="grid grid-cols-2 gap-2">
              {matchedPrompts.map((prompt: string) => (
                <div key={prompt} className="bg-black p-2 border border-gray-800">
                  <div className="text-blue-400 text-sm font-medium">{prompt}</div>
                  <div className="text-gray-500 text-xs">{yoloworldCounts[prompt]} detections</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-gray-500 text-sm">No custom prompts matched</div>
          )}
          {data.safety_signals && (
            <div className="mt-2 pt-2 border-t border-gray-800 text-xs text-gray-400">
              <span className={data.safety_signals.has_weapons ? 'text-red-400' : 'text-green-400'}>
                {data.safety_signals.has_weapons ? `⚠️ ${data.safety_signals.weapon_count} weapons` : '✓ No weapons'}
              </span>
              {' • '}
              <span className={data.safety_signals.has_substances ? 'text-yellow-400' : 'text-green-400'}>
                {data.safety_signals.has_substances ? `⚠️ ${data.safety_signals.substance_count} substances` : '✓ No substances'}
              </span>
            </div>
          )}
        </div>
      )
    }
    
    case 'violence_detection': {
      // Stage output has violence_segments at top level
      const violenceSegments = data.violence_segments || evidence.violence_segments || evidence.violence || []
      const highViolence = violenceSegments.filter((s: any) => (s.violence_score || s.score || 0) > 0.5)
      const maxScore = Math.max(...violenceSegments.map((s: any) => s.violence_score || s.score || 0), 0)
      
      return (
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-2">
            <div className="bg-black p-3 border border-gray-800">
              <div className="text-[10px] text-gray-500 mb-1">SEGMENTS</div>
              <div className="text-lg font-medium">{violenceSegments.length}</div>
            </div>
            <div className="bg-black p-3 border border-gray-800">
              <div className="text-[10px] text-gray-500 mb-1">HIGH VIOLENCE</div>
              <div className={`text-lg font-medium ${highViolence.length > 0 ? 'text-red-400' : 'text-green-400'}`}>{highViolence.length}</div>
            </div>
            <div className="bg-black p-3 border border-gray-800">
              <div className="text-[10px] text-gray-500 mb-1">MAX SCORE</div>
              <div className={`text-lg font-medium ${maxScore > 0.5 ? 'text-red-400' : 'text-green-400'}`}>{maxScore.toFixed(2)}</div>
            </div>
          </div>
          {highViolence.length > 0 && (
            <div className="space-y-1">
              <div className="text-sm font-medium">High Violence Segments:</div>
              {highViolence.slice(0, 3).map((seg: any, i: number) => (
                <div key={i} className="bg-black p-2 border-l-2 border-red-500 text-xs">
                  <div className="flex justify-between">
                    <span>{seg.start_time?.toFixed(1)}s - {seg.end_time?.toFixed(1)}s</span>
                    <span className="text-red-400">{((seg.violence_score || seg.score) * 100).toFixed(0)}%</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )
    }
    
    case 'audio_transcription': {
      // Stage output has full_text and chunks at top level
      const transcript = data.transcript || evidence.transcript || {}
      const chunks = data.chunks || transcript.chunks || evidence.asr || []
      const fullText = data.full_text || transcript.text || ''
      
      return (
        <div className="space-y-3">
          <div className="text-sm mb-2">
            <strong>{chunks.length}</strong> speech chunks transcribed
            {transcript.language && <span className="text-gray-500"> (Language: {transcript.language})</span>}
          </div>
          
          {fullText && (
            <div className="bg-gray-800 p-3 border-l-2 border-white">
              <div className="text-xs font-medium text-white mb-2">Full Transcript:</div>
              <div className="text-xs text-gray-300 leading-relaxed">{fullText}</div>
            </div>
          )}
          
          {chunks.length > 0 ? (
            <div className="space-y-1">
              <div className="text-xs font-medium text-white mb-1">Timestamped Chunks:</div>
              {chunks.slice(0, 5).map((chunk: any, i: number) => (
                <div key={i} className="bg-black p-2 border-l-2 border-white">
                  <div className="text-[10px] text-gray-500 mb-1">
                    {chunk.start_time != null ? `${chunk.start_time.toFixed(1)}s` : (chunk.timestamp?.[0] != null ? `${chunk.timestamp[0].toFixed(1)}s` : 'N/A')} 
                    {' - '}
                    {chunk.end_time != null ? `${chunk.end_time.toFixed(1)}s` : (chunk.timestamp?.[1] != null ? `${chunk.timestamp[1].toFixed(1)}s` : 'N/A')}
                  </div>
                  <div className="text-xs text-gray-300">{chunk.text}</div>
                </div>
              ))}
              {chunks.length > 5 && (
                <div className="text-[10px] text-gray-500 text-center">... and {chunks.length - 5} more chunks</div>
              )}
            </div>
          ) : (
            <div className="text-gray-500 text-sm">No speech detected</div>
          )}
        </div>
      )
    }
    
    case 'ocr_extraction': {
      // Stage output has texts array directly, final result has evidence.ocr
      const ocrResults = evidence.ocr || data.ocr || []
      const textsFromStage = data.texts || []
      const texts = textsFromStage.length > 0 ? textsFromStage : ocrResults.map((o: any) => o.text).filter(Boolean)
      const totalDetections = data.total_detections || ocrResults.length
      
      return (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-black p-3 border border-gray-800">
              <div className="text-[10px] text-gray-500 mb-1">TEXT REGIONS</div>
              <div className="text-lg font-medium">{totalDetections}</div>
            </div>
            {data.frames_analyzed && (
              <div className="bg-black p-3 border border-gray-800">
                <div className="text-[10px] text-gray-500 mb-1">FRAMES WITH TEXT</div>
                <div className="text-lg font-medium">{data.frames_with_text || 0}/{data.frames_analyzed}</div>
              </div>
            )}
          </div>
          {texts.length > 0 ? (
            <div className="space-y-1">
              {texts.slice(0, 5).map((text: string, i: number) => (
                <div key={i} className="bg-gray-900 p-2 text-xs text-gray-300 truncate">
                  {text}
                </div>
              ))}
              {texts.length > 5 && (
                <div className="text-[10px] text-gray-500 text-center">... and {texts.length - 5} more</div>
              )}
            </div>
          ) : (
            <div className="text-gray-500 text-sm">No text detected in video</div>
          )}
        </div>
      )
    }
    
    // Text Moderation - uses transcript_moderation and ocr_moderation
    case 'text_moderation': {
      // Stage output has flagged_* at top level
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
      
      return (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <div className="bg-black p-3 border border-gray-800">
              <div className="text-[10px] text-gray-500 mb-1">TRANSCRIPT CHUNKS</div>
              <div className="text-lg font-medium">{transcriptCount}</div>
              <div className={`text-[10px] mt-1 ${flaggedTranscriptCount > 0 ? 'text-red-400' : 'text-green-400'}`}>
                {flaggedTranscriptCount} flagged
              </div>
            </div>
            <div className="bg-black p-3 border border-gray-800">
              <div className="text-[10px] text-gray-500 mb-1">OCR TEXTS</div>
              <div className="text-lg font-medium">{ocrCount}</div>
              <div className={`text-[10px] mt-1 ${flaggedOcrCount > 0 ? 'text-red-400' : 'text-green-400'}`}>
                {flaggedOcrCount} flagged
              </div>
            </div>
          </div>
          
          {flaggedTranscript.length > 0 && (
            <div className="space-y-1">
              <div className="text-xs font-medium text-yellow-400">⚠️ Flagged Transcript:</div>
              {flaggedTranscript.slice(0, 3).map((mod: any, i: number) => (
                <div key={i} className="bg-black p-2 border-l-2 border-red-500 text-xs">
                  <div className="text-gray-300 mb-1">"{mod.text || mod.original_text || 'N/A'}"</div>
                  <div className="flex flex-wrap gap-2 text-[10px]">
                    {(mod.profanity_score || mod.profanity || 0) > 0.3 && <span className="text-red-400">Profanity: {((mod.profanity_score || mod.profanity) * 100).toFixed(0)}%</span>}
                    {(mod.sexual_score || mod.sexual || 0) > 0.3 && <span className="text-red-400">Sexual: {((mod.sexual_score || mod.sexual) * 100).toFixed(0)}%</span>}
                    {(mod.hate_score || mod.hate || 0) > 0.3 && <span className="text-red-400">Hate: {((mod.hate_score || mod.hate) * 100).toFixed(0)}%</span>}
                    {(mod.violence_score || mod.violence || 0) > 0.3 && <span className="text-red-400">Violence: {((mod.violence_score || mod.violence) * 100).toFixed(0)}%</span>}
                    {mod.profanity_words?.length > 0 && <span className="text-red-400">[{mod.profanity_words.join(', ')}]</span>}
                  </div>
                  <div className="text-gray-600 text-[10px] mt-1">
                    @ {mod.start_time?.toFixed(1) || mod.timestamp?.toFixed(1) || 'N/A'}s
                  </div>
                </div>
              ))}
            </div>
          )}
          
          {transcriptCount > 0 && flaggedTranscript.length === 0 && (
            <div className="space-y-1">
              <div className="text-xs font-medium text-green-400">📝 Sample Clean Transcript:</div>
              {transcriptMod.slice(0, 2).map((mod: any, i: number) => (
                <div key={i} className="bg-black p-2 border-l-2 border-green-500 text-xs">
                  <div className="text-gray-300">"{mod.text || mod.original_text || 'N/A'}"</div>
                </div>
              ))}
            </div>
          )}
          
          {flaggedOcr.length > 0 && (
            <div className="space-y-1">
              <div className="text-xs font-medium text-orange-400">⚠️ Flagged OCR:</div>
              {flaggedOcr.slice(0, 2).map((mod: any, i: number) => (
                <div key={i} className="bg-black p-2 border-l-2 border-orange-500 text-xs">
                  <div className="text-gray-300">"{mod.text || 'N/A'}"</div>
                  <div className="flex flex-wrap gap-2 text-[10px]">
                    {mod.profanity_score > 0.3 && <span className="text-orange-400">Profanity: {(mod.profanity_score * 100).toFixed(0)}%</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )
    }
    
    case 'policy_fusion': {
      // Stage output has scores, verdict, violations at top level
      const scores = data.scores || data.criteria || {}
      const verdict = data.verdict || 'unknown'
      const violations = data.violations || []
      const violationsCount = data.violations_count ?? violations.length
      
      return (
        <div className="space-y-3">
          <div className={`bg-black p-3 border-2 ${verdict === 'fail' ? 'border-red-500' : verdict === 'pass' ? 'border-green-500' : 'border-yellow-500'}`}>
            <div className="text-[10px] text-gray-500 mb-1">VERDICT</div>
            <div className={`text-xl font-bold uppercase ${verdict === 'fail' ? 'text-red-400' : verdict === 'pass' ? 'text-green-400' : 'text-yellow-400'}`}>
              {verdict}
            </div>
            {violationsCount > 0 && (
              <div className="text-xs text-red-400 mt-1">{violationsCount} violations</div>
            )}
          </div>
          
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(scores).slice(0, 6).map(([key, val]: [string, any]) => {
              const score = typeof val === 'object' ? (val.score || val.value || 0) : (parseFloat(String(val)) || 0)
              const pct = (score * 100).toFixed(0)
              return (
                <div key={key} className="bg-black p-3 border border-gray-800">
                  <div className="text-[10px] text-gray-500 mb-1 uppercase">{key.replace(/_/g, ' ')}</div>
                  <div className={`text-lg font-medium ${score > 0.6 ? 'text-red-400' : score > 0.3 ? 'text-yellow-400' : 'text-green-400'}`}>
                    {pct}%
                  </div>
                </div>
              )
            })}
          </div>
          
          {violations.length > 0 && (
            <div className="space-y-1">
              <div className="text-xs font-medium text-red-400">⚠️ Violations:</div>
              {violations.slice(0, 3).map((v: any, i: number) => (
                <div key={i} className="bg-black p-2 border-l-2 border-red-500 text-xs">
                  <span className="text-gray-300">{v.criterion}</span>
                  <span className="text-red-400 ml-2">{((v.score || 0) * 100).toFixed(0)}%</span>
                  <span className="text-gray-500 ml-2">({v.severity})</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )
    }
    
    case 'report_generation': {
      // Stage output has report_preview at top level
      const summary = data.report_preview || data.report || data.summary
      const reportType = data.report_type || 'generated'
      
      return (
        <div className="space-y-3">
          <div className="bg-black p-2 border border-gray-800 text-xs">
            <span className="text-gray-500">Type:</span>{' '}
            <span className={reportType === 'qwen' ? 'text-blue-400' : 'text-gray-300'}>{reportType}</span>
          </div>
          {summary ? (
            <div className="bg-gray-900 p-3 text-xs text-gray-300 max-h-48 overflow-y-auto whitespace-pre-wrap">
              {summary}
            </div>
          ) : (
            <div className="text-gray-500 text-sm">Report generated</div>
          )}
        </div>
      )
    }
    
    case 'complete': {
      // Final result view (no longer a separate pipeline stage)
      return (
        <div className="space-y-3">
          <div className={`p-4 border text-center ${
            data.verdict === 'SAFE' ? 'border-green-600 bg-green-900/20' :
            data.verdict === 'CAUTION' ? 'border-yellow-600 bg-yellow-900/20' :
            data.verdict === 'UNSAFE' ? 'border-red-600 bg-red-900/20' :
            'border-blue-600 bg-blue-900/20'
          }`}>
            <div className="text-2xl font-bold">{data.verdict || 'N/A'}</div>
            <div className="text-sm text-gray-400 mt-1">
              {data.confidence ? `${(data.confidence * 100).toFixed(0)}% confidence` : ''}
            </div>
          </div>
        </div>
      )
    }
    
    default:
      return <div className="text-gray-500 text-sm">No data for this stage</div>
  }
}

const Pipeline: FC = () => {
  const { 
    queue, selectedVideoId, processingBatch,
    addVideos, updateVideo, removeVideo, selectVideo, 
    setProcessingBatch, getVideoById, getVideoByItemId
  } = useVideoStore()
  
  const { currentPolicy } = useSettingsStore()
  
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
        // Load criteria presets (built-in and custom)
        const [presetsRes, customRes] = await Promise.all([
          api.get('/criteria/presets').catch(() => ({ data: [] })),
          api.get('/criteria/custom').catch(() => ({ data: [] }))
        ])
        setPresets(presetsRes.data || [])
        setCustomCriteria(customRes.data || [])

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
          const baseProgress = STAGE_PROGRESS_MAP[update.stage] || 0
          const stages = Object.keys(STAGE_PROGRESS_MAP)
          const idx = stages.indexOf(update.stage)
          if (idx >= 0) {
            const nextProgress = idx < stages.length - 1 ? STAGE_PROGRESS_MAP[stages[idx + 1]] : 100
            const range = nextProgress - baseProgress
            const normalizedProgress = update.progress > 1 ? update.progress / 100 : update.progress
            progress = Math.round(baseProgress + (normalizedProgress * range))
          }
        }

        updateVideo(targetVideoId, {
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

  const selectedVideo = selectedVideoId ? getVideoById(selectedVideoId) : null
  
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
  
  const getStageStatus = (stageId: string, video: QueueVideo | null) => {
    if (!video) return 'pending'
    if (video.status === 'completed') return 'completed'
    if (video.status === 'failed') return 'error'
    const stageIndex = PIPELINE_STAGES.findIndex(s => s.id === stageId)
    const currentIndex = PIPELINE_STAGES.findIndex(s => s.id === video.currentStage)
    if (stageIndex < currentIndex) return 'completed'
    if (stageIndex === currentIndex) return 'active'
    return 'pending'
  }

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

  // Check if a stage is clickable (completed or video is done)
  const isStageClickable = (stageId: string, video: QueueVideo | null) => {
    if (!video) return false
    if (video.status === 'completed') return true
    
    // During processing, check if stage is completed
    const stageIndex = PIPELINE_STAGES.findIndex(s => s.id === stageId)
    const currentIndex = PIPELINE_STAGES.findIndex(s => s.id === video.currentStage)
    return stageIndex < currentIndex
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
              {/* Stages */}
              <div className="p-2 border-b border-gray-800 bg-gray-900/30 overflow-x-auto flex-shrink-0">
                <div className="flex items-center gap-1.5 min-w-max">
                  {PIPELINE_STAGES.map((stage, idx) => {
                    const status = getStageStatus(stage.id, selectedVideo)
                    const clickable = isStageClickable(stage.id, selectedVideo)
                    return (
                      <div key={stage.id} className="flex items-center gap-2">
                        <button onClick={() => clickable && handleStageClick(stage.id)} disabled={!clickable} className="flex flex-col items-center">
                          <div className={`w-9 h-9 rounded-full border-2 flex items-center justify-center text-xs transition-all ${
                            selectedStage === stage.id ? 'border-blue-400 bg-blue-400 text-black ring-2 ring-blue-400/50' :
                            status === 'completed' ? 'border-white bg-white text-black' :
                            status === 'active' ? 'border-white bg-white text-black animate-pulse' :
                            status === 'error' ? 'border-red-500 text-red-400' : 'border-gray-700 text-gray-600'
                          } ${clickable ? 'cursor-pointer hover:opacity-80' : 'cursor-default'}`}>
                            {status === 'completed' ? <Check size={14} /> : status === 'active' ? <Loader2 size={14} className="animate-spin" /> : status === 'error' ? <AlertCircle size={14} /> : stage.number}
                          </div>
                          <span className={`text-[9px] mt-1 ${selectedStage === stage.id ? 'text-blue-400' : status === 'completed' ? 'text-white' : 'text-gray-600'}`}>{stage.name}</span>
                        </button>
                        {idx < PIPELINE_STAGES.length - 1 && <div className={`w-4 h-px ${status === 'completed' ? 'bg-white' : 'bg-gray-800'}`} />}
                      </div>
                    )
                  })}
                </div>
              </div>

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
