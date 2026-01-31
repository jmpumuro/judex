# Codebase Redundancy Report & Consolidation Plan

## Executive Summary

**Total Redundant Code Identified:** ~800-1000 lines across 15+ files
**Critical Issues:** 3 major redundancies requiring immediate attention
**Estimated Effort:** 2-3 weeks for full consolidation
**Risk Level:** Low (mostly deletions and import updates)

---

## Critical Redundancies (Fix Immediately)

### 🔴 1. DUAL API CLIENT SYSTEMS

**Problem:** Two complete API client implementations exist side-by-side

**Files:**
- `api/endpoints.ts` (743 lines) - OLD pattern
- `api/client.ts` (397 lines) - NEW pattern

**Impact:** CRITICAL
- Inconsistent API calls across codebase
- Different parameter names (`async` vs `isAsync`, `criteria` vs `criteriaYaml`)
- Different response handling
- Confusion for developers on which to use

**Used By:**
| Component | Uses OLD (endpoints.ts) | Uses NEW (client.ts) |
|-----------|------------------------|---------------------|
| Pipeline.tsx | ✓ (evaluationApi, stageApi) | ✓ (evaluations) |
| Settings.tsx | ✓ (stagesApi) | |
| useFileUpload.ts | ✓ (evaluationApi) | |
| usePipelineProcessing.ts | ✓ (evaluationApi, stageApi) | |
| ProcessedFrames.tsx | | ✓ (evaluations) |
| ReportChat.tsx | | ✓ (chat) |

**Solution:**
```bash
# 1. Delete the old API client
rm frontend/src/api/endpoints.ts

# 2. Update all imports in these files:
# - pages/Pipeline.tsx
# - pages/Settings.tsx
# - hooks/useFileUpload.ts
# - hooks/usePipelineProcessing.ts

# Change from:
import { evaluationApi, stageApi } from '@/api/endpoints'

# To:
import { evaluations, stages } from '@/api'
```

**Effort:** 2-3 hours
**Risk:** Medium (requires testing all API calls)

---

### 🔴 2. BROKEN HOOK - usePipelineProcessing

**Problem:** Hook calls non-existent API methods

**File:** `hooks/usePipelineProcessing.ts`

**Issues Found:**
```typescript
// Line 98 - Method doesn't exist
const data = await stageApi.getOutput(evaluationId, stageId, itemId)
// Should be: getStageOutput()

// Line 120 - Method doesn't exist
const status = await evaluationApi.getStatus(evaluationId)
// Should be: get()

// Line 245 - Returns wrong type
const blob = await evaluationApi.getUploadedVideoUrl(...)
// Returns URL string, not blob
```

**Impact:** Hook is currently non-functional and will throw errors

**Solution:** Fix all method calls to match actual API client

**Effort:** 1 hour
**Risk:** Low (straightforward fix)

---

### 🔴 3. DUPLICATE TYPE DEFINITIONS

**Problem:** Three overlapping type definition files

**Files:**
- `types/api.ts` (251 lines) - ✅ Modern, complete
- `types/common.ts` (172 lines) - ❌ Legacy, conflicting
- `types/video.ts` (37 lines) - ❌ Unused

**Conflicts:**
```typescript
// Different names for same concept:
// api.ts:
criteria_scores: Record<string, CriterionScore>

// common.ts:
criteria: CriteriaScores  // Different property name!
scores?: SafetyScores     // Or this?

// Result type has 3 names:
EvaluationResult  // api.ts
VideoResult       // common.ts
VideoItem         // video.ts
```

**Impact:** HIGH - Type confusion, compilation errors

**Solution:**
```bash
# Delete legacy type files
rm frontend/src/types/common.ts
rm frontend/src/types/video.ts

# Update imports everywhere to use types/api.ts
```

**Effort:** 1-2 hours
**Risk:** Low (TypeScript will catch issues)

---

## High Priority Redundancies

### 🟡 4. DUPLICATE SSE HOOKS

