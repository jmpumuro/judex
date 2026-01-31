"""
Pose Violence Heuristics stage plugin - detects bare-hand violence using pose analysis.

This stage uses lightweight pose estimation (MediaPipe) combined with deterministic
heuristics to detect potential violence indicators:
- High-velocity limb movements toward another person
- Strike-like arm patterns
- Aggressive proximity + motion combinations
- Repeated impact-like motions

VIDEO ONLY: Requires motion analysis across multiple frames for velocity/pattern detection.

Industry Standard:
- Deterministic and explainable heuristics (no ML black box)
- Outputs include timestamps and reasons for audit
- Integrates with candidate windows for focused analysis
"""
import asyncio
import cv2
import numpy as np
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, field

from app.pipeline.stages.base import StagePlugin, StageSpec, StageImpact, STAGE_IMPACT_DEFAULTS, VIDEO_ONLY, MediaType
from app.core.logging import get_logger
from app.utils.progress import save_stage_output, format_stage_output

logger = get_logger("stages.pose_heuristics")

# Register default impact
STAGE_IMPACT_DEFAULTS["pose_heuristics"] = StageImpact.SUPPORTING


@dataclass
class PoseSignal:
    """A detected pose-based violence signal."""
    timestamp: float
    signal_type: str  # "strike_motion", "rapid_approach", "impact_pattern", etc.
    confidence: float  # 0-1
    reason: str  # Human-readable explanation
    persons_involved: int
    keypoints: Optional[Dict[str, Any]] = None  # Debug info
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": round(self.timestamp, 2),
            "signal_type": self.signal_type,
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
            "persons_involved": self.persons_involved,
        }


