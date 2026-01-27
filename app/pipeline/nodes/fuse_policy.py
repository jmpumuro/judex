"""
Policy fusion node - deterministic scoring and verdict.
"""
from typing import Dict, Any, List, Tuple
from app.pipeline.state import PipelineState
from app.core.logging import get_logger
from app.models.yolo26 import YOLO26Detector
from app.utils.progress import send_progress, save_stage_output, format_stage_output

logger = get_logger("node.policy")


class PolicyEngine:
    """Deterministic policy engine for scoring and verdicts."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.thresholds = config.get("thresholds", {})
        self.weights = config.get("weights", {})
    
    def compute_scores(self, state: PipelineState) -> Dict[str, float]:
        """Compute criterion scores from evidence."""
        
        # Extract evidence
        vision_detections = state.get("vision_detections", [])
        violence_segments = state.get("violence_segments", [])
        transcript_moderation = state.get("transcript_moderation", [])
        ocr_moderation = state.get("ocr_moderation", [])
        
        # Violence score
        violence_score = self._compute_violence_score(
            violence_segments,
            vision_detections,
            transcript_moderation
        )
        
        # Profanity score
        profanity_score = self._compute_profanity_score(
            transcript_moderation,
            ocr_moderation
        )
        
        # Sexual score
        sexual_score = self._compute_sexual_score(
            transcript_moderation,
            ocr_moderation,
            vision_detections
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
        transcript_moderation: List[Dict]
    ) -> float:
        """Compute violence score."""
        weights = self.weights.get("violence", {})
        
        # Violence model score
        violence_model_score = 0.0
        if violence_segments:
            violence_model_score = max([s["violence_score"] for s in violence_segments])
        
        # YOLO weapons score
        yolo_weapons_score = 0.0
        if vision_detections:
            weapon_detections = [d for d in vision_detections if d.get("category") == "weapon"]
            if weapon_detections:
                # Normalize by video duration or frame count
                yolo_weapons_score = min(len(weapon_detections) * 0.3, 1.0)
        
        # Transcript violence score
        transcript_score = 0.0
        if transcript_moderation:
            scores = [t.get("violence_score", 0.0) for t in transcript_moderation]
            transcript_score = max(scores) if scores else 0.0
        
        # Weighted combination
        final_score = (
            violence_model_score * weights.get("violence_model", 0.6) +
            yolo_weapons_score * weights.get("yolo_weapons", 0.3) +
            transcript_score * weights.get("transcript", 0.1)
        )
        
        return min(final_score, 1.0)
    
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
        vision_detections: List[Dict]
    ) -> float:
        """Compute sexual content score with frequency consideration."""
        import math
        weights = self.weights.get("sexual", {})
        
        # Transcript - count instances
        transcript_score = 0.0
        if transcript_moderation:
            total_sexual_words = sum(len(t.get("sexual_words", [])) for t in transcript_moderation)
            max_score = max([t.get("sexual_score", 0.0) for t in transcript_moderation])
            
            if total_sexual_words > 0:
                frequency_factor = min(total_sexual_words / 4.0, 1.0)
                transcript_score = (frequency_factor * 0.6 + max_score * 0.4)
                
                # Dampen for single instances
                if total_sexual_words <= 2:
                    transcript_score = math.sqrt(transcript_score) * 0.6
        
        # OCR
        ocr_score = 0.0
        if ocr_moderation:
            scores = [o.get("sexual_score", 0.0) for o in ocr_moderation]
            ocr_score = max(scores) if scores else 0.0
        
        # Vision (placeholder - YOLO26 doesn't have explicit labels for this)
        vision_score = 0.0
        
        final_score = (
            transcript_score * weights.get("transcript", 0.7) +
            ocr_score * weights.get("ocr", 0.2) +
            vision_score * weights.get("vision", 0.1)
        )
        
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
        """Assess violence with multi-signal confirmation."""
        violence_score = scores["violence"]
        unsafe_threshold = self.thresholds.get("unsafe", {}).get("violence", 0.75)
        caution_threshold = self.thresholds.get("caution", {}).get("violence", 0.40)
        
        # Get confirming signals
        vision_detections = state.get("vision_detections", [])
        has_weapon = any(d.get("category") == "weapon" for d in vision_detections)
        
        transcript_text = state.get("transcript", {}).get("text", "").lower()
        violence_keywords = ["assault", "attack", "fight", "hit", "punch", "kick", "stab", "shoot", "kill"]
        has_violence_transcript = any(kw in transcript_text for kw in violence_keywords)
        
        ocr_texts = [r.get("text", "").lower() for r in state.get("ocr_results", [])]
        threat_keywords = ["threat", "kill", "die", "dead", "murder", "blood"]
        has_threat_ocr = any(any(kw in ocr_text for kw in threat_keywords) for ocr_text in ocr_texts)
        
        # Count confirming signals
        confirming_signals = sum([has_weapon, has_violence_transcript, has_threat_ocr])
        
        # Decision logic
        if violence_score >= unsafe_threshold:
            if confirming_signals >= 1 and not is_sports_gaming:
                return "UNSAFE"
            elif is_sports_gaming:
                return "NEEDS_REVIEW"  # High violence in sports/gaming context
            else:
                return "NEEDS_REVIEW"  # High violence but no confirming signals
        
        elif violence_score >= caution_threshold:
            if is_sports_gaming and violence_score < 0.65:
                return "SAFE"  # Likely false positive from sports/gaming
            elif confirming_signals >= 1:
                return "CAUTION"
            else:
                return "NEEDS_REVIEW" if violence_score > 0.55 else "CAUTION"
        
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
    """Fuse evidence and apply policy to determine verdict."""
    logger.info("=== Policy Fusion Node ===")
    
    send_progress(state.get("progress_callback"), "policy_fusion", "Computing safety scores", 85)
    
    policy_config = state.get("policy_config", {})
    
    # Initialize policy engine
    engine = PolicyEngine(policy_config)
    
    # Compute criterion scores
    scores = engine.compute_scores(state)
    state["criterion_scores"] = scores
    
    logger.info(f"Criterion scores: {scores}")
    
    # Determine verdict with multi-signal confirmation
    verdict = engine.determine_verdict(scores, state)
    state["verdict"] = verdict
    
    logger.info(f"Verdict: {verdict}")
    
    # If NEEDS_REVIEW, add explanation
    if verdict == "NEEDS_REVIEW":
        logger.info("Verdict requires manual review: conflicting signals or borderline case")
    
    # Extract violations
    violations = engine.extract_violations(scores, state)
    state["violations"] = violations
    
    logger.info(f"Found {len(violations)} violations")
    
    # Build evidence structure
    evidence = {
        "vision": state.get("vision_detections", []),
        "violence_segments": state.get("violence_segments", []),
        "asr": state.get("transcript", {}).get("chunks", []),
        "ocr": state.get("ocr_results", []),
        "transcript_moderation": state.get("transcript_moderation", []),
        "ocr_moderation": state.get("ocr_moderation", [])
    }
    
    state["evidence"] = evidence
    
    # Save stage output for real-time retrieval
    save_stage_output(state.get("video_id"), "policy_fusion", format_stage_output(
        "policy_fusion",
        verdict=verdict,
        scores={k: round(v, 3) for k, v in scores.items()},
        violations_count=len(violations),
        violations=[
            {
                "criterion": v.get("criterion"),
                "score": round(v.get("score", 0), 3),
                "threshold": v.get("threshold"),
                "severity": v.get("severity")
            }
            for v in violations[:10]  # First 10 violations
        ],
        evidence_counts={
            "vision": len(state.get("vision_detections", [])),
            "violence_segments": len(state.get("violence_segments", [])),
            "transcript_chunks": len(state.get("transcript", {}).get("chunks", [])),
            "ocr_results": len(state.get("ocr_results", []))
        }
    ))
    
    return state
