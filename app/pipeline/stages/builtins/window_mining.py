"""
Window Mining stage plugin - identifies candidate time windows for expensive analysis.

This stage analyzes video metadata, motion patterns, and YOLO detections to identify
time windows that are most likely to contain violence or safety-relevant content.
This focuses expensive models (VideoMAE, X-CLIP) on relevant segments.

VIDEO ONLY: Requires motion analysis across multiple frames.

Industry Standard:
- Lightweight preprocessing to reduce computational cost
- Explainable window selection (reasons for each window)
- Configurable sensitivity and max windows
"""
import asyncio
import cv2
import numpy as np
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple, Optional
from dataclasses import dataclass

from app.pipeline.stages.base import StagePlugin, StageSpec, StageImpact, STAGE_IMPACT_DEFAULTS, VIDEO_ONLY, MediaType
from app.core.logging import get_logger
from app.utils.progress import save_stage_output, format_stage_output

logger = get_logger("stages.window_mining")

# Register default impact
STAGE_IMPACT_DEFAULTS["window_mining"] = StageImpact.SUPPORTING


@dataclass
class CandidateWindow:
    """A candidate time window for detailed analysis."""
    start_time: float
    end_time: float
    score: float  # 0-1 priority score
    reasons: List[str]  # Why this window was selected
    cues: Dict[str, Any]  # Debug info: motion_score, person_count, etc.
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_time": round(self.start_time, 2),
            "end_time": round(self.end_time, 2),
            "score": round(self.score, 3),
            "reasons": self.reasons,
            "cues": self.cues,
        }


