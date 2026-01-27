import { FC, useState } from 'react'
import { VideoResult } from '@/types'
import { formatDuration, formatPercent } from '@/utils/format'
import VideoPlayer from './VideoPlayer'
import Badge from '../common/Badge'
import Button from '../common/Button'

interface ResultsPanelProps {
  result: VideoResult
  videoId: string
}

const ResultsPanel: FC<ResultsPanelProps> = ({ result, videoId }) => {
  const [videoType, setVideoType] = useState<'labeled' | 'original'>('labeled')
  const [activeTab, setActiveTab] = useState<'summary' | 'evidence'>('summary')

  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8012'
  const videoUrl = videoType === 'labeled'
    ? `${API_URL}/v1/videos/${videoId}/labeled`
    : `${API_URL}/v1/videos/${videoId}/uploaded`

  return (
    <div className="space-y-4">
      {/* Verdict Summary */}
      <div className="card p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-bold text-white">Analysis Result</h3>
          <Badge variant={result.verdict}>{result.verdict}</Badge>
        </div>
        
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {Object.entries(result.scores).map(([key, value]) => (
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

        <div className="mt-3 pt-3 border-t border-gray-800 text-sm text-gray-400">
          <span>Processing Time: {result.processing_time_sec.toFixed(1)}s</span>
          <span className="mx-2">•</span>
          <span>Duration: {formatDuration(result.evidence.video_metadata.duration)}</span>
          <span className="mx-2">•</span>
          <span>Resolution: {result.evidence.video_metadata.width}×{result.evidence.video_metadata.height}</span>
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
          violenceSegments={result.evidence.violence_segments}
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
              <p className="text-gray-300 whitespace-pre-wrap">{result.summary}</p>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Violence Segments */}
              {result.evidence.violence_segments.length > 0 && (
                <div>
                  <h4 className="font-semibold text-white mb-2">Violence Detected</h4>
                  <div className="space-y-2">
                    {result.evidence.violence_segments.map((seg, idx) => (
                      <div key={idx} className="bg-dark-50 rounded p-2 text-sm">
                        <span className="text-gray-300">
                          {formatDuration(seg.start_time)} - {formatDuration(seg.end_time)}
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
              {result.evidence.object_detections.detections.length > 0 && (
                <div>
                  <h4 className="font-semibold text-white mb-2">Objects Detected</h4>
                  <p className="text-sm text-gray-400">
                    {result.evidence.object_detections.total_frames_analyzed} frames analyzed
                  </p>
                </div>
              )}

              {/* Audio Transcript */}
              {result.evidence.audio_transcript.length > 0 && (
                <div>
                  <h4 className="font-semibold text-white mb-2">Audio Transcript</h4>
                  <div className="space-y-2">
                    {result.evidence.audio_transcript.slice(0, 5).map((item, idx) => (
                      <div key={idx} className="bg-dark-50 rounded p-2 text-sm">
                        <span className="text-gray-400">[{formatDuration(item.timestamp)}]</span>
                        <span className="ml-2 text-gray-300">{item.text}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* OCR Results */}
              {result.evidence.ocr_results.length > 0 && (
                <div>
                  <h4 className="font-semibold text-white mb-2">OCR Text Extracted</h4>
                  <div className="space-y-2">
                    {result.evidence.ocr_results.slice(0, 5).map((item, idx) => (
                      <div key={idx} className="bg-dark-50 rounded p-2 text-sm">
                        <span className="text-gray-400">[{formatDuration(item.timestamp)}]</span>
                        <span className="ml-2 text-gray-300">{item.text}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default ResultsPanel