**Files:**
- `hooks/useSSE.ts` (74 lines) - ❌ Basic, unused
- `hooks/useSSEConnection.ts` (195 lines) - ✅ Advanced, used

**Solution:** Delete `useSSE.ts`

**Effort:** 5 minutes
**Risk:** None (unused file)

---

### 🟡 5. MODAL PATTERN DUPLICATION

**Files:**
- `components/common/Modal.tsx` - Generic reusable modal
- `components/pipeline/UploadModal.tsx` - Custom implementation

**Problem:** UploadModal reimplements modal UI instead of using generic Modal component

**Solution:**
```tsx
// Refactor UploadModal to use Modal component
import Modal from '../common/Modal'

export const UploadModal: FC = ({ onClose }) => {
  return (
    <Modal isOpen={true} onClose={onClose} title="Add Videos" size="sm">
      {/* content */}
    </Modal>
  )
}
```

**Effort:** 30 minutes
**Risk:** Low (visual testing needed)

---

## Medium Priority Redundancies

### 🟢 6. UTILITY FUNCTION DUPLICATION

**Problem:** Time formatting implemented 3 times

**Files:**
- `utils/format.ts` - `formatDuration()` - ✅ Full version with hours
- `components/pipeline/VideoPlayer.tsx` - `formatTime()` - Local copy
- `components/pipeline/ProcessedFrames.tsx` - `formatTimestamp()` - Local copy

**Solution:** Use centralized `formatDuration` everywhere

**Effort:** 15 minutes
**Risk:** None

---

### 🟢 7. HARDCODED API URLS

**Problem:** Components construct URLs instead of using API client

**File:** `components/pipeline/ResultsPanel.tsx`

**Current:**
```typescript
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8012'
const videoUrl = `${API_URL}/v1/videos/${videoId}/labeled`
```

**Should Be:**
```typescript
const videoUrl = evaluations.getLabeledVideoUrl(evaluationId, itemId)
```

**Effort:** 10 minutes
**Risk:** None

---

### 🟢 8. STATE MANAGEMENT CLARITY

**Problem:** `presets` property in two stores means different things

**Files:**
- `pipelineStore.ts` - `presets: CriteriaPreset[]` (evaluation criteria)
- `settingsStore.ts` - `presets: Record<string, PolicyConfig>` (policy thresholds)

**Solution:** Rename for clarity:
```typescript
// pipelineStore.ts
criteriaPresets: CriteriaPreset[]  // Was: presets

// settingsStore.ts
policyPresets: Record<string, PolicyConfig>  // Was: presets
```

**Effort:** 30 minutes
**Risk:** Low (find/replace with testing)

---

## Detailed Consolidation Plan

### Phase 1: Critical Fixes (Week 1)

**Day 1-2: Fix API Client**
- [ ] Create migration script to update imports
- [ ] Update `Pipeline.tsx` to use `api/client.ts`
- [ ] Update `Settings.tsx` to use `api/client.ts`
- [ ] Update `useFileUpload.ts` to use `api/client.ts`
- [ ] Fix `usePipelineProcessing.ts` method calls
- [ ] Delete `api/endpoints.ts`
- [ ] Test all API calls thoroughly

**Day 3: Fix Types**
- [ ] Delete `types/common.ts`
- [ ] Delete `types/video.ts`
- [ ] Update imports in `videoStore.ts`
- [ ] Update imports in `settingsStore.ts`
- [ ] Update imports across all components
- [ ] Run TypeScript compiler to catch issues

**Day 4-5: Testing**
- [ ] Test video upload (local & URL)
- [ ] Test video processing
- [ ] Test stage output display
- [ ] Test all modals and UI interactions
- [ ] Fix any issues found

### Phase 2: High Priority (Week 2)

**Day 1: Remove Unused Code**
- [ ] Delete `hooks/useSSE.ts`
- [ ] Search for any references (should be none)
- [ ] Update `hooks/index.ts` exports

