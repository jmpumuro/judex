"""
Policy fusion node - Research-backed multi-modal scoring and verdict.

Uses evidence from multiple detection stages and applies:
1. Reliability-weighted pooling
2. Coverage normalization
3. Agreement-based confidence adjustment
4. Calibrated thresholds

Reference research:
- Dempster-Shafer Theory for evidence combination
- Atrey et al. (2010) on multimodal fusion
- Platt scaling for score calibration
"""
from typing import Dict, Any, List, Tuple
from app.pipeline.state import PipelineState
from app.core.logging import get_logger
from app.models.yolo26 import YOLO26Detector
from app.utils.progress import send_progress, save_stage_output, format_stage_output

# Import research-backed fusion
from app.fusion.research_fusion import (
    compute_all_scores_research_backed,
    fuse_violence_signals,
    fuse_sexual_signals,
    fuse_profanity_signals,
    fuse_drugs_signals,
    fuse_hate_signals,
)

logger = get_logger("node.policy")


class PolicyEngine:
    """Deterministic policy engine for scoring and verdicts."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.thresholds = config.get("thresholds", {})
        self.weights = config.get("weights", {})
    
    def compute_scores(self, state: PipelineState) -> Dict[str, float]:
        """Compute criterion scores from evidence with reliability-weighted fusion."""
        
        # Extract evidence from all stages
        vision_detections = state.get("vision_detections", [])
        violence_segments = state.get("violence_segments", [])
        transcript_moderation = state.get("transcript_moderation", [])
        ocr_moderation = state.get("ocr_moderation", [])
        
        # New safety stack outputs
        videomae_scores = state.get("videomae_scores", [])
        pose_signals = state.get("pose_signals", [])
        candidate_windows = state.get("candidate_windows", [])
        nsfw_results = state.get("nsfw_results", {})  # NSFW visual detection results
        
        # Violence score with enhanced fusion
        violence_score = self._compute_violence_score(
            violence_segments,
            vision_detections,
            transcript_moderation,
            videomae_scores,
            pose_signals
        )
        
        # Profanity score (swear words/expletives - separate from sexual)
        profanity_score = self._compute_profanity_score(
            transcript_moderation,
            ocr_moderation
        )
        
        # Sexual score - requires VISUAL confirmation (NSFW) or explicit sexual language
        # Industry standard: Profanity alone ≠ Sexual content
        sexual_score = self._compute_sexual_score(
            transcript_moderation,
            ocr_moderation,
            vision_detections,
            nsfw_results  # Pass NSFW visual detection results
        )
        
        # Drugs score
        drugs_score = self._compute_drugs_score(
            transcript_moderation,
            ocr_moderation,
            vision_detections
        )
        
        # Hate score
        hate_score = self._compute_hate_score(
            transcript_moderation,
            ocr_moderation
        )
        
        return {
            "violence": violence_score,
            "profanity": profanity_score,
            "sexual": sexual_score,
            "drugs": drugs_score,
            "hate": hate_score
        }
    
    def _compute_violence_score(
        self,
        violence_segments: List[Dict],
        vision_detections: List[Dict],
        transcript_moderation: List[Dict],
        videomae_scores: List[Dict] = None,
        pose_signals: List[Dict] = None
    ) -> float:
        """
        Compute violence score with reliability-weighted fusion.
        
        Uses multiple specialist models with configurable reliability weights:
        - X-CLIP: General video violence classification
        - VideoMAE: Action-specific violence detection (specialist)
        - Pose Heuristics: Bare-hand interaction patterns
        - YOLO: Weapon detection
        - Transcript: Violence keywords in speech
        """
        weights = self.weights.get("violence", {})
        videomae_scores = videomae_scores or []
        pose_signals = pose_signals or []
        
        # Reliability weights (configurable, bounded 0.0-1.0)
        reliability = {
            "xclip": weights.get("xclip_reliability", 0.75),
            "videomae": weights.get("videomae_reliability", 0.85),  # Specialist model
            "pose": weights.get("pose_reliability", 0.60),          # Heuristic-based
            "yolo_weapons": weights.get("yolo_reliability", 0.90),  # High confidence for weapons
            "transcript": weights.get("transcript_reliability", 0.50)
        }
        
        # === X-CLIP Violence Score ===
        xclip_score = 0.0
        if violence_segments:
            xclip_score = max([s.get("violence_score", 0) for s in violence_segments])
        
        # === VideoMAE Violence Score (specialist) ===
        videomae_score = 0.0
        if videomae_scores:
            # Use max score from action-based violence detection
            videomae_score = max([s.get("score", 0) for s in videomae_scores])
        
        # === Pose Heuristics Score ===
        pose_score = 0.0
        if pose_signals:
            # Count high-confidence violence signals
            high_conf_signals = [s for s in pose_signals if s.get("confidence", 0) > 0.6]
            if high_conf_signals:
                # More signals = higher score, cap at 1.0
                pose_score = min(len(high_conf_signals) * 0.25, 1.0)
        
        # === YOLO Weapons Score ===
        yolo_weapons_score = 0.0
        if vision_detections:
            weapon_classes = {"knife", "gun", "weapon", "pistol", "rifle", "sword", "machete"}
            weapon_detections = [d for d in vision_detections 
                               if d.get("category") == "weapon" or 
                               d.get("label", "").lower() in weapon_classes]
            if weapon_detections:
                # Multiple weapons = higher confidence
                yolo_weapons_score = min(len(weapon_detections) * 0.35, 1.0)
        
        # === Transcript Violence Score ===
        transcript_score = 0.0
        if transcript_moderation:
            scores = [t.get("violence_score", 0.0) for t in transcript_moderation]
            transcript_score = max(scores) if scores else 0.0
        
        # === Reliability-Weighted Fusion ===
        # Normalize weights
        active_signals = []
        if xclip_score > 0:
            active_signals.append(("xclip", xclip_score, reliability["xclip"]))
        if videomae_score > 0:
            active_signals.append(("videomae", videomae_score, reliability["videomae"]))
        if pose_score > 0:
            active_signals.append(("pose", pose_score, reliability["pose"]))
        if yolo_weapons_score > 0:
            active_signals.append(("yolo", yolo_weapons_score, reliability["yolo_weapons"]))
        if transcript_score > 0:
            active_signals.append(("transcript", transcript_score, reliability["transcript"]))
        
        if not active_signals:
            return 0.0
        
        # Weighted average with reliability
        total_weight = sum(r for _, _, r in active_signals)
        weighted_sum = sum(score * r for _, score, r in active_signals)
        base_score = weighted_sum / total_weight if total_weight > 0 else 0.0
        
        # Agreement bonus: Multiple models agreeing increases confidence
        high_scores = [s for _, s, _ in active_signals if s > 0.5]
        if len(high_scores) >= 2:
            agreement_bonus = 0.10  # Boost for corroborating evidence
            base_score = min(base_score + agreement_bonus, 1.0)
        
        # Specialist model override: VideoMAE very high = strong signal
        if videomae_score > 0.8 and reliability["videomae"] > 0.7:
            base_score = max(base_score, videomae_score * 0.95)
        
        return min(base_score, 1.0)
    
    def _compute_profanity_score(
        self,
        transcript_moderation: List[Dict],
        ocr_moderation: List[Dict]
    ) -> float:
        """Compute profanity score with realistic frequency-based scoring."""
        import math
        weights = self.weights.get("profanity", {})
        
        # Transcript profanity - count instances and consider density
        transcript_score = 0.0
        if transcript_moderation:
            # Count total profanity words across all chunks
            total_profanity_count = 0
            total_chunks = len(transcript_moderation)
            max_severity = 0.0
            
            for t in transcript_moderation:
                profanity_words = t.get("profanity_words", [])
                total_profanity_count += len(profanity_words)
                max_severity = max(max_severity, t.get("profanity_score", 0.0))
            
            if total_profanity_count > 0:
                # Frequency score: normalize by chunks (more instances = higher score)
                # 1-2 words: low, 3-5: moderate, 6+: high
                frequency_factor = min(total_profanity_count / 5.0, 1.0)
                
                # Density score: how concentrated is the profanity?
                chunks_with_profanity = sum(1 for t in transcript_moderation if t.get("profanity_score", 0) > 0.3)
                density_factor = chunks_with_profanity / total_chunks if total_chunks > 0 else 0
                
                # Severity score: max severity detected
                severity_factor = max_severity
                
                # Combine with dampening for single instances
                # Single word: ~0.25-0.35, Multiple: scales up
                transcript_score = (
                    frequency_factor * 0.4 +
                    density_factor * 0.3 +
                    severity_factor * 0.3
                )
                
                # Apply square root dampening for low counts (1-2 words)
                if total_profanity_count <= 2:
                    transcript_score = math.sqrt(transcript_score) * 0.6
        
        # OCR profanity
        ocr_score = 0.0
        if ocr_moderation:
            scores = [o.get("profanity_score", 0.0) for o in ocr_moderation]
            ocr_score = max(scores) if scores else 0.0
        
        final_score = (
            transcript_score * weights.get("transcript", 0.7) +
            ocr_score * weights.get("ocr", 0.3)
        )
        
        return min(final_score, 1.0)
    
    def _compute_sexual_score(
        self,
        transcript_moderation: List[Dict],
        ocr_moderation: List[Dict],
        vision_detections: List[Dict],
        nsfw_results: Dict = None
    ) -> float:
        """
        Compute sexual content score with VISUAL CONFIRMATION required.
        
        Industry Standard: Profanity alone ≠ Sexual content.
        - Sexual score requires NSFW visual detection OR explicit sexual language
        - "What the fuck!" → profanity only, NOT sexual
        - Naked person + sexual language → sexual content
        
        Multi-signal approach:
        1. NSFW visual (if available) - primary signal
        2. Explicit sexual language in text - secondary signal
        3. Text alone requires high threshold to trigger without visual
        """
        import math
        weights = self.weights.get("sexual", {})
        nsfw_results = nsfw_results or {}
        
        # === NSFW Visual Detection Score ===
        visual_nsfw_score = 0.0
        has_visual_nsfw = False
        
        if nsfw_results:
            max_nsfw = nsfw_results.get("max_nsfw_score", 0)
            nsfw_frames = nsfw_results.get("nsfw_frames", 0)
            is_nsfw = nsfw_results.get("is_nsfw", False)
            
            if is_nsfw or max_nsfw > 0.7:
                visual_nsfw_score = max_nsfw
                has_visual_nsfw = True
            elif max_nsfw > 0.4:
                visual_nsfw_score = max_nsfw * 0.6  # Moderate visual signal
        
        # === Explicit Sexual Language Score ===
        # Only count EXPLICIT sexual words, not just profanity
        text_sexual_score = 0.0
        has_explicit_text = False
        
        if transcript_moderation:
            # Count ONLY sexual_words (explicit sexual language)
            # NOT profanity_words (which are separate)
            total_sexual_words = sum(len(t.get("sexual_words", [])) for t in transcript_moderation)
            max_text_score = max([t.get("sexual_score", 0.0) for t in transcript_moderation], default=0)
            
            if total_sexual_words > 0:
                has_explicit_text = True
                frequency_factor = min(total_sexual_words / 3.0, 1.0)
                text_sexual_score = (frequency_factor * 0.5 + max_text_score * 0.5)
                
                # Single explicit word still significant but dampened
                if total_sexual_words == 1:
                    text_sexual_score = text_sexual_score * 0.5
        
        # OCR sexual content
        ocr_score = 0.0
        if ocr_moderation:
            scores = [o.get("sexual_score", 0.0) for o in ocr_moderation]
            ocr_score = max(scores) if scores else 0.0
        
        # === Multi-Signal Fusion ===
        # Key principle: Require visual confirmation OR strong text signals
        
        if has_visual_nsfw and has_explicit_text:
            # BOTH visual and text → high confidence sexual content
            final_score = max(visual_nsfw_score, text_sexual_score) * 1.2  # Boost for agreement
            logger.info(f"Sexual content: Visual + Text confirmed (score: {final_score:.2f})")
            
        elif has_visual_nsfw:
            # Visual NSFW without text → still significant but capped
            final_score = visual_nsfw_score * 0.85
            logger.info(f"Sexual content: Visual only (score: {final_score:.2f})")
            
        elif has_explicit_text:
            # Explicit sexual language without visual → moderate signal, dampen more
            # This prevents profanity from inflating sexual score
            final_score = text_sexual_score * 0.5  # Significant dampening without visual
            logger.info(f"Sexual content: Text only (score: {final_score:.2f})")
            
        else:
            # No strong signals → minimal score
            # Only OCR contributes minimally
            final_score = ocr_score * 0.2
        
        return min(final_score, 1.0)
    
    def _compute_drugs_score(
        self,
        transcript_moderation: List[Dict],
        ocr_moderation: List[Dict],
        vision_detections: List[Dict]
    ) -> float:
        """Compute drugs/substance score with frequency consideration."""
        import math
        weights = self.weights.get("drugs", {})
        
        # Transcript - count instances
        transcript_score = 0.0
        if transcript_moderation:
            total_drug_words = sum(len(t.get("drug_words", [])) for t in transcript_moderation)
            max_score = max([t.get("drugs_score", 0.0) for t in transcript_moderation], default=0.0)
            
            if total_drug_words > 0:
                frequency_factor = min(total_drug_words / 4.0, 1.0)
                transcript_score = (frequency_factor * 0.6 + max_score * 0.4)
                
                # Dampen for single instances
                if total_drug_words <= 2:
                    transcript_score = math.sqrt(transcript_score) * 0.6
        
        # OCR
        ocr_score = 0.0
        if ocr_moderation:
            scores = [o.get("drugs_score", 0.0) for o in ocr_moderation]
            ocr_score = max(scores) if scores else 0.0
        
        # YOLO substances
        yolo_score = 0.0
        if vision_detections:
            substance_detections = [d for d in vision_detections if d.get("category") == "substance"]
            if substance_detections:
                yolo_score = min(len(substance_detections) * 0.2, 1.0)
        
        final_score = (
            transcript_score * weights.get("transcript", 0.5) +
            yolo_score * weights.get("yolo", 0.4) +
            ocr_score * weights.get("ocr", 0.1)
        )
        
        return min(final_score, 1.0)
    
    def _compute_hate_score(
        self,
        transcript_moderation: List[Dict],
        ocr_moderation: List[Dict]
    ) -> float:
        """Compute hate/harassment score with frequency consideration."""
        import math
        weights = self.weights.get("hate", {})
        
        # Transcript - count instances
        transcript_score = 0.0
        if transcript_moderation:
            total_hate_words = sum(len(t.get("hate_words", [])) for t in transcript_moderation)
            max_score = max([t.get("hate_score", 0.0) for t in transcript_moderation], default=0.0)
            
            if total_hate_words > 0:
                frequency_factor = min(total_hate_words / 3.0, 1.0)
                transcript_score = (frequency_factor * 0.6 + max_score * 0.4)
                
                # Dampen for single instances
                if total_hate_words <= 1:
                    transcript_score = math.sqrt(transcript_score) * 0.5
        
        # OCR
        ocr_score = 0.0
        if ocr_moderation:
            scores = [o.get("hate_score", 0.0) for o in ocr_moderation]
            ocr_score = max(scores) if scores else 0.0
        
        final_score = (
            transcript_score * weights.get("transcript", 0.7) +
            ocr_score * weights.get("ocr", 0.3)
        )
        
        return min(final_score, 1.0)
    
    def determine_verdict(self, scores: Dict[str, float], state: PipelineState) -> str:
        """
        Determine verdict from scores with multi-signal confirmation.
        
        UNSAFE requires strong evidence + confirming signals (except extreme cases)
        NEEDS_REVIEW for borderline cases or conflicting signals
        """
        unsafe_thresholds = self.thresholds.get("unsafe", {})
        caution_thresholds = self.thresholds.get("caution", {})
        
        # Check for sports/gaming context that might cause false positives
        is_sports_gaming = self._is_sports_gaming_context(state)
        
        # Violence assessment with multi-signal confirmation
        violence_verdict = self._assess_violence(scores, state, is_sports_gaming)
        
        # Hate assessment with multi-signal confirmation
        hate_verdict = self._assess_hate(scores, state)
        
        # Sexual assessment with multi-signal confirmation
        sexual_verdict = self._assess_sexual(scores, state)
        
        # Drugs assessment
        drugs_verdict = self._assess_drugs(scores, state)
        
        # Aggregate verdicts (UNSAFE > NEEDS_REVIEW > CAUTION > SAFE)
        verdicts = [violence_verdict, hate_verdict, sexual_verdict, drugs_verdict]
        
        if "UNSAFE" in verdicts:
            return "UNSAFE"
        elif "NEEDS_REVIEW" in verdicts:
            return "NEEDS_REVIEW"
        elif "CAUTION" in verdicts:
            return "CAUTION"
        else:
            # Simple profanity check (no multi-signal needed)
            if scores["profanity"] >= caution_thresholds.get("profanity", 0.40):
                return "CAUTION"
            return "SAFE"
    
    def _is_sports_gaming_context(self, state: PipelineState) -> bool:
        """Detect if video is sports/gaming content (common false positive source)."""
        context_keywords = [
            "goal", "score", "match", "round", "game", "play", "player",
            "killstreak", "level up", "respawn", "tournament", "championship",
            "team", "win", "lose", "point", "foul", "penalty"
        ]
        
        # Check transcript
        transcript_text = state.get("transcript", {}).get("text", "").lower()
        has_keywords = any(kw in transcript_text for kw in context_keywords)
        
        # Check OCR
        ocr_texts = [r.get("text", "").lower() for r in state.get("ocr_results", [])]
        has_ocr_keywords = any(any(kw in ocr_text for kw in context_keywords) for ocr_text in ocr_texts)
        
        # No weapons detected by YOLO
        vision_detections = state.get("vision_detections", [])
        no_weapons = not any(d.get("category") == "weapon" for d in vision_detections)
        
        return (has_keywords or has_ocr_keywords) and no_weapons
    
    def _assess_violence(self, scores: Dict[str, float], state: PipelineState, is_sports_gaming: bool) -> str:
        """
        Assess violence with multi-signal confirmation from enhanced safety stack.
        
        Considers: X-CLIP, VideoMAE, Pose Heuristics, YOLO weapons, transcript analysis.
        """
        violence_score = scores["violence"]
        unsafe_threshold = self.thresholds.get("unsafe", {}).get("violence", 0.75)
        caution_threshold = self.thresholds.get("caution", {}).get("violence", 0.40)
        
        # === Traditional signals ===
        vision_detections = state.get("vision_detections", [])
        weapon_classes = {"knife", "gun", "weapon", "pistol", "rifle", "sword", "machete"}
        has_weapon = any(d.get("category") == "weapon" or d.get("label", "").lower() in weapon_classes 
                        for d in vision_detections)
        
        transcript_text = state.get("transcript", {}).get("text", "").lower()
        violence_keywords = ["assault", "attack", "fight", "hit", "punch", "kick", "stab", "shoot", "kill"]
        has_violence_transcript = any(kw in transcript_text for kw in violence_keywords)
        
        ocr_texts = [r.get("text", "").lower() for r in state.get("ocr_results", [])]
        threat_keywords = ["threat", "kill", "die", "dead", "murder", "blood"]
        has_threat_ocr = any(any(kw in ocr_text for kw in threat_keywords) for ocr_text in ocr_texts)
        
        # === New safety stack signals ===
        videomae_scores = state.get("videomae_scores", [])
        has_videomae_high = any(s.get("score", 0) > 0.6 for s in videomae_scores)
        videomae_max = max([s.get("score", 0) for s in videomae_scores], default=0)
        
        pose_signals = state.get("pose_signals", [])
        has_pose_violence = any(s.get("confidence", 0) > 0.5 for s in pose_signals)
        
        violence_segments = state.get("violence_segments", [])
        has_xclip_high = any(s.get("violence_score", 0) > 0.6 for s in violence_segments)
        
        # === Count confirming signals with enhanced stack ===
        # Traditional signals
        traditional_signals = sum([has_weapon, has_violence_transcript, has_threat_ocr])
        
        # New stack signals (specialist models)
        specialist_signals = sum([has_videomae_high, has_pose_violence, has_xclip_high])
        
        total_confirming = traditional_signals + specialist_signals
        
        # === Decision logic with enhanced confidence ===
        if violence_score >= unsafe_threshold:
            # High violence score
            if specialist_signals >= 2:
                # Multiple specialist models agree = high confidence UNSAFE
                return "UNSAFE"
            elif specialist_signals >= 1 and traditional_signals >= 1:
                # Specialist + traditional signal = UNSAFE
                return "UNSAFE" if not is_sports_gaming else "NEEDS_REVIEW"
            elif is_sports_gaming:
                return "NEEDS_REVIEW"  # High violence in sports/gaming context
            elif videomae_max > 0.75:
                # VideoMAE very confident = likely real violence
                return "UNSAFE"
            else:
                return "NEEDS_REVIEW"
        
        elif violence_score >= caution_threshold:
            # Moderate violence score
            if is_sports_gaming and violence_score < 0.60 and specialist_signals == 0:
                return "SAFE"  # Likely false positive from sports/gaming
            elif specialist_signals >= 2:
                # Multiple models flagging at moderate score = CAUTION
                return "CAUTION"
            elif total_confirming >= 2:
                return "CAUTION"
            elif violence_score > 0.55:
                return "NEEDS_REVIEW"
            else:
                return "CAUTION" if total_confirming >= 1 else "SAFE"
        
        return "SAFE"
    
    def _assess_hate(self, scores: Dict[str, float], state: PipelineState) -> str:
        """Assess hate speech with multi-signal confirmation."""
        hate_score = scores["hate"]
        unsafe_threshold = self.thresholds.get("unsafe", {}).get("hate", 0.60)
        caution_threshold = self.thresholds.get("caution", {}).get("hate", 0.30)
        
        if hate_score < caution_threshold:
            return "SAFE"
        
        # Check if we have both OCR and transcript signals
        transcript_moderation = state.get("transcript_moderation", [])
        ocr_moderation = state.get("ocr_moderation", [])
        
        has_transcript_hate = any(t.get("hate_score", 0) > 0.3 for t in transcript_moderation)
        has_ocr_hate = any(o.get("hate_score", 0) > 0.3 for o in ocr_moderation)
        
        # UNSAFE requires both OR very high score in one
        if hate_score >= unsafe_threshold:
            if has_transcript_hate or has_ocr_hate:
                return "UNSAFE"
            else:
                return "NEEDS_REVIEW"  # High score but unclear source
        
        # CAUTION level
        if has_transcript_hate or has_ocr_hate:
            return "CAUTION"
        else:
            return "NEEDS_REVIEW"  # Moderate score, unclear signals
    
    def _assess_sexual(self, scores: Dict[str, float], state: PipelineState) -> str:
        """Assess sexual content with multi-signal confirmation."""
        sexual_score = scores["sexual"]
        unsafe_threshold = self.thresholds.get("unsafe", {}).get("sexual", 0.60)
        caution_threshold = self.thresholds.get("caution", {}).get("sexual", 0.30)
        
        if sexual_score < caution_threshold:
            return "SAFE"
        
        # Check multiple signals
        transcript_moderation = state.get("transcript_moderation", [])
        ocr_moderation = state.get("ocr_moderation", [])
        
        has_transcript_sexual = any(t.get("sexual_score", 0) > 0.3 for t in transcript_moderation)
        has_ocr_sexual = any(o.get("sexual_score", 0) > 0.3 for o in ocr_moderation)
        
        confirming_signals = sum([has_transcript_sexual, has_ocr_sexual])
        
        if sexual_score >= unsafe_threshold:
            if confirming_signals >= 1:
                return "UNSAFE"
            else:
                return "NEEDS_REVIEW"
        
        if confirming_signals >= 1:
            return "CAUTION"
        else:
            return "NEEDS_REVIEW" if sexual_score > 0.4 else "SAFE"
    
    def _assess_drugs(self, scores: Dict[str, float], state: PipelineState) -> str:
        """Assess drugs/substance content."""
        drugs_score = scores["drugs"]
        unsafe_threshold = self.thresholds.get("unsafe", {}).get("drugs", 0.70)
        caution_threshold = self.thresholds.get("caution", {}).get("drugs", 0.40)
        
        if drugs_score >= unsafe_threshold:
            return "UNSAFE"
        elif drugs_score >= caution_threshold:
            return "CAUTION"
        return "SAFE"
    
    def extract_violations(
        self,
        scores: Dict[str, float],
        state: PipelineState
    ) -> List[Dict[str, Any]]:
        """Extract violations from evidence."""
        violations = []
        
        unsafe_thresholds = self.thresholds.get("unsafe", {})
        caution_thresholds = self.thresholds.get("caution", {})
        
        for criterion, score in scores.items():
            if score >= unsafe_thresholds.get(criterion, 1.0):
                severity = "high"
            elif score >= caution_thresholds.get(criterion, 1.0):
                severity = "medium"
            else:
                continue
            
            # Find timestamp ranges and evidence
            timestamp_ranges, evidence_refs = self._find_evidence_for_criterion(
                criterion,
                state
            )
            
            violations.append({
                "criterion": criterion,
                "severity": severity,
                "score": score,
                "timestamp_ranges": timestamp_ranges,
                "evidence_refs": evidence_refs
            })
        
        return violations
    
    def _find_evidence_for_criterion(
        self,
        criterion: str,
        state: PipelineState
    ) -> Tuple[List[List[float]], List[str]]:
        """Find evidence for a criterion."""
        timestamp_ranges = []
        evidence_refs = []
        
        if criterion == "violence":
            violence_segments = state.get("violence_segments", [])
            for seg in violence_segments:
                if seg["violence_score"] > 0.4:
                    timestamp_ranges.append([seg["start_time"], seg["end_time"]])
                    evidence_refs.append(seg["id"])
            
            # Add weapon detections
            vision_detections = state.get("vision_detections", [])
            for det in vision_detections:
                if det.get("category") == "weapon":
                    evidence_refs.append(det["id"])
        
        elif criterion == "profanity":
            transcript_moderation = state.get("transcript_moderation", [])
            for mod in transcript_moderation:
                if mod.get("profanity_score", 0) > 0.4:
                    timestamp_ranges.append([mod.get("start_time", 0), mod.get("end_time", 0)])
                    evidence_refs.append(mod["id"])
        
        elif criterion == "sexual":
            transcript_moderation = state.get("transcript_moderation", [])
            for mod in transcript_moderation:
                if mod.get("sexual_score", 0) > 0.3:
                    timestamp_ranges.append([mod.get("start_time", 0), mod.get("end_time", 0)])
                    evidence_refs.append(mod["id"])
        
        elif criterion == "drugs":
            transcript_moderation = state.get("transcript_moderation", [])
            for mod in transcript_moderation:
                if mod.get("drugs_score", 0) > 0.4:
                    timestamp_ranges.append([mod.get("start_time", 0), mod.get("end_time", 0)])
                    evidence_refs.append(mod["id"])
            
            vision_detections = state.get("vision_detections", [])
            for det in vision_detections:
                if det.get("category") == "substance":
                    evidence_refs.append(det["id"])
        
        elif criterion == "hate":
            transcript_moderation = state.get("transcript_moderation", [])
            for mod in transcript_moderation:
                if mod.get("hate_score", 0) > 0.3:
                    timestamp_ranges.append([mod.get("start_time", 0), mod.get("end_time", 0)])
                    evidence_refs.append(mod["id"])
        
        return timestamp_ranges, evidence_refs


def fuse_evidence_policy(state: PipelineState) -> PipelineState:
    """
    Fuse evidence using research-backed multi-modal fusion.
    
    This replaces the legacy heuristic-based fusion with a principled
    approach based on:
    - Reliability-weighted pooling
    - Coverage normalization  
    - Agreement-based confidence
    - Calibrated thresholds
    """
    logger.info("=== Policy Fusion Node (Research-Backed) ===")
    
    send_progress(state.get("progress_callback"), "policy_fusion", "Computing safety scores", 85)
    
    policy_config = state.get("policy_config", {})
    
    # Use research-backed fusion
    use_research_fusion = policy_config.get("use_research_fusion", True)
    
    if use_research_fusion:
        # === Research-Backed Fusion ===
        logger.info("Using research-backed multi-modal fusion")
        
        fusion_result = compute_all_scores_research_backed(state, policy_config)
        
        scores = fusion_result["scores"]
        confidences = fusion_result["confidences"]
        criterion_verdicts = fusion_result["criterion_verdicts"]
        verdict = fusion_result["verdict"]
        overall_confidence = fusion_result["confidence"]
        fusion_debug = fusion_result["fusion_debug"]
        
        # Store in state
        state["criterion_scores"] = scores
        state["criterion_confidences"] = confidences
        state["criterion_verdicts"] = criterion_verdicts
        state["verdict"] = verdict
        state["verdict_confidence"] = overall_confidence
        
        logger.info(f"Criterion scores: {scores}")
        logger.info(f"Criterion confidences: {confidences}")
        logger.info(f"Verdict: {verdict} (confidence: {overall_confidence:.2f})")
        
        # Extract violations using both score and confidence
        violations = _extract_violations_research(scores, confidences, criterion_verdicts, state, policy_config)
        state["violations"] = violations
        
    else:
        # === Legacy Fusion (fallback) ===
        logger.info("Using legacy fusion (fallback)")
        engine = PolicyEngine(policy_config)
        scores = engine.compute_scores(state)
        state["criterion_scores"] = scores
        
        verdict = engine.determine_verdict(scores, state)
        state["verdict"] = verdict
        
        violations = engine.extract_violations(scores, state)
        state["violations"] = violations
        
        fusion_debug = {"method": "legacy"}
    
    logger.info(f"Found {len(violations)} violations")
    
    # If NEEDS_REVIEW, add explanation
    if verdict == "NEEDS_REVIEW":
        logger.info("Verdict requires manual review: conflicting signals or borderline case")
    
    # Build evidence structure with enhanced safety stack
    evidence = {
        "vision": state.get("vision_detections", []),
        "violence_segments": state.get("violence_segments", []),
        "asr": state.get("transcript", {}).get("chunks", []),
        "ocr": state.get("ocr_results", []),
        "transcript_moderation": state.get("transcript_moderation", []),
        "ocr_moderation": state.get("ocr_moderation", []),
        # New safety stack
        "candidate_windows": state.get("candidate_windows", []),
        "videomae_scores": state.get("videomae_scores", []),
        "pose_signals": state.get("pose_signals", []),
        "nsfw_results": state.get("nsfw_results", {})
    }
    
    state["evidence"] = evidence
    
    # Build comprehensive fusion debug info
    videomae_scores = state.get("videomae_scores", [])
    pose_signals = state.get("pose_signals", [])
    violence_segments = state.get("violence_segments", [])
    nsfw_results = state.get("nsfw_results", {})
    
    if use_research_fusion:
        fusion_debug["signals_summary"] = {
            "xclip_active": len(violence_segments) > 0,
            "xclip_max": max([s.get("violence_score", 0) for s in violence_segments], default=0),
            "videomae_active": len(videomae_scores) > 0,
            "videomae_max": max([s.get("violence_score", s.get("score", 0)) for s in videomae_scores], default=0),
            "pose_active": len(pose_signals) > 0,
            "pose_high_conf": len([s for s in pose_signals if s.get("confidence", 0) > 0.5]),
            "nsfw_active": nsfw_results.get("analyzed_frames", 0) > 0,
            "nsfw_max": nsfw_results.get("max_nsfw_score", 0),
            "weapons_detected": len([d for d in state.get("vision_detections", []) 
                                    if d.get("category") == "weapon"]),
        }
        fusion_debug["verdict_rationale"] = _get_research_verdict_rationale(
            verdict, scores, confidences, criterion_verdicts, fusion_debug
        )
    else:
        fusion_debug["signals_used"] = {
            "xclip_active": len(violence_segments) > 0,
            "videomae_active": len(videomae_scores) > 0,
            "pose_active": len(pose_signals) > 0,
        }
        fusion_debug["verdict_rationale"] = _get_verdict_rationale(verdict, scores, state)
    
    state["fusion_debug"] = fusion_debug
    
    # Save stage output for real-time retrieval
    save_stage_output(state.get("video_id"), "policy_fusion", format_stage_output(
        "policy_fusion",
        verdict=verdict,
        confidence=state.get("verdict_confidence", 0.5),
        scores={k: round(v, 3) for k, v in scores.items()},
        confidences={k: round(v, 3) for k, v in (state.get("criterion_confidences", {}) or {}).items()},
        violations_count=len(violations),
        violations=[
            {
                "criterion": v.get("criterion"),
                "score": round(v.get("score", 0), 3),
                "confidence": round(v.get("confidence", 0.5), 3),
                "severity": v.get("severity")
            }
            for v in violations[:10]
        ],
        evidence_counts={
            "vision": len(state.get("vision_detections", [])),
            "violence_segments": len(state.get("violence_segments", [])),
            "transcript_chunks": len(state.get("transcript", {}).get("chunks", [])),
            "ocr_results": len(state.get("ocr_results", [])),
            "videomae_scores": len(videomae_scores),
            "pose_signals": len(pose_signals),
            "candidate_windows": len(state.get("candidate_windows", [])),
            "nsfw_frames": nsfw_results.get("nsfw_frames", 0)
        },
        fusion_method="research_backed" if use_research_fusion else "legacy",
        fusion_debug=fusion_debug
    ))
    
    return state


def _extract_violations_research(
    scores: Dict[str, float],
    confidences: Dict[str, float],
    criterion_verdicts: Dict[str, str],
    state: PipelineState,
    config: Dict
) -> List[Dict[str, Any]]:
    """Extract violations using research-backed scoring with confidence."""
    violations = []
    
    thresholds = config.get("thresholds", {})
    unsafe_thresh = thresholds.get("unsafe", {})
    caution_thresh = thresholds.get("caution", {})
    
    for criterion, score in scores.items():
        confidence = confidences.get(criterion, 0.5)
        criterion_verdict = criterion_verdicts.get(criterion, "SAFE")
        
        # Determine severity based on verdict and confidence
        if criterion_verdict == "UNSAFE":
            severity = "high"
        elif criterion_verdict == "NEEDS_REVIEW":
            severity = "high" if confidence < 0.5 else "medium"
        elif criterion_verdict == "CAUTION":
            severity = "medium"
        else:
            continue  # SAFE - no violation
        
        # Find evidence timestamps
        timestamp_ranges, evidence_refs = _find_evidence_for_criterion(criterion, state)
        
        violations.append({
            "criterion": criterion,
            "severity": severity,
            "score": score,
            "confidence": confidence,
            "verdict": criterion_verdict,
            "timestamp_ranges": timestamp_ranges,
            "evidence_refs": evidence_refs
        })
    
    return violations


def _find_evidence_for_criterion(criterion: str, state: PipelineState) -> Tuple[List[List[float]], List[str]]:
    """Find evidence timestamps and references for a criterion."""
    timestamp_ranges = []
    evidence_refs = []
    
    if criterion == "violence":
        # X-CLIP segments
        for seg in state.get("violence_segments", []):
            if seg.get("violence_score", 0) > 0.4:
                timestamp_ranges.append([seg.get("start_time", 0), seg.get("end_time", 0)])
                evidence_refs.append(seg.get("id", "xclip"))
        
        # VideoMAE scores
        for score in state.get("videomae_scores", []):
            if score.get("violence_score", score.get("score", 0)) > 0.5:
                timestamp_ranges.append([score.get("start_time", 0), score.get("end_time", 0)])
                evidence_refs.append(f"videomae_{score.get('window_idx', 0)}")
        
        # Pose signals
        for sig in state.get("pose_signals", []):
            if sig.get("confidence", 0) > 0.5:
                ts = sig.get("timestamp", 0)
                timestamp_ranges.append([ts, ts + 1])
                evidence_refs.append("pose")
        
        # Weapons
        for det in state.get("vision_detections", []):
            if det.get("category") == "weapon":
                evidence_refs.append(det.get("id", "weapon"))
    
    elif criterion == "sexual":
        # NSFW detections
        nsfw = state.get("nsfw_results", {})
        for det in nsfw.get("detections", []):
            if det.get("nsfw_score", 0) > 0.4:
                ts = det.get("timestamp", 0)
                timestamp_ranges.append([ts, ts])
                evidence_refs.append("nsfw_visual")
        
        # Text-based
        for mod in state.get("transcript_moderation", []):
            if mod.get("sexual_score", 0) > 0.3:
                timestamp_ranges.append([mod.get("start_time", 0), mod.get("end_time", 0)])
                evidence_refs.append(mod.get("id", "transcript"))
    
    elif criterion == "profanity":
        for mod in state.get("transcript_moderation", []):
            if mod.get("profanity_score", 0) > 0.3:
                timestamp_ranges.append([mod.get("start_time", 0), mod.get("end_time", 0)])
                evidence_refs.append(mod.get("id", "transcript"))
    
    elif criterion == "drugs":
        for mod in state.get("transcript_moderation", []):
            if mod.get("drugs_score", 0) > 0.3:
                timestamp_ranges.append([mod.get("start_time", 0), mod.get("end_time", 0)])
                evidence_refs.append(mod.get("id", "transcript"))
        
        for det in state.get("vision_detections", []):
            if det.get("category") == "substance":
                evidence_refs.append(det.get("id", "yolo"))
    
    elif criterion == "hate":
        for mod in state.get("transcript_moderation", []):
            if mod.get("hate_score", 0) > 0.3:
                timestamp_ranges.append([mod.get("start_time", 0), mod.get("end_time", 0)])
                evidence_refs.append(mod.get("id", "transcript"))
    
    return timestamp_ranges, evidence_refs


def _get_research_verdict_rationale(
    verdict: str,
    scores: Dict[str, float],
    confidences: Dict[str, float],
    criterion_verdicts: Dict[str, str],
    fusion_debug: Dict
) -> str:
    """Generate detailed rationale for research-backed verdict."""
    reasons = []
    
    for criterion, crit_verdict in criterion_verdicts.items():
        if crit_verdict in ["UNSAFE", "NEEDS_REVIEW", "CAUTION"]:
            score = scores.get(criterion, 0)
            conf = confidences.get(criterion, 0)
            contributing = fusion_debug.get("contributing_signals", {}).get(criterion, [])
            agreement = fusion_debug.get("agreement_levels", {}).get(criterion, "unknown")
            
            if contributing:
                contrib_str = ", ".join(contributing)
                reasons.append(
                    f"{criterion.capitalize()}: {crit_verdict} (score={score:.2f}, "
                    f"conf={conf:.2f}, signals=[{contrib_str}], agreement={agreement})"
                )
    
    if not reasons:
        if verdict == "SAFE":
            return "No significant safety concerns. All models agree content is safe."
        return "Borderline signals detected across criteria."
    
    return " | ".join(reasons)


def _get_verdict_rationale(verdict: str, scores: Dict[str, float], state: PipelineState) -> str:
    """Generate human-readable rationale for verdict."""
    videomae_scores = state.get("videomae_scores", [])
    pose_signals = state.get("pose_signals", [])
    violence_segments = state.get("violence_segments", [])
    
    reasons = []
    
    violence_score = scores.get("violence", 0)
    if violence_score > 0.5:
        sources = []
        if any(s.get("violence_score", 0) > 0.5 for s in violence_segments):
            sources.append("X-CLIP")
        if any(s.get("score", 0) > 0.5 for s in videomae_scores):
            sources.append("VideoMAE")
        if any(s.get("confidence", 0) > 0.5 for s in pose_signals):
            sources.append("Pose Analysis")
        
        if sources:
            reasons.append(f"Violence detected by: {', '.join(sources)} (score: {violence_score:.2f})")
    
    if scores.get("profanity", 0) > 0.3:
        reasons.append(f"Profanity score: {scores['profanity']:.2f}")
    
    if scores.get("drugs", 0) > 0.3:
        reasons.append(f"Substance score: {scores['drugs']:.2f}")
    
    if not reasons:
        if verdict == "SAFE":
            return "No significant safety concerns detected across all models."
        return "Borderline signals detected, manual review recommended."
    
    return " | ".join(reasons)