class WindowMiningStagePlugin(StagePlugin):
    """
    Window mining stage - identifies candidate windows for expensive analysis.
    
    Uses lightweight heuristics:
    1. Motion detection (frame differencing)
    2. Person presence/interaction from YOLO
    3. Object cues (weapons, crowds)
    4. Audio cues (loud segments) if available
    
    VIDEO ONLY: Requires motion analysis across multiple frames.
    """
    
    @property
    def stage_type(self) -> str:
        return "window_mining"
    
    @property
    def display_name(self) -> str:
        return "Window Mining"
    
    @property
    def supported_media_types(self) -> Set[MediaType]:
        """Window mining requires motion (video only)."""
        return VIDEO_ONLY
    
    @property
    def input_keys(self) -> Set[str]:
        return {"video_path", "duration", "sampled_frames"}
    
    @property
    def output_keys(self) -> Set[str]:
        return {"candidate_windows", "window_mining_debug"}
    
    async def run(
        self,
        state: Dict[str, Any],
        spec: StageSpec
    ) -> Dict[str, Any]:
        """Execute window mining to identify candidate segments."""
        logger.info(f"Running window mining stage (id={spec.id})")
        
        video_id = state.get("video_id")
        video_path = state.get("video_path")
        duration = state.get("duration", 0)
        sampled_frames = state.get("sampled_frames", [])
        vision_detections = state.get("vision_detections", [])
        
        # Get configuration
        config = spec.config or {}
        max_windows = config.get("max_windows", 10)
        window_duration = config.get("window_duration", 2.0)  # seconds
        sensitivity = config.get("sensitivity", "balanced")  # low/balanced/high
        
        # Sensitivity thresholds
        thresholds = {
            "low": {"motion": 0.4, "person": 0.3, "interaction": 0.5},
            "balanced": {"motion": 0.25, "person": 0.2, "interaction": 0.35},
            "high": {"motion": 0.15, "person": 0.1, "interaction": 0.2},
        }.get(sensitivity, {"motion": 0.25, "person": 0.2, "interaction": 0.35})
        
        loop = asyncio.get_event_loop()
        
        # Run analysis in thread pool
        candidate_windows, debug_info = await loop.run_in_executor(
            None,
            self._analyze_video,
            video_path,
            duration,
            sampled_frames,
            vision_detections,
            max_windows,
            window_duration,
            thresholds,
        )
        
        # Convert to dicts
        windows_dicts = [w.to_dict() for w in candidate_windows]
        
        # Save stage output
        if video_id:
            save_stage_output(video_id, "window_mining", format_stage_output(
                "window_mining",
                windows_found=len(candidate_windows),
                max_windows=max_windows,
                sensitivity=sensitivity,
                window_duration=window_duration,
                windows=windows_dicts[:5],  # Preview
                coverage_percent=round(
                    sum(w.end_time - w.start_time for w in candidate_windows) / max(duration, 1) * 100, 1
                ) if duration > 0 else 0,
            ))
        
        logger.info(f"Window mining found {len(candidate_windows)} candidate windows")
        
        return {
            "candidate_windows": windows_dicts,
            "window_mining_debug": debug_info,
        }
    
    def _analyze_video(
        self,
        video_path: str,
        duration: float,
        sampled_frames: List[Dict],
        vision_detections: List[Dict],
        max_windows: int,
        window_duration: float,
        thresholds: Dict[str, float],
    ) -> Tuple[List[CandidateWindow], Dict[str, Any]]:
        """
        Analyze video to find candidate windows.
        
        Strategy:
        1. Compute motion scores across time
        2. Identify person interactions from YOLO
        3. Combine signals into window scores
        4. Select top-N non-overlapping windows
        """
        debug_info = {
            "motion_scores": [],
            "person_counts": [],
            "interaction_scores": [],
            "total_frames_analyzed": 0,
        }
        
        if not video_path or duration <= 0:
            return [], debug_info
        
        # Step 1: Motion analysis from sampled frames
        motion_scores = self._compute_motion_scores(sampled_frames)
        debug_info["motion_scores"] = motion_scores[:20]  # Preview
        debug_info["total_frames_analyzed"] = len(sampled_frames)
        
        # Step 2: Person interaction analysis from YOLO
        person_data = self._analyze_person_interactions(vision_detections, duration)
        debug_info["person_counts"] = person_data["counts"][:20]
        debug_info["interaction_scores"] = person_data["interactions"][:20]
        
        # Step 3: Object cue analysis (weapons, crowds)
        object_cues = self._analyze_object_cues(vision_detections)
        debug_info["object_cues"] = object_cues
        
        # Step 4: Combine into time-based scores
        window_scores = self._compute_window_scores(
            duration,
            window_duration,
            motion_scores,
            sampled_frames,
            person_data,
            object_cues,
            thresholds,
        )
        
        # Step 5: Select top windows (non-overlapping)
        candidate_windows = self._select_top_windows(
            window_scores,
            max_windows,
            window_duration,
        )
        
        return candidate_windows, debug_info
    
    def _compute_motion_scores(
        self,
        sampled_frames: List[Dict]
    ) -> List[Dict[str, Any]]:
        """
        Compute motion scores using frame differencing.
        
        Returns list of {timestamp, motion_score} for each frame pair.
        """
        motion_scores = []
        prev_frame = None
        
        for frame_info in sampled_frames:
            frame_path = frame_info.get("path", "")
            timestamp = frame_info.get("timestamp", 0)
            
            if not frame_path or not Path(frame_path).exists():
                motion_scores.append({"timestamp": timestamp, "motion_score": 0.0})
                continue
            
            try:
                frame = cv2.imread(frame_path, cv2.IMREAD_GRAYSCALE)
                if frame is None:
                    motion_scores.append({"timestamp": timestamp, "motion_score": 0.0})
                    continue
                
                # Resize for efficiency
                frame = cv2.resize(frame, (160, 90))
                
                if prev_frame is not None:
                    # Frame difference
                    diff = cv2.absdiff(frame, prev_frame)
                    motion_score = float(np.mean(diff)) / 255.0
                    motion_scores.append({
                        "timestamp": timestamp,
                        "motion_score": round(motion_score, 4)
                    })
                else:
                    motion_scores.append({"timestamp": timestamp, "motion_score": 0.0})
                
                prev_frame = frame
                
            except Exception as e:
                logger.warning(f"Motion analysis failed for frame: {e}")
                motion_scores.append({"timestamp": timestamp, "motion_score": 0.0})
        
        return motion_scores
    
    def _analyze_person_interactions(
        self,
        vision_detections: List[Dict],
        duration: float
    ) -> Dict[str, Any]:
        """
        Analyze YOLO detections for person presence and interactions.
        
        Interaction cues:
        - Multiple persons in close proximity
        - Rapid movement (bounding box changes)
        - Overlapping bounding boxes
        """
        person_counts = []
        interaction_scores = []
        
        # Group detections by timestamp
        detections_by_time: Dict[float, List[Dict]] = {}
        for det in vision_detections:
            ts = det.get("timestamp", 0)
            if ts not in detections_by_time:
                detections_by_time[ts] = []
            detections_by_time[ts].append(det)
        
        for ts in sorted(detections_by_time.keys()):
            dets = detections_by_time[ts]
            
            # Count persons
            persons = [d for d in dets if d.get("label", "").lower() == "person"]
            person_count = len(persons)
            person_counts.append({"timestamp": ts, "count": person_count})
            
            # Compute interaction score
            interaction_score = 0.0
            if person_count >= 2:
                # Check for close proximity
                boxes = [d.get("box", {}) for d in persons]
                interaction_score = self._compute_proximity_score(boxes)
            
            interaction_scores.append({
                "timestamp": ts,
                "interaction_score": round(interaction_score, 3)
            })
        
        return {
            "counts": person_counts,
            "interactions": interaction_scores,
        }
    
    def _compute_proximity_score(self, boxes: List[Dict]) -> float:
        """Compute how close persons are to each other (0-1)."""
        if len(boxes) < 2:
            return 0.0
        
        min_distance = float("inf")
        
        for i, box1 in enumerate(boxes):
            for j, box2 in enumerate(boxes):
                if i >= j:
                    continue
                
                # Get box centers
                x1 = (box1.get("x1", 0) + box1.get("x2", 0)) / 2
                y1 = (box1.get("y1", 0) + box1.get("y2", 0)) / 2
                x2 = (box2.get("x1", 0) + box2.get("x2", 0)) / 2
                y2 = (box2.get("y1", 0) + box2.get("y2", 0)) / 2
                
                distance = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
                min_distance = min(min_distance, distance)
        
        # Normalize: closer = higher score
        # Assume frame width ~640, so 100px is close
        if min_distance < 50:
            return 1.0
        elif min_distance < 100:
            return 0.8
        elif min_distance < 200:
            return 0.5
        elif min_distance < 300:
            return 0.3
        return 0.1
    
    def _analyze_object_cues(
        self,
        vision_detections: List[Dict]
    ) -> List[Dict[str, Any]]:
        """
        Identify object-based cues for violence.
        
        Objects of interest: knife, gun, bat, stick, blood, fire
        """
        weapon_labels = {"knife", "gun", "rifle", "pistol", "bat", "stick", "sword", "weapon"}
        danger_labels = {"blood", "fire", "smoke", "explosion"}
        
        cues = []
        for det in vision_detections:
            label = det.get("label", "").lower()
            if label in weapon_labels or label in danger_labels:
                cues.append({
                    "timestamp": det.get("timestamp", 0),
                    "label": label,
                    "confidence": det.get("confidence", 0),
                    "cue_type": "weapon" if label in weapon_labels else "danger",
                })
        
        return cues
    
    def _compute_window_scores(
        self,
        duration: float,
        window_duration: float,
        motion_scores: List[Dict],
        sampled_frames: List[Dict],
        person_data: Dict[str, Any],
        object_cues: List[Dict],
        thresholds: Dict[str, float],
    ) -> List[CandidateWindow]:
        """
        Compute scores for each possible window.
        """
        windows = []
        step = window_duration / 2  # 50% overlap
        
        current_time = 0.0
        while current_time + window_duration <= duration:
            end_time = current_time + window_duration
            
            # Get signals in this window
            window_motion = [
                m["motion_score"] for m in motion_scores
                if current_time <= m["timestamp"] < end_time
            ]
            
            window_persons = [
                p["count"] for p in person_data["counts"]
                if current_time <= p["timestamp"] < end_time
            ]
            
            window_interactions = [
                i["interaction_score"] for i in person_data["interactions"]
                if current_time <= i["timestamp"] < end_time
            ]
            
            window_objects = [
                c for c in object_cues
                if current_time <= c["timestamp"] < end_time
            ]
            
            # Compute sub-scores
            motion_score = max(window_motion) if window_motion else 0.0
            person_score = min(max(window_persons) / 5.0, 1.0) if window_persons else 0.0
            interaction_score = max(window_interactions) if window_interactions else 0.0
            object_score = min(len(window_objects) / 3.0, 1.0)
            
            # Build reasons
            reasons = []
            cues = {
                "motion_score": round(motion_score, 3),
                "person_score": round(person_score, 3),
                "interaction_score": round(interaction_score, 3),
                "object_score": round(object_score, 3),
            }
            
            if motion_score >= thresholds["motion"]:
                reasons.append(f"High motion ({motion_score:.2f})")
            if person_score >= thresholds["person"]:
                reasons.append(f"Multiple persons ({int(max(window_persons) if window_persons else 0)})")
            if interaction_score >= thresholds["interaction"]:
                reasons.append(f"Person interaction ({interaction_score:.2f})")
            if object_score > 0:
                labels = list(set(c["label"] for c in window_objects))
                reasons.append(f"Objects detected: {', '.join(labels)}")
            
            # Combined score (weighted)
            combined_score = (
                motion_score * 0.3 +
                person_score * 0.2 +
                interaction_score * 0.3 +
                object_score * 0.2
            )
            
            # Only include windows with some signal
            if reasons or combined_score > 0.1:
                windows.append(CandidateWindow(
                    start_time=current_time,
                    end_time=end_time,
                    score=combined_score,
                    reasons=reasons if reasons else ["Low-level activity"],
                    cues=cues,
                ))
            
            current_time += step
        
        return windows
    
    def _select_top_windows(
        self,
        all_windows: List[CandidateWindow],
        max_windows: int,
        window_duration: float,
    ) -> List[CandidateWindow]:
        """
        Select top non-overlapping windows by score.
        """
        if not all_windows:
            return []
        
        # Sort by score descending
        sorted_windows = sorted(all_windows, key=lambda w: w.score, reverse=True)
        
        selected = []
        for window in sorted_windows:
            if len(selected) >= max_windows:
                break
            
            # Check for overlap with already selected
            overlaps = False
            for sel in selected:
                if not (window.end_time <= sel.start_time or window.start_time >= sel.end_time):
                    overlaps = True
                    break
            
            if not overlaps:
                selected.append(window)
        
        # Sort by time for output
        selected.sort(key=lambda w: w.start_time)
        
        return selected