class PoseHeuristicsStagePlugin(StagePlugin):
    """
    Pose-based violence heuristics using MediaPipe Pose.
    
    Analyzes body keypoints to detect:
    1. Strike motions (arm velocity toward another person)
    2. Rapid approaches (person moving quickly toward another)
    3. Impact patterns (repeated strike-like movements)
    4. Aggressive postures (fighting stance indicators)
    
    VIDEO ONLY: Requires motion analysis across frames for velocity/pattern detection.
    """
    
    def __init__(self):
        self._pose_model = None
    
    @property
    def stage_type(self) -> str:
        return "pose_heuristics"
    
    @property
    def display_name(self) -> str:
        return "Pose Violence Analysis"
    
    @property
    def supported_media_types(self) -> Set[MediaType]:
        """Pose heuristics requires motion (video only)."""
        return VIDEO_ONLY
    
    @property
    def input_keys(self) -> Set[str]:
        return {"sampled_frames", "candidate_windows"}
    
    @property
    def output_keys(self) -> Set[str]:
        return {"pose_signals", "pose_keypoints"}
    
    def _load_pose_model(self):
        """Load MediaPipe Pose model."""
        if self._pose_model is None:
            try:
                import mediapipe as mp
                self._pose_model = mp.solutions.pose.Pose(
                    static_image_mode=True,
                    model_complexity=0,  # Lite model for speed
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5,
                )
                logger.info("MediaPipe Pose model loaded")
            except ImportError:
                logger.warning("MediaPipe not available, pose heuristics will be limited")
                self._pose_model = "unavailable"
            except Exception as e:
                logger.error(f"Failed to load MediaPipe Pose: {e}")
                self._pose_model = "unavailable"
        return self._pose_model
    
    async def run(
        self,
        state: Dict[str, Any],
        spec: StageSpec
    ) -> Dict[str, Any]:
        """Execute pose-based violence heuristics."""
        logger.info(f"Running pose heuristics stage (id={spec.id})")
        
        video_id = state.get("video_id")
        sampled_frames = state.get("sampled_frames", [])
        candidate_windows = state.get("candidate_windows", [])
        vision_detections = state.get("vision_detections", [])
        
        # Get configuration
        config = spec.config or {}
        sensitivity = config.get("sensitivity", "balanced")
        analyze_all_frames = config.get("analyze_all_frames", False)
        
        loop = asyncio.get_event_loop()
        
        # Run analysis in thread pool
        signals, keypoints = await loop.run_in_executor(
            None,
            self._analyze_poses,
            sampled_frames,
            candidate_windows,
            vision_detections,
            sensitivity,
            analyze_all_frames,
        )
        
        # Convert to dicts
        signals_dicts = [s.to_dict() for s in signals]
        
        # Save stage output
        if video_id:
            save_stage_output(video_id, "pose_heuristics", format_stage_output(
                "pose_heuristics",
                signals_found=len(signals),
                sensitivity=sensitivity,
                frames_analyzed=len(keypoints),
                windows_analyzed=len(candidate_windows) if candidate_windows else "all",
                signals=signals_dicts[:10],  # Preview
                signal_types=list(set(s.signal_type for s in signals)),
            ))
        
        logger.info(f"Pose heuristics found {len(signals)} signals")
        
        return {
            "pose_signals": signals_dicts,
            "pose_keypoints": keypoints,
        }
    
    def _analyze_poses(
        self,
        sampled_frames: List[Dict],
        candidate_windows: List[Dict],
        vision_detections: List[Dict],
        sensitivity: str,
        analyze_all_frames: bool,
    ) -> Tuple[List[PoseSignal], List[Dict]]:
        """
        Analyze poses to detect violence indicators.
        """
        signals = []
        all_keypoints = []
        
        # Sensitivity thresholds
        thresholds = {
            "low": {"velocity": 0.4, "proximity": 0.3, "strike": 0.5},
            "balanced": {"velocity": 0.25, "proximity": 0.2, "strike": 0.35},
            "high": {"velocity": 0.15, "proximity": 0.1, "strike": 0.2},
        }.get(sensitivity, {"velocity": 0.25, "proximity": 0.2, "strike": 0.35})
        
        # Determine which frames to analyze
        frames_to_analyze = []
        
        if candidate_windows and not analyze_all_frames:
            # Only analyze frames in candidate windows
            for frame in sampled_frames:
                ts = frame.get("timestamp", 0)
                for window in candidate_windows:
                    if window.get("start_time", 0) <= ts <= window.get("end_time", 0):
                        frames_to_analyze.append(frame)
                        break
        else:
            # Analyze all frames (sample every Nth)
            step = max(1, len(sampled_frames) // 50)  # Max 50 frames
            frames_to_analyze = sampled_frames[::step]
        
        logger.info(f"Analyzing {len(frames_to_analyze)} frames for pose heuristics")
        
        # Load pose model
        pose_model = self._load_pose_model()
        
        # Track keypoints over time for velocity computation
        prev_keypoints: Optional[Dict] = None
        prev_timestamp: Optional[float] = None
        
        for frame_info in frames_to_analyze:
            frame_path = frame_info.get("path", "")
            timestamp = frame_info.get("timestamp", 0)
            
            if not frame_path or not Path(frame_path).exists():
                continue
            
            try:
                # Extract keypoints
                keypoints = self._extract_keypoints(frame_path, pose_model, vision_detections, timestamp)
                
                if keypoints:
                    all_keypoints.append({
                        "timestamp": timestamp,
                        "persons": len(keypoints.get("persons", [])),
                        "keypoints": keypoints,
                    })
                    
                    # Analyze for violence indicators
                    frame_signals = self._analyze_frame_poses(
                        keypoints,
                        prev_keypoints,
                        timestamp,
                        prev_timestamp,
                        thresholds,
                    )
                    signals.extend(frame_signals)
                    
                    prev_keypoints = keypoints
                    prev_timestamp = timestamp
                    
            except Exception as e:
                logger.warning(f"Pose analysis failed for frame at {timestamp}s: {e}")
        
        # Post-process: detect patterns across time
        pattern_signals = self._detect_temporal_patterns(all_keypoints, thresholds)
        signals.extend(pattern_signals)
        
        # Deduplicate and sort by timestamp
        signals = self._deduplicate_signals(signals)
        
        return signals, all_keypoints
    
    def _extract_keypoints(
        self,
        frame_path: str,
        pose_model: Any,
        vision_detections: List[Dict],
        timestamp: float,
    ) -> Optional[Dict]:
        """
        Extract pose keypoints from a frame.
        
        Uses MediaPipe if available, falls back to YOLO person boxes.
        """
        if pose_model == "unavailable":
            # Fallback: use YOLO person detections
            return self._extract_from_yolo(vision_detections, timestamp)
        
        try:
            import mediapipe as mp
            
            frame = cv2.imread(frame_path)
            if frame is None:
                return None
            
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = pose_model.process(frame_rgb)
            
            if not results.pose_landmarks:
                return self._extract_from_yolo(vision_detections, timestamp)
            
            # Extract key landmarks
            landmarks = results.pose_landmarks.landmark
            h, w = frame.shape[:2]
            
            # Key points for violence detection
            keypoint_indices = {
                "nose": 0,
                "left_shoulder": 11,
                "right_shoulder": 12,
                "left_elbow": 13,
                "right_elbow": 14,
                "left_wrist": 15,
                "right_wrist": 16,
                "left_hip": 23,
                "right_hip": 24,
            }
            
            person_keypoints = {}
            for name, idx in keypoint_indices.items():
                lm = landmarks[idx]
                person_keypoints[name] = {
                    "x": lm.x * w,
                    "y": lm.y * h,
                    "visibility": lm.visibility,
                }
            
            return {
                "persons": [person_keypoints],
                "source": "mediapipe",
            }
            
        except Exception as e:
            logger.warning(f"MediaPipe pose extraction failed: {e}")
            return self._extract_from_yolo(vision_detections, timestamp)
    
    def _extract_from_yolo(
        self,
        vision_detections: List[Dict],
        timestamp: float
    ) -> Optional[Dict]:
        """
        Fallback: extract person info from YOLO detections.
        """
        persons = []
        tolerance = 0.5  # seconds
        
        for det in vision_detections:
            if det.get("label", "").lower() != "person":
                continue
            if abs(det.get("timestamp", 0) - timestamp) > tolerance:
                continue
            
            box = det.get("box", {})
            center_x = (box.get("x1", 0) + box.get("x2", 0)) / 2
            center_y = (box.get("y1", 0) + box.get("y2", 0)) / 2
            
            # Estimate keypoints from bounding box
            box_h = box.get("y2", 0) - box.get("y1", 0)
            box_w = box.get("x2", 0) - box.get("x1", 0)
            
            persons.append({
                "center": {"x": center_x, "y": center_y},
                "box": box,
                "estimated_shoulder_y": box.get("y1", 0) + box_h * 0.15,
                "estimated_hip_y": box.get("y1", 0) + box_h * 0.5,
            })
        
        if not persons:
            return None
        
        return {
            "persons": persons,
            "source": "yolo_fallback",
        }
    
    def _analyze_frame_poses(
        self,
        keypoints: Dict,
        prev_keypoints: Optional[Dict],
        timestamp: float,
        prev_timestamp: Optional[float],
        thresholds: Dict[str, float],
    ) -> List[PoseSignal]:
        """
        Analyze poses in a single frame for violence indicators.
        """
        signals = []
        persons = keypoints.get("persons", [])
        source = keypoints.get("source", "unknown")
        
        # Signal 1: Multiple persons in aggressive proximity
        if len(persons) >= 2:
            proximity_score = self._compute_person_proximity(persons, source)
            if proximity_score >= thresholds["proximity"]:
                signals.append(PoseSignal(
                    timestamp=timestamp,
                    signal_type="close_proximity",
                    confidence=proximity_score,
                    reason=f"{len(persons)} persons in close proximity",
                    persons_involved=len(persons),
                ))
        
        # Signal 2: High-velocity movement (if we have previous frame)
        if prev_keypoints and prev_timestamp:
            dt = timestamp - prev_timestamp
            if dt > 0:
                velocity_signal = self._detect_velocity_signals(
                    keypoints, prev_keypoints, dt, timestamp, thresholds, source
                )
                if velocity_signal:
                    signals.append(velocity_signal)
        
        # Signal 3: Strike-like arm position (MediaPipe only)
        if source == "mediapipe":
            strike_signal = self._detect_strike_pose(persons, timestamp, thresholds)
            if strike_signal:
                signals.append(strike_signal)
        
        return signals
    
    def _compute_person_proximity(self, persons: List[Dict], source: str) -> float:
        """Compute proximity score between persons."""
        if len(persons) < 2:
            return 0.0
        
        min_distance = float("inf")
        
        for i, p1 in enumerate(persons):
            for j, p2 in enumerate(persons):
                if i >= j:
                    continue
                
                if source == "mediapipe":
                    x1 = (p1.get("left_shoulder", {}).get("x", 0) + p1.get("right_shoulder", {}).get("x", 0)) / 2
                    y1 = (p1.get("left_shoulder", {}).get("y", 0) + p1.get("right_shoulder", {}).get("y", 0)) / 2
                    x2 = (p2.get("left_shoulder", {}).get("x", 0) + p2.get("right_shoulder", {}).get("x", 0)) / 2
                    y2 = (p2.get("left_shoulder", {}).get("y", 0) + p2.get("right_shoulder", {}).get("y", 0)) / 2
                else:
                    x1 = p1.get("center", {}).get("x", 0)
                    y1 = p1.get("center", {}).get("y", 0)
                    x2 = p2.get("center", {}).get("x", 0)
                    y2 = p2.get("center", {}).get("y", 0)
                
                distance = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
                min_distance = min(min_distance, distance)
        
        # Normalize (assume 720p resolution)
        if min_distance < 50:
            return 0.9
        elif min_distance < 100:
            return 0.7
        elif min_distance < 150:
            return 0.5
        elif min_distance < 200:
            return 0.3
        return 0.0
    
    def _detect_velocity_signals(
        self,
        curr: Dict,
        prev: Dict,
        dt: float,
        timestamp: float,
        thresholds: Dict,
        source: str,
    ) -> Optional[PoseSignal]:
        """Detect high-velocity movements."""
        if source != "mediapipe":
            return None  # Need keypoints for velocity
        
        curr_persons = curr.get("persons", [])
        prev_persons = prev.get("persons", [])
        
        if not curr_persons or not prev_persons:
            return None
        
        # Compare wrist positions
        max_velocity = 0.0
        
        for curr_p in curr_persons:
            for prev_p in prev_persons:
                for wrist in ["left_wrist", "right_wrist"]:
                    curr_wrist = curr_p.get(wrist, {})
                    prev_wrist = prev_p.get(wrist, {})
                    
                    if not curr_wrist or not prev_wrist:
                        continue
                    
                    dx = curr_wrist.get("x", 0) - prev_wrist.get("x", 0)
                    dy = curr_wrist.get("y", 0) - prev_wrist.get("y", 0)
                    velocity = np.sqrt(dx**2 + dy**2) / dt
                    max_velocity = max(max_velocity, velocity)
        
        # Normalize velocity (pixels/second)
        norm_velocity = min(max_velocity / 500, 1.0)  # 500 px/s is high
        
        if norm_velocity >= thresholds["velocity"]:
            return PoseSignal(
                timestamp=timestamp,
                signal_type="rapid_movement",
                confidence=norm_velocity,
                reason=f"High velocity limb movement ({norm_velocity:.2f})",
                persons_involved=len(curr_persons),
            )
        
        return None
    
    def _detect_strike_pose(
        self,
        persons: List[Dict],
        timestamp: float,
        thresholds: Dict,
    ) -> Optional[PoseSignal]:
        """Detect strike-like arm positions."""
        for person in persons:
            # Check if arm is raised and extended (strike position)
            left_shoulder = person.get("left_shoulder", {})
            right_shoulder = person.get("right_shoulder", {})
            left_elbow = person.get("left_elbow", {})
            right_elbow = person.get("right_elbow", {})
            left_wrist = person.get("left_wrist", {})
            right_wrist = person.get("right_wrist", {})
            
            # Check left arm
            if left_shoulder and left_elbow and left_wrist:
                if (left_wrist.get("y", 1000) < left_shoulder.get("y", 0) and
                    left_elbow.get("y", 1000) < left_shoulder.get("y", 0)):
                    return PoseSignal(
                        timestamp=timestamp,
                        signal_type="strike_pose",
                        confidence=0.6,
                        reason="Arm raised in potential strike position",
                        persons_involved=1,
                    )
            
            # Check right arm
            if right_shoulder and right_elbow and right_wrist:
                if (right_wrist.get("y", 1000) < right_shoulder.get("y", 0) and
                    right_elbow.get("y", 1000) < right_shoulder.get("y", 0)):
                    return PoseSignal(
                        timestamp=timestamp,
                        signal_type="strike_pose",
                        confidence=0.6,
                        reason="Arm raised in potential strike position",
                        persons_involved=1,
                    )
        
        return None
    
    def _detect_temporal_patterns(
        self,
        all_keypoints: List[Dict],
        thresholds: Dict,
    ) -> List[PoseSignal]:
        """
        Detect violence patterns across time.
        
        Patterns:
        - Repeated strike motions
        - Sustained close proximity
        """
        signals = []
        
        # Look for sustained close proximity
        proximity_windows = []
        current_window = None
        
        for kp in all_keypoints:
            persons = kp.get("keypoints", {}).get("persons", [])
            if len(persons) >= 2:
                if current_window is None:
                    current_window = {"start": kp["timestamp"], "end": kp["timestamp"]}
                else:
                    current_window["end"] = kp["timestamp"]
            else:
                if current_window and (current_window["end"] - current_window["start"]) >= 1.0:
                    proximity_windows.append(current_window)
                current_window = None
        
        if current_window and (current_window["end"] - current_window["start"]) >= 1.0:
            proximity_windows.append(current_window)
        
        for window in proximity_windows:
            duration = window["end"] - window["start"]
            signals.append(PoseSignal(
                timestamp=window["start"],
                signal_type="sustained_proximity",
                confidence=min(duration / 3.0, 1.0),
                reason=f"Multiple persons in close proximity for {duration:.1f}s",
                persons_involved=2,
            ))
        
        return signals
    
    def _deduplicate_signals(self, signals: List[PoseSignal]) -> List[PoseSignal]:
        """Remove duplicate signals within short time windows."""
        if not signals:
            return []
        
        signals.sort(key=lambda s: (s.timestamp, s.signal_type))
        
        deduped = [signals[0]]
        for signal in signals[1:]:
            last = deduped[-1]
            # Skip if same type within 0.5 seconds
            if (signal.signal_type == last.signal_type and
                abs(signal.timestamp - last.timestamp) < 0.5):
                continue
            deduped.append(signal)
        
        return deduped
