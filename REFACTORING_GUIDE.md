# Pipeline Refactoring Guide

## What Has Been Completed

### ✅ 1. Zustand Store (`store/pipelineStore.ts`)
A comprehensive pipeline state store has been created with:
- UI state management (modals, panels, selections)
- Stage data with caching
- SSE connection management
- Configuration state (presets, stages)
- All necessary actions and selectors

### ✅ 2. Custom Hooks

#### `hooks/useSSEConnection.ts`
Manages Server-Sent Events for real-time updates:
```tsx
const { connectSSE, disconnectSSE, disconnectAllSSE } = useSSEConnection()

// Connect to SSE for real-time updates
connectSSE(evaluationId, videoId, availableStages)

// Disconnect when done
disconnectSSE(`sse-${evaluationId}`)
```

#### `hooks/usePipelineProcessing.ts`
Handles all video processing operations:
```tsx
const {
  processSingleVideo,
  processAllVideos,
  retryVideo,
  reprocessVideo,
  fetchStageOutput,
  pollEvaluationStatus
} = usePipelineProcessing()

// Process a video
await processSingleVideo(videoId, file)

// Process all queued videos
await processAllVideos(queuedVideos, criteriaId)

// Retry failed video
await retryVideo(videoId)

// Reprocess with new settings
await reprocessVideo(evaluationId, videoId)

// Fetch stage output
const output = await fetchStageOutput(evaluationId, itemId, stageId, videoId)
```

### ✅ 3. Example Component (`components/pipeline/UploadModal.tsx`)
A fully extracted, working UploadModal component demonstrating:
- Using Zustand store for state
- Using video store actions
- Clean separation of concerns
- All original functionality preserved

## How to Continue the Refactoring

### Step 1: Update Pipeline.tsx to Use New Stores

Replace the existing useState calls with Zustand store:

**Before:**
```tsx
const [showUploadModal, setShowUploadModal] = useState(false)
const [uploadSource, setUploadSource] = useState<'local' | 'url' | 'storage' | 'database'>('local')
const [selectedStage, setSelectedStage] = useState<string | null>(null)
// ... many more useState calls
```

**After:**
```tsx
// Import the store
import { usePipelineStore } from '@/store/pipelineStore'

// In component
const showUploadModal = usePipelineStore(state => state.showUploadModal)
const setShowUploadModal = usePipelineStore(state => state.setShowUploadModal)
const selectedStage = usePipelineStore(state => state.selectedStage)
const setSelectedStage = usePipelineStore(state => state.setSelectedStage)
// ... etc
```

### Step 2: Replace Processing Logic with Hooks

**Before:**
```tsx
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
      connectSSE(response.id, videoId)
      pollEvaluationStatus(response.id)
    }
  } catch (error: any) {
    updateVideo(videoId, { status: 'failed', error: error.message })
    toast.error('Failed to process video')
  }
}
```

**After:**
```tsx
import { usePipelineProcessing } from '@/hooks/usePipelineProcessing'

// In component
const { processSingleVideo } = usePipelineProcessing()

// Use directly - all logic is in the hook
<button onClick={() => {
  const video = getVideoById(videoId)
  if (video?.file) {
    processSingleVideo(videoId, video.file)
  }
}}>
  Process
</button>
```

### Step 3: Replace SSE Logic with Hook

**Before:**
```tsx
const connectSSE = (evaluationId: string, queueVideoId: string, retryCount = 0) => {
  // Close existing connection
  const existingKey = `sse-${evaluationId}`
  if (sseConnectionsRef.current.has(existingKey)) {
    sseConnectionsRef.current.get(existingKey)?.close()
  }

  // ... 60+ lines of SSE logic
}
```

**After:**
```tsx
import { useSSEConnection } from '@/hooks/useSSEConnection'

// In component
const { connectSSE } = useSSEConnection()

// Use directly - all logic is in the hook
connectSSE(evaluationId, videoId, availableStages)
```

### Step 4: Replace Upload Modal with Component

**Before:**
```tsx
{showUploadModal && (
  <div className="fixed inset-0 bg-black/90 flex items-center justify-center z-50">
    {/* 50+ lines of upload modal JSX */}
  </div>
)}
```

**After:**
```tsx
import { UploadModal } from '@/components/pipeline/UploadModal'

{showUploadModal && (
  <UploadModal onClose={() => setShowUploadModal(false)} />
)}
```

### Step 5: Extract Additional Components

Following the UploadModal pattern, extract other large sections:

#### PipelineHeader Component
Extract the header with criteria selector and action buttons:
```tsx
// components/pipeline/PipelineHeader.tsx
export const PipelineHeader: FC<Props> = ({ ... }) => {
  const selectedPreset = usePipelineStore(state => state.selectedPreset)
  const setSelectedPreset = usePipelineStore(state => state.setSelectedPreset)
  const setShowUploadModal = usePipelineStore(state => state.setShowUploadModal)

  return (
    <div className="p-2 border-b border-gray-800 flex items-center justify-between">
      {/* Criteria selector */}
      {/* Add video button */}
      {/* Evaluate button */}
      {/* Clear all button */}
    </div>
  )
}
```

#### VideoQueue Component
Extract the left sidebar queue list:
```tsx
// components/pipeline/VideoQueue.tsx
export const VideoQueue: FC = () => {
  const queue = useQueue()
  const selectedVideoId = useVideoStore(state => state.selectedVideoId)
  const { selectVideo, removeVideo } = useVideoStoreActions()

  return (
    <div className="flex-shrink-0 w-48 border-r border-gray-800 overflow-y-auto">
      {queue.map(video => (
        <VideoQueueItem
          key={video.id}
          video={video}
          isSelected={video.id === selectedVideoId}
          onSelect={() => selectVideo(video.id)}
          onDelete={() => removeVideo(video.id)}
        />
      ))}
    </div>
  )
}
```