**Day 2: Refactor Modals**
- [ ] Refactor `UploadModal` to use generic `Modal`
- [ ] Test modal animations and styling
- [ ] Ensure all modal features work

**Day 3: Consolidate Utilities**
- [ ] Update `VideoPlayer.tsx` to use `utils/format.ts`
- [ ] Update `ProcessedFrames.tsx` to use `utils/format.ts`
- [ ] Remove local `formatTime` functions
- [ ] Test time display formatting

### Phase 3: Polish (Week 3)

**Day 1: Centralize URLs**
- [ ] Update `ResultsPanel.tsx` to use API client URLs
- [ ] Search for other hardcoded URLs
- [ ] Update all to use API client

**Day 2: Rename for Clarity**
- [ ] Rename `presets` in `pipelineStore.ts` to `criteriaPresets`
- [ ] Rename `presets` in `settingsStore.ts` to `policyPresets`
- [ ] Update all references
- [ ] Test thoroughly

**Day 3-5: Documentation & Testing**
- [ ] Update component documentation
- [ ] Add JSDoc comments to clarify store purposes
- [ ] Full regression testing
- [ ] Update README if needed

---

## Quick Wins (Can Do Today)

These have zero risk and immediate benefit:

```bash
# 1. Delete unused SSE hook (5 minutes)
rm frontend/src/hooks/useSSE.ts

# 2. Add clarifying comments to stores (10 minutes)
# Add to pipelineStore.ts:
/**
 * Criteria presets - define what content to evaluate
 * (violence, hate speech, etc.)
 */
criteriaPresets: CriteriaPreset[]

# Add to settingsStore.ts:
/**
 * Policy presets - define threshold strictness levels
 * (strict, balanced, lenient)
 */
policyPresets: Record<string, PolicyConfig>
```

---

## Testing Checklist

After each phase, verify:

**API Client Migration:**
- [ ] Upload video (local file)
- [ ] Upload video (URL)
- [ ] Process single video
- [ ] Process batch videos
- [ ] Fetch stage outputs
- [ ] Display evaluation results
- [ ] Settings page loads
- [ ] Criteria presets load

**Type Consolidation:**
- [ ] No TypeScript errors
- [ ] Store state properly typed
- [ ] Component props properly typed
- [ ] API responses properly typed

**Component Refactoring:**
- [ ] Upload modal opens/closes
- [ ] Modal styling identical
- [ ] Time formats display correctly
- [ ] Video URLs load properly

---

## Metrics

**Before Consolidation:**
- Total Lines: ~2,500 in affected files
- API Client Lines: 1,140 (both systems)
- Type Definition Lines: 460 (3 files)
- Duplicate Utilities: 3 implementations

**After Consolidation:**
- Total Lines: ~1,700 (↓ 32%)
- API Client Lines: 397 (↓ 65%)
- Type Definition Lines: 251 (↓ 45%)
- Duplicate Utilities: 1 centralized

**Benefits:**
- Single source of truth for APIs
- Consistent type definitions
- Clearer state management
- Easier maintenance
- Better developer experience

---

## Risk Mitigation

**Backup Strategy:**
```bash
# Before starting, create a branch
git checkout -b consolidate-redundancy
git commit -am "Checkpoint before consolidation"
```

**Incremental Approach:**
1. Make one change at a time
2. Test after each change
3. Commit working state
4. If issues, easy to revert

**Testing Safety:**
- Keep old files until new version fully tested
- Run full test suite after each phase
- Manual QA for critical flows

---

## Conclusion

The codebase has accumulated redundancy through iterative development. Consolidating will:

✅ Reduce codebase by ~800 lines
✅ Eliminate confusion from dual implementations
✅ Improve type safety
✅ Simplify maintenance
✅ Speed up development

**Recommended Start:** Phase 1 (API client consolidation) has highest impact.

**Total Effort:** 2-3 weeks with proper testing
**Risk Level:** Low with incremental approach
**Return:** Significantly improved codebase maintainability
