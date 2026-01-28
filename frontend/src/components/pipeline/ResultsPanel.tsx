import { FC, useState } from 'react'
import { EvaluationResult } from '@/types/api'
import { formatDuration, formatPercent } from '@/utils/format'
import VideoPlayer from './VideoPlayer'
import Badge from '../common/Badge'
import Button from '../common/Button'

interface ResultsPanelProps {
  result: EvaluationResult
  videoId: string
}

const ResultsPanel: FC<ResultsPanelProps> = ({ result, videoId }) => {
  const [videoType, setVideoType] = useState<'labeled' | 'original'>('labeled')
  const [activeTab, setActiveTab] = useState<'summary' | 'evidence'>('summary')

  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8012'
  const videoUrl = videoType === 'labeled'
    ? `${API_URL}/v1/videos/${videoId}/labeled`
    : `${API_URL}/v1/videos/${videoId}/uploaded`

  // Extract scores from criteria_scores or violations
  const scores: Record<string, number> = {}
  if (result.criteria_scores) {
    Object.entries(result.criteria_scores).forEach(([key, val]) => {
      scores[key] = typeof val === 'object' ? val.score : val
    })
  } else if (result.violations) {
    result.violations.forEach(v => {
      scores[v.criterion] = v.score
    })
  }

  // Extract evidence with fallbacks
  const evidence = result.evidence || {}
  const violenceSegments = (evidence as any)?.violence_segments || (evidence as any)?.violence || []

  return (
    <div className="space-y-4">
      {/* Verdict Summary */}
      <div className="card p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-bold text-white">Analysis Result</h3>
          <Badge variant={result.verdict}>{result.verdict}</Badge>
        </div>
        
        {Object.keys(scores).length > 0 && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {Object.entries(scores).map(([key, value]) => (
              <div key={key} className="text-center">
                <p className="text-xs text-gray-400 uppercase mb-1">{key}</p>
                <p className={`text-2xl font-bold ${
                  value > 0.75 ? 'text-danger' :
                  value > 0.40 ? 'text-warning' :
                  'text-success'
                }`}>
                  {formatPercent(value)}
                </p>
              </div>
            ))}
          </div>
        )}

        <div className="mt-3 pt-3 border-t border-gray-800 text-sm text-gray-400">
          {result.processing_time_sec && (
            <span>Processing Time: {result.processing_time_sec.toFixed(1)}s</span>
          )}
          {(result as any).metadata?.duration && (
            <>
              <span className="mx-2">•</span>
              <span>Duration: {formatDuration((result as any).metadata.duration)}</span>
            </>
          )}
        </div>
      </div>

      {/* Video Player */}
      <div className="card p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-bold text-white">Video Preview</h3>
          <div className="flex gap-2">
            <Button
              variant={videoType === 'labeled' ? 'primary' : 'ghost'}
              onClick={() => setVideoType('labeled')}
              className="!py-1 !px-3 text-sm"
            >
              Labeled
            </Button>
            <Button
              variant={videoType === 'original' ? 'primary' : 'ghost'}
              onClick={() => setVideoType('original')}
              className="!py-1 !px-3 text-sm"
            >
              Original
            </Button>
          </div>
        </div>

        <VideoPlayer
          videoUrl={videoUrl}
          violenceSegments={violenceSegments}
        />
      </div>

      {/* Tabs */}
      <div className="card">
        <div className="flex border-b border-gray-800">
          <button
            className={`flex-1 px-4 py-3 font-medium transition-colors ${
              activeTab === 'summary'
                ? 'text-primary border-b-2 border-primary'
                : 'text-gray-400 hover:text-white'
            }`}
            onClick={() => setActiveTab('summary')}
          >
            Summary
          </button>
          <button
            className={`flex-1 px-4 py-3 font-medium transition-colors ${
              activeTab === 'evidence'
                ? 'text-primary border-b-2 border-primary'
                : 'text-gray-400 hover:text-white'
            }`}
            onClick={() => setActiveTab('evidence')}
          >
            Evidence
          </button>
        </div>

        <div className="p-4 max-h-96 overflow-y-auto">
          {activeTab === 'summary' ? (
            <div className="prose prose-invert prose-sm max-w-none">
              <p className="text-gray-300 whitespace-pre-wrap">
                {result.report || (result as any).summary || 'No summary available'}
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Violence Segments */}
              {violenceSegments.length > 0 && (
                <div>
                  <h4 className="font-semibold text-white mb-2">Violence Detected</h4>
                  <div className="space-y-2">
                    {violenceSegments.map((seg: any, idx: number) => (
                      <div key={idx} className="bg-dark-50 rounded p-2 text-sm">
                        <span className="text-gray-300">
                          {formatDuration(seg.start_time || seg.start || seg.segment * 3)} - 
                          {formatDuration(seg.end_time || seg.end || (seg.segment + 1) * 3)}
                        </span>
                        <span className="ml-2 text-danger font-medium">
                          {formatPercent(seg.score)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Object Detections */}
              {((evidence as any)?.object_detections?.length > 0 || (evidence as any)?.vision?.length > 0) && (
                <div>
                  <h4 className="font-semibold text-white mb-2">Objects Detected</h4>
                  <p className="text-sm text-gray-400">
                    {(evidence as any)?.object_detections?.length || (evidence as any)?.vision?.length || 0} detections
                  </p>
                </div>
              )}

              {/* Audio Transcript */}
              {((evidence as any)?.audio_transcript?.length > 0 || (evidence as any)?.transcript?.length > 0) && (
                <div>
                  <h4 className="font-semibold text-white mb-2">Audio Transcript</h4>
                  <div className="space-y-2">
                    {((evidence as any)?.audio_transcript || (evidence as any)?.transcript || [])
                      .slice(0, 5)
                      .map((item: any, idx: number) => (
                        <div key={idx} className="bg-dark-50 rounded p-2 text-sm">
                          <span className="text-gray-400">
                            [{formatDuration(item.timestamp || item.start || 0)}]
                          </span>
                          <span className="ml-2 text-gray-300">{item.text}</span>
                        </div>
                      ))}
                  </div>
                </div>
              )}

              {/* OCR Results */}
              {((evidence as any)?.ocr_results?.length > 0 || (evidence as any)?.ocr?.length > 0) && (
                <div>
                  <h4 className="font-semibold text-white mb-2">OCR Text Extracted</h4>
                  <div className="space-y-2">
                    {((evidence as any)?.ocr_results || (evidence as any)?.ocr || [])
                      .slice(0, 5)
                      .map((item: any, idx: number) => (
                        <div key={idx} className="bg-dark-50 rounded p-2 text-sm">
                          <span className="text-gray-400">
                            [{formatDuration(item.timestamp || 0)}]
                          </span>
                          <span className="ml-2 text-gray-300">{item.text}</span>
                        </div>
                      ))}
                  </div>
                </div>
              )}
              
              {/* No Evidence Available */}
              {!result.evidence && violenceSegments.length === 0 && (
                <p className="text-gray-500 text-sm">No detailed evidence available</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default ResultsPanel