#### StageOutputPanel Component
Extract the right panel that shows stage output or chat:
```tsx
// components/pipeline/StageOutputPanel.tsx
export const StageOutputPanel: FC<Props> = ({ ... }) => {
  const selectedStage = usePipelineStore(state => state.selectedStage)
  const stageOutput = usePipelineStore(state => state.stageOutput)
  const showChat = usePipelineStore(state => state.showChat)

  if (showChat) {
    return <ReportChat {...props} />
  }

  if (selectedStage && stageOutput) {
    return <StageOutput stage={selectedStage} data={stageOutput} />
  }

  return <EmptyState />
}
```

## Component Extraction Checklist

When extracting a component, follow this checklist:

### 1. Identify State Dependencies
- [ ] List all state variables the component uses
- [ ] Determine if state should be in Zustand or remain local
- [ ] Check for any refs or side effects

### 2. Extract Component
- [ ] Create new file in appropriate directory
- [ ] Import necessary dependencies
- [ ] Define clear prop interface
- [ ] Copy JSX and adapt for props
- [ ] Add proper TypeScript types

### 3. Update Parent Component
- [ ] Import the new component
- [ ] Replace inline JSX with component
- [ ] Pass necessary props
- [ ] Verify functionality

### 4. Test Thoroughly
- [ ] All interactions work
- [ ] Styling is preserved
- [ ] No console errors
- [ ] Performance is maintained

## Migration Strategy

### Phase 1: State Management (Low Risk)
1. Replace useState with usePipelineStore
2. Replace SSE logic with useSSEConnection hook
3. Replace processing logic with usePipelineProcessing hook
4. Test thoroughly

### Phase 2: Component Extraction (Medium Risk)
1. Extract UploadModal (✅ Done)
2. Extract PipelineHeader
3. Extract VideoQueue
4. Extract StageOutputPanel
5. Test after each extraction

### Phase 3: Advanced Refactoring (Higher Risk)
1. Extract stage content generators to separate files
2. Create sub-components for complex stage renderers
3. Optimize re-renders with React.memo
4. Add error boundaries

## Testing After Refactoring

After each change, verify:

### Core Functionality
- [ ] Upload videos (local files and URLs)
- [ ] Process single video
- [ ] Process batch of videos
- [ ] SSE updates work in real-time
- [ ] Polling fallback works
- [ ] Stage selection and output display

### UI/UX
- [ ] All buttons and controls work
- [ ] Styling is identical to original
- [ ] Animations and transitions work
- [ ] No layout shifts or flickers
- [ ] Responsive design maintained

### Edge Cases
- [ ] Empty queue state
- [ ] Failed video handling
- [ ] Retry functionality
- [ ] Reprocess functionality
- [ ] Cache invalidation on reprocess
- [ ] External stages display correctly

### Performance
- [ ] No unnecessary re-renders
- [ ] Batch updates work (no flickering)
- [ ] Stage output caching works
- [ ] Large queues handle smoothly

## Benefits of This Refactoring

### Immediate Benefits
✅ Centralized state management with Zustand
✅ Reusable SSE and processing logic in hooks
✅ Cleaner, more maintainable code
✅ Better TypeScript support
✅ Easier testing and debugging

### Long-term Benefits
✅ Easier to add new features
✅ Better collaboration (multiple devs can work on different components)
✅ Improved code quality
✅ Reduced bugs from scattered state
✅ Better performance potential with granular updates

## Example: Full Migration for processSingleVideo

**Original (inline in Pipeline.tsx):**
```tsx
const processSingleVideo = async (videoId: string) => {
  const video = getVideoById(videoId)
  if (!video || !video.file) {
    toast.error('Video file not available')
    return
  }

  updateVideo(videoId, {
    status: 'processing',
    currentStage: 'ingest_video',
    progress: 0
  })

  try {
    const response = await evaluationApi.create({
      files: [video.file],
      criteriaId: selectedPreset || undefined,
      async: true
    })

    if (response.items?.[0]) {
      const item = response.items[0]
      updateVideo(videoId, {
        itemId: item.id,
        evaluationId: response.id
      })

      evaluationToVideoMap.set(response.id, videoId)
      itemIdToVideoMap.set(item.id, videoId)

      connectSSE(response.id, videoId)
      pollEvaluationStatus(response.id)
    }
  } catch (error: any) {
    console.error('Error processing video:', error)
    updateVideo(videoId, {
      status: 'failed',
      error: error.response?.data?.detail || error.message
    })
    toast.error('Failed to process video')
  }
}
```

**After (using hook):**
```tsx
// In Pipeline.tsx
import { usePipelineProcessing } from '@/hooks/usePipelineProcessing'

const { processSingleVideo } = usePipelineProcessing()

// Usage
<button onClick={() => {
  const video = getVideoById(videoId)
  if (video?.file) {
    processSingleVideo(videoId, video.file)
  }
}}>
  Process Video
</button>
```

All the complex logic is now in the reusable hook, and the component is much simpler!

## Next Steps

1. **Update Pipeline.tsx**: Replace useState with usePipelineStore
2. **Use the hooks**: Replace inline processing/SSE logic with hooks
3. **Extract components**: Follow the UploadModal pattern for other sections
4. **Test thoroughly**: Verify all functionality after each change
5. **Document**: Update component documentation as you go

## Questions?

If you encounter issues during refactoring:
1. Check the existing UploadModal component for reference
2. Verify hook imports and usage
3. Test state updates in isolation
4. Use React DevTools to inspect Zustand store
5. Check browser console for errors

Remember: **Refactor incrementally and test after each change!**
