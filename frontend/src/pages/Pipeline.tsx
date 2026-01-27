import { FC, useState, useEffect, useRef, useCallback } from 'react'
import { 
  Upload, Plus, Video, Play, Trash2,
  RotateCcw, Loader2, Link, Database, Cloud,
  Check, Circle, AlertCircle, X, Eye
} from 'lucide-react'
import { useVideoStore, QueueVideo, VideoStatus } from '@/store/videoStore'
import { useSettingsStore } from '@/store/settingsStore'
import { evaluationApi, resultsApi, checkpointsApi, videoApi, stageApi, createSSEConnection } from '@/api/endpoints'
import toast from 'react-hot-toast'

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
  { id: 'finalize', backendId: 'finalize', name: 'Finalize', number: '11' },
]

const STAGE_PROGRESS_MAP: Record<string, number> = {
  'ingest_video': 5, 'segment_video': 10, 'yolo26_vision': 25,
  'yoloworld_vision': 30, 'violence_detection': 40, 'audio_transcription': 55,
  'ocr_extraction': 65, 'text_moderation': 75, 'policy_fusion': 85,
  'report_generation': 95, 'finalize': 100
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
    
    case 'finalize': {
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
    setProcessingBatch, loadSavedResults, getVideoById, getVideoByBatchId
  } = useVideoStore()
  
  const { currentPolicy } = useSettingsStore()
  
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [uploadSource, setUploadSource] = useState<'local' | 'url' | 'storage' | 'database'>('local')
  const [urlInput, setUrlInput] = useState('')
  const [videoType, setVideoType] = useState<'labeled' | 'original'>('labeled')
  const [selectedStage, setSelectedStage] = useState<string | null>(null)
  const [stageOutput, setStageOutput] = useState<any>(null)
  const [stageLoading, setStageLoading] = useState(false)
  const [completedStages, setCompletedStages] = useState<string[]>([])
  const [videoError, setVideoError] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const sseConnectionsRef = useRef<Map<string, EventSource>>(new Map())

  // LocalStorage cache helpers for stage outputs
  const STAGE_CACHE_KEY = 'safevid_stage_outputs'
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

  // Load saved results and checkpoints on mount
  useEffect(() => {
    const loadData = async () => {
      try {
        const results = await resultsApi.load()
        if (results.length > 0) loadSavedResults(results)
        
        const checkpoints = await checkpointsApi.list()
        checkpoints.forEach((cp: any) => {
          const exists = queue.find(v => v.id === cp.video_id || v.batchVideoId === cp.batch_video_id || v.filename === cp.filename)
          if (!exists) {
            addVideos([{
              filename: cp.filename, file: null, status: 'failed', source: 'local',
              progress: cp.progress || 0, currentStage: cp.stage, batchVideoId: cp.batch_video_id,
              error: `Interrupted at ${cp.progress}% (${cp.stage})`,
            }])
          }
        })
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

  // SSE connection with retry
  const connectSSE = useCallback((videoId: string, queueVideoId: string, retryCount = 0) => {
    const maxRetries = 3
    const existing = sseConnectionsRef.current.get(videoId)
    if (existing) existing.close()

    const eventSource = createSSEConnection(videoId)
    sseConnectionsRef.current.set(videoId, eventSource)

    eventSource.onmessage = (event) => {
      try {
        const update = JSON.parse(event.data)
        const video = getVideoById(queueVideoId)
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

        updateVideo(queueVideoId, {
          currentStage: update.stage,
          progress: Math.min(progress, 100),
          statusMessage: update.message,
          status: update.stage === 'complete' || (update.stage === 'finalize' && progress >= 100) ? 'completed' : 'processing'
        })

        if (update.stage === 'complete') {
          eventSource.close()
          sseConnectionsRef.current.delete(videoId)
        }
      } catch (e) {
        console.error('SSE parse error:', e)
      }
    }

    eventSource.onerror = () => {
      eventSource.close()
      sseConnectionsRef.current.delete(videoId)
      const video = getVideoById(queueVideoId)
      if (video && video.status === 'processing' && retryCount < maxRetries) {
        setTimeout(() => connectSSE(videoId, queueVideoId, retryCount + 1), 2000 * (retryCount + 1))
      }
    }
  }, [getVideoById, updateVideo])

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
      const response = await evaluationApi.uploadBatch([video.file], currentPolicy)
      if (response.videos?.[0]) {
        const batchVideo = response.videos[0]
        updateVideo(videoId, { batchVideoId: batchVideo.video_id })
        connectSSE(batchVideo.video_id, videoId)
        pollBatchStatus(response.batch_id)
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
      const response = await evaluationApi.uploadBatch(files, currentPolicy)
      response.videos.forEach((batchVideo: any) => {
        const queueVideo = queue.find(v => v.filename === batchVideo.filename)
        if (queueVideo) {
          updateVideo(queueVideo.id, { batchVideoId: batchVideo.video_id, status: 'processing' })
          connectSSE(batchVideo.video_id, queueVideo.id)
        }
      })
      pollBatchStatus(response.batch_id)
    } catch (error: any) {
      toast.error('Failed to start batch processing'); setProcessingBatch(false)
    }
  }

  const pollBatchStatus = (batchId: string) => {
    const interval = setInterval(async () => {
      try {
        const data = await evaluationApi.getBatchStatus(batchId)
        if (data.videos) {
          Object.values(data.videos).forEach((bv: any) => {
            const qv = getVideoByBatchId(bv.video_id) || queue.find(v => v.filename === bv.filename)
            if (qv) {
              updateVideo(qv.id, {
                status: bv.status, progress: bv.progress || 0, verdict: bv.verdict,
                error: bv.error, result: bv.result,
                duration: bv.result?.metadata?.duration ? `${bv.result.metadata.duration.toFixed(1)}s` : undefined
              })
            }
          })
        }
        if (data.status === 'completed') {
          clearInterval(interval); setProcessingBatch(false)
          const completed = queue.filter(v => v.status === 'completed' && v.result)
          if (completed.length > 0) {
            await resultsApi.save(completed.map(v => ({
              id: v.id, filename: v.filename, status: v.status, verdict: v.verdict,
              duration: v.duration, result: v.result, batchVideoId: v.batchVideoId, timestamp: new Date().toISOString()
            })))
          }
        }
      } catch { clearInterval(interval); setProcessingBatch(false) }
    }, 2000)
  }

  const retryVideo = async (videoId: string) => {
    const video = getVideoById(videoId)
    if (!video) return
    if (!video.file && video.batchVideoId) {
      try {
        const blob = await videoApi.getUploadedVideo(video.batchVideoId)
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
    
    // Delete from backend if it was saved
    const backendId = video.batchVideoId || videoId
    try {
      // Delete result (also deletes from database)
      await resultsApi.delete(backendId)
    } catch (e) {
      // Ignore if not found
    }
    try {
      // Delete checkpoint
      await checkpointsApi.delete(backendId)
    } catch (e) {
      // Ignore if not found
    }
    toast.success('Video deleted')
  }

  // Clear all videos from queue and backend
  const handleClearAll = async () => {
    if (!confirm('Delete all videos from queue and saved results?')) return
    
    // Get all video IDs before clearing
    const videoIds = queue.map(v => v.id)
    
    // Clear local store
    videoIds.forEach(id => removeVideo(id))
    
    // Delete all from backend
    try {
      await resultsApi.clearAll().catch(() => {})
      await checkpointsApi.clearAll().catch(() => {})
    } catch (e) {
      // Continue even if backend fails
    }
    
    toast.success('All videos cleared')
  }

  const selectedVideo = selectedVideoId ? getVideoById(selectedVideoId) : null
  
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
  const fetchStageOutput = async (videoId: string, stageName: string) => {
    setStageLoading(true)
    
    // Check localStorage cache first
    const cached = getCachedStageOutput(videoId, stageName)
    if (cached) {
      console.log('Using cached stage output for:', stageName)
      setStageOutput(cached)
      setStageLoading(false)
      return
    }
    
    try {
      const output = await stageApi.getStageOutput(videoId, stageName)
      if (output && Object.keys(output).length > 0) {
        // Cache the result
        setCachedStageOutput(videoId, stageName, output)
        setStageOutput(output)
        setStageLoading(false)
        return
      }
    } catch (error) {
      console.log('Stage output not in checkpoint, using fallback:', stageName)
    }
    
    // Fallback: derive stage data from video result
    if (selectedVideo?.result) {
      console.log('Deriving stage output from result for:', stageName)
      const derivedOutput = deriveStageOutputFromResult(stageName, selectedVideo.result)
      // Cache the derived output too
      setCachedStageOutput(videoId, stageName, derivedOutput)
      setStageOutput(derivedOutput)
    } else {
      console.log('No result data available for fallback')
      setStageOutput(null)
    }
    setStageLoading(false)
  }
  
  // Derive stage-specific output from overall result (for older videos without checkpoint data)
  const deriveStageOutputFromResult = (stageName: string, result: any) => {
    const evidence = result.evidence || {}
    const metadata = result.metadata || {}
    
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
          detections: evidence.vision || [],
          total_detections: (evidence.vision || []).length
        }
      case 'yoloworld':
        return {
          stage: 'yoloworld',
          detections: evidence.yoloworld || [],
          total_detections: (evidence.yoloworld || []).length
        }
      case 'violence':
        return {
          stage: 'violence',
          violence_segments: evidence.violence_segments || []
        }
      case 'audio_asr':
        return {
          stage: 'audio_asr',
          full_text: result.transcript?.text || '',
          chunks: result.transcript?.chunks || []
        }
      case 'ocr':
        return {
          stage: 'ocr',
          texts: (evidence.ocr || []).map((o: any) => o.text),
          total_detections: (evidence.ocr || []).length
        }
      case 'text_moderation':
        return {
          stage: 'text_moderation',
          transcript_chunks_analyzed: result.transcript?.chunks?.length || 0,
          ocr_items_analyzed: (evidence.ocr || []).length,
          flagged_transcript: evidence.transcript_moderation || [],
          flagged_ocr: evidence.ocr_moderation || []
        }
      case 'policy_fusion':
        return {
          stage: 'policy_fusion',
          verdict: result.verdict,
          scores: Object.fromEntries(
            Object.entries(result.criteria || {}).map(([k, v]: [string, any]) => [k, v?.value || v || 0])
          ),
          violations: result.violations || []
        }
      case 'report':
        return {
          stage: 'report',
          report_preview: result.report,
          report_type: 'saved'
        }
      default:
        return result
    }
  }

  // Handle stage click - always fetch stage output from backend by video_id
  const handleStageClick = async (stageId: string) => {
    if (selectedStage === stageId) {
      setSelectedStage(null)
      setStageOutput(null)
      return
    }
    
    setSelectedStage(stageId)
    
    // Always fetch stage-specific output from backend using video_id
    const videoId = selectedVideo?.batchVideoId || selectedVideo?.id
    const stage = PIPELINE_STAGES.find(s => s.id === stageId)
    
    if (videoId && stage) {
      await fetchStageOutput(videoId, stage.backendId)
    } else if (selectedVideo?.result) {
      // Fallback to result data if no video_id available
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

  // Note: Video URLs are now computed inline in the JSX to properly handle
  // local file vs backend URL fallback (matching index.html behavior)

  return (
    <div className="h-full flex flex-col bg-black text-white overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between flex-shrink-0">
        <span className="text-xs text-gray-500 tracking-widest">VIDEO QUEUE</span>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowUploadModal(true)} className="p-1.5 border border-gray-700 hover:border-white transition-all" title="Add Video"><Plus size={16} /></button>
          {queue.length > 0 && (
            <button onClick={handleClearAll} className="p-1.5 border border-gray-700 hover:border-red-500 hover:text-red-500 transition-all" title="Clear All">
              <Trash2 size={16} />
            </button>
          )}
          <button onClick={processAllVideos} disabled={processingBatch || queue.filter(v => v.status === 'queued' && v.file).length === 0} className="btn text-xs flex items-center gap-1.5 py-1.5 px-3">
            {processingBatch ? <><Loader2 size={12} className="animate-spin" /> PROCESSING</> : <><Play size={12} /> PROCESS</>}
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
                  <div key={video.id} onClick={() => { selectVideo(video.id); setSelectedStage(null); setStageOutput(null); setVideoError(false) }}
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
                {/* Video */}
                <div className="flex flex-col bg-gray-900 border border-gray-800 overflow-hidden">
                  <div className="p-1.5 border-b border-gray-800 flex items-center justify-between">
                    <span className="text-[9px] text-gray-500 uppercase">{videoType === 'labeled' ? 'Labeled' : 'Original'}</span>
                    {selectedVideo.status === 'completed' && (
                      <div className="flex text-[9px]">
                        <button onClick={() => { setVideoType('labeled'); setVideoError(false) }} className={`px-1.5 py-0.5 ${videoType === 'labeled' ? 'bg-white text-black' : 'text-gray-600'}`}>LAB</button>
                        <button onClick={() => { setVideoType('original'); setVideoError(false) }} className={`px-1.5 py-0.5 ${videoType === 'original' ? 'bg-white text-black' : 'text-gray-600'}`}>ORI</button>
                      </div>
                    )}
                  </div>
                  <div className="flex-1 bg-black flex items-center justify-center">
                    {selectedVideo.status === 'completed' ? (
                      videoError ? (
                        <div className="text-center text-gray-600 p-4">
                          <Video size={24} className="mx-auto mb-2 opacity-50" />
                          <p className="text-xs">Video not available</p>
                          {videoType === 'labeled' && (
                            <button onClick={() => { setVideoType('original'); setVideoError(false) }} className="text-blue-400 text-xs mt-2 underline">Try original</button>
                          )}
                        </div>
                      ) : (
                        <video 
                          controls 
                          className="max-w-full max-h-full" 
                          key={`${selectedVideo.id}-${videoType}`}
                          src={(() => {
                            const vid = selectedVideo.batchVideoId || (selectedVideo.result as any)?.metadata?.video_id
                            
                            if (videoType === 'original') {
                              // Try local file first, then backend
                              if (selectedVideo.file) return URL.createObjectURL(selectedVideo.file)
                              return vid ? videoApi.getUploadedVideoUrl(vid) : ''
                            } else {
                              // Labeled video from backend
                              return vid ? videoApi.getLabeledVideoUrl(vid) : ''
                            }
                          })()}
                          onError={() => {
                            if (videoType === 'labeled') {
                              // If labeled fails, auto-switch to original
                              console.log('Labeled video failed, trying original')
                              setVideoType('original')
                            } else {
                              // Original also failed
                              setVideoError(true)
                            }
                          }}
                        />
                      )
                    ) : selectedVideo.status === 'processing' ? (
                      <div className="text-center"><Loader2 size={24} className="mx-auto mb-1 animate-spin text-gray-700" /><p className="text-[10px] text-gray-600">{selectedVideo.progress}%</p></div>
                    ) : <Video size={24} className="text-gray-800" />}
                  </div>
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
                        <div className={`p-3 border text-center ${
                          selectedVideo.verdict === 'SAFE' ? 'border-green-700 bg-green-900/20' :
                          selectedVideo.verdict === 'CAUTION' ? 'border-yellow-700 bg-yellow-900/20' :
                          selectedVideo.verdict === 'UNSAFE' ? 'border-red-700 bg-red-900/20' : 'border-blue-700 bg-blue-900/20'
                        }`}>
                          <div className="text-xl font-bold">{selectedVideo.verdict}</div>
                          <div className="text-[10px] text-gray-500">{((selectedVideo.result.confidence || 0) * 100).toFixed(0)}% confidence</div>
                        </div>
                        {selectedVideo.result.criteria && (
                          <div className="grid grid-cols-2 gap-1">
                            {Object.entries(selectedVideo.result.criteria).slice(0, 6).map(([key, val]: [string, any]) => (
                              <div key={key} className="bg-black p-2 border border-gray-800">
                                <div className="text-[9px] text-gray-600 uppercase">{key}</div>
                                <div className="text-sm font-medium">{typeof val === 'object' ? ((val.score || val.value || 0) * 100).toFixed(0) : ((parseFloat(val) || 0) * 100).toFixed(0)}%</div>
                              </div>
                            ))}
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
