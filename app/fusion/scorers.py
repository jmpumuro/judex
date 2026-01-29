"""
Criterion Scorers - Strategy pattern for computing criterion scores.

Each scorer encapsulates the logic for computing a score for a specific
criterion type. New criterion types can be added by creating a new scorer
and registering it - no if/else modifications needed.

Design Patterns:
- Strategy: Each scorer is a strategy for computing scores
- Factory: ScorerFactory creates appropriate scorer
- Registry: ScorerRegistry maps keywords to scorers

All configurable values are externalized to fusion/config.py.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Set
from dataclasses import dataclass, field
from app.evaluation.criteria import Criterion, SEVERITY_WEIGHTS
from app.fusion.config import get_fusion_config, FusionConfig
from app.core.logging import get_logger

logger = get_logger("fusion.scorers")


# ===== SIGNAL CONTAINER =====

@dataclass
class DetectorSignals:
    """
    Aggregated signals from all detectors.
    
    This is the input to all scorers - a normalized view of detector outputs.
    """
    # Vision detections
    vision_classes: List[str] = field(default_factory=list)
    vision_confidences: List[float] = field(default_factory=list)
    
    yoloworld_classes: List[str] = field(default_factory=list)
    yoloworld_confidences: List[float] = field(default_factory=list)
    
    # Violence
    violence_max_score: float = 0.0
    violence_segment_count: int = 0
    
    # Audio/Text
    transcript_text: str = ""
    transcript_chunks: List[Dict[str, Any]] = field(default_factory=list)
    
    # OCR
    ocr_texts: List[str] = field(default_factory=list)
    ocr_count: int = 0
    
    # Moderation scores (max across all chunks)
    profanity_score: float = 0.0
    violence_text_score: float = 0.0
    sexual_score: float = 0.0
    drugs_score: float = 0.0
    hate_score: float = 0.0
    
    # External stage results
    external_verdicts: List[str] = field(default_factory=list)  # PASS, REVIEW, FAIL
    external_risk_scores: List[float] = field(default_factory=list)
    external_violations: List[Dict[str, Any]] = field(default_factory=list)
    external_confidence: float = 0.0
    
    # Skipped stages tracking
    skipped_stages: List[str] = field(default_factory=list)
    skipped_supporting_count: int = 0  # Number of skipped SUPPORTING stages
    
    @classmethod
    def from_state(cls, state: Dict[str, Any]) -> "DetectorSignals":
        """Build signals from pipeline state."""
        config = get_fusion_config()
        
        # Vision
        vision_detections = state.get("vision_detections", [])
        yoloworld_detections = state.get("yoloworld_detections", [])
        
        # Violence
        violence_segments = state.get("violence_segments", [])
        violence_max = max((s.get("violence_score", 0) for s in violence_segments), default=0)
        violence_count = len([
            s for s in violence_segments 
            if s.get("violence_score", 0) > config.thresholds.violence_segment_threshold
        ])
        
        # Audio
        transcript = state.get("transcript", {})
        
        # OCR
        ocr_results = state.get("ocr_results", [])
        
        # Moderation - aggregate max scores from lists
        transcript_mod = state.get("transcript_moderation", [])
        ocr_mod = state.get("ocr_moderation", [])
        
        def max_score(items: List[Dict], key: str) -> float:
            return max((m.get(key, 0) for m in items), default=0)
        
        all_mod = transcript_mod + ocr_mod
        
        # Extract external stage results
        external_verdicts = []
        external_risk_scores = []
        external_violations = []
        external_confidence = 0.0
        
        # Look for external stage outputs in state (keys starting with 'external_stage_')
        for key, value in state.items():
            if key.startswith("external_stage_") and isinstance(value, dict):
                if value.get("status") == "completed":
                    # Also check the mapped output fields
                    pass
            # Check for mapped external stage outputs (verdict, risk_score, violations, confidence)
            if key == "verdict" and isinstance(value, str) and value in ("PASS", "REVIEW", "FAIL"):
                external_verdicts.append(value)
            if key == "risk_score" and isinstance(value, (int, float)):
                external_risk_scores.append(float(value))
            if key == "violations" and isinstance(value, list):
                external_violations.extend(value)
            if key == "confidence" and isinstance(value, (int, float)):
                external_confidence = max(external_confidence, float(value))
        
        # Extract skipped stages from stage_runs
        skipped_stages = []
        skipped_supporting_count = 0
        stage_runs = state.get("stage_runs", [])
        for run in stage_runs:
            if run.get("status") == "skipped":
                skipped_stages.append(run.get("stage_id", ""))
                if run.get("impact") == "supporting":
                    skipped_supporting_count += 1
        
        return cls(
            vision_classes=[d.get("label", "").lower() for d in vision_detections],
            vision_confidences=[d.get("confidence", 0) for d in vision_detections],
            yoloworld_classes=[d.get("label", "").lower() for d in yoloworld_detections],
            yoloworld_confidences=[d.get("confidence", 0) for d in yoloworld_detections],
            violence_max_score=violence_max,
            violence_segment_count=violence_count,
            transcript_text=transcript.get("text", ""),
            transcript_chunks=transcript.get("chunks", []),
            ocr_texts=[o.get("text", "") for o in ocr_results],
            ocr_count=len(ocr_results),
            profanity_score=max_score(all_mod, "profanity_score"),
            violence_text_score=max_score(all_mod, "violence_score"),
            sexual_score=max_score(all_mod, "sexual_score"),
            drugs_score=max_score(all_mod, "drugs_score"),
            hate_score=max_score(all_mod, "hate_score"),
            external_verdicts=external_verdicts,
            external_risk_scores=external_risk_scores,
            external_violations=external_violations,
            external_confidence=external_confidence,
            skipped_stages=skipped_stages,
            skipped_supporting_count=skipped_supporting_count,
        )
    
    def has_class(self, target_classes: Set[str]) -> bool:
        """Check if any target class is detected in vision outputs."""
        all_classes = self.vision_classes + self.yoloworld_classes
        return any(
            any(target in detected for target in target_classes)
            for detected in all_classes
        )


# ===== ABSTRACT SCORER =====

class CriterionScorer(ABC):
    """
    Abstract base class for criterion scorers.
    
    Each scorer implements the logic for computing a score
    for a specific type of criterion.
    """
    
    # Keywords that trigger this scorer
    keywords: Set[str] = set()
    
    def __init__(self):
        self.config = get_fusion_config()
    
    @abstractmethod
    def compute_score(
        self,
        criterion: Criterion,
        signals: DetectorSignals
    ) -> float:
        """
        Compute score for the criterion.
        
        Args:
            criterion: The criterion being evaluated
            signals: Aggregated detector signals
            
        Returns:
            Score between 0.0 and 1.0
        """
        pass
    
    def applies_to(self, criterion_id: str, criterion: Criterion) -> bool:
        """
        Check if this scorer applies to the given criterion.
        
        Default implementation checks keywords in ID, label, description.
        Override for custom matching logic.
        """
        text_to_check = f"{criterion_id} {criterion.label} {criterion.description or ''}".lower()
        return any(kw in text_to_check for kw in self.keywords)
    
    def _apply_severity_weight(self, score: float, criterion: Criterion) -> float:
        """Apply severity weight to normalize score."""
        weight = SEVERITY_WEIGHTS.get(criterion.severity, 1.0)
        return min(score * weight, 1.0)
    
    def _clamp(self, value: float) -> float:
        """Clamp value to [0, 1] range."""
        return max(0.0, min(1.0, value))


# ===== CONCRETE SCORERS =====

class ViolenceScorer(CriterionScorer):
    """Scorer for violence-related criteria."""
    
    keywords = {"violence", "violent", "physical", "assault", "attack", "fighting"}
    
    def compute_score(self, criterion: Criterion, signals: DetectorSignals) -> float:
        w = self.config.weights
        classes = self.config.classes
        
        score = 0.0
        
        # Primary: X-CLIP violence detection
        score += signals.violence_max_score * w.violence_video
        
        # Secondary: Weapon detections from YOLO
        if signals.has_class(classes.weapon_classes):
            score += w.violence_visual
        
        # Tertiary: Violence language in transcript
        score += signals.violence_text_score * w.violence_text
        
        return self._apply_severity_weight(self._clamp(score), criterion)


class ProfanityScorer(CriterionScorer):
    """Scorer for profanity/language criteria."""
    
    keywords = {"profanity", "profane", "language", "curse", "vulgar", "explicit"}
    
    def compute_score(self, criterion: Criterion, signals: DetectorSignals) -> float:
        return self._apply_severity_weight(signals.profanity_score, criterion)


class SexualContentScorer(CriterionScorer):
    """Scorer for sexual/adult content criteria."""
    
    keywords = {"sexual", "adult", "nudity", "nude", "explicit", "mature", "nsfw"}
    
    def compute_score(self, criterion: Criterion, signals: DetectorSignals) -> float:
        w = self.config.weights
        t = self.config.thresholds
        
        score = signals.sexual_score * w.sexual_text
        
        # Boost if persons detected with sexual content
        person_count = signals.vision_classes.count("person")
        if person_count > 0 and signals.sexual_score > t.sexual_person_score_threshold:
            score += w.sexual_person_boost
        
        return self._apply_severity_weight(self._clamp(score), criterion)


class DrugScorer(CriterionScorer):
    """Scorer for drug/substance criteria."""
    
    keywords = {"drug", "drugs", "substance", "alcohol", "smoking", "paraphernalia"}
    
    def compute_score(self, criterion: Criterion, signals: DetectorSignals) -> float:
        w = self.config.weights
        classes = self.config.classes
        
        score = 0.0
        
        # YOLO drug-related detections
        if signals.has_class(classes.drug_classes):
            score += w.drug_visual
        
        # Text moderation drug score
        score += signals.drugs_score * w.drug_text
        
        return self._apply_severity_weight(self._clamp(score), criterion)


class HateSpeechScorer(CriterionScorer):
    """Scorer for hate speech/harassment criteria."""
    
    keywords = {"hate", "harassment", "discrimination", "slur", "extremism", "bullying"}
    
    def compute_score(self, criterion: Criterion, signals: DetectorSignals) -> float:
        return self._apply_severity_weight(signals.hate_score, criterion)


class ControversialScorer(CriterionScorer):
    """Scorer for controversial/political content."""
    
    keywords = {"controversial", "political", "religious", "divisive"}
    
    def compute_score(self, criterion: Criterion, signals: DetectorSignals) -> float:
        w = self.config.weights
        
        score = max(
            signals.hate_score * w.controversial_hate,
            signals.violence_text_score * w.controversial_violence
        )
        return self._apply_severity_weight(self._clamp(score), criterion)


class NegativeSentimentScorer(CriterionScorer):
    """Scorer for negative sentiment criteria."""
    
    keywords = {"negative", "sentiment", "sad", "disturbing", "depressing"}
    
    def compute_score(self, criterion: Criterion, signals: DetectorSignals) -> float:
        w = self.config.weights
        
        score = max(
            signals.violence_max_score * w.negative_violence,
            signals.hate_score * w.negative_hate,
            signals.violence_text_score * w.negative_text
        )
        return self._apply_severity_weight(self._clamp(score), criterion)


class SpamScorer(CriterionScorer):
    """Scorer for spam/scam content."""
    
    keywords = {"spam", "scam", "fraud", "phishing"}
    
    def compute_score(self, criterion: Criterion, signals: DetectorSignals) -> float:
        t = self.config.thresholds
        
        score = 0.0
        
        # High OCR text count might indicate spam
        if signals.ocr_count > t.spam_high_ocr_count:
            score = t.spam_high_score
        elif signals.ocr_count > t.spam_medium_ocr_count:
            score = t.spam_medium_score
        
        return self._apply_severity_weight(score, criterion)


class DefaultScorer(CriterionScorer):
    """
    Fallback scorer for unknown criterion types.
    
    Aggregates all available signals with configurable weights.
    """
    
    keywords = set()  # Matches nothing - used as fallback
    
    def compute_score(self, criterion: Criterion, signals: DetectorSignals) -> float:
        w = self.config.weights
        
        # Aggregate all signals
        scores = [
            signals.violence_max_score,
            signals.profanity_score,
            signals.sexual_score,
            signals.drugs_score,
            signals.hate_score
        ]
        
        max_val = max(scores) if scores else 0
        avg_val = sum(scores) / len(scores) if scores else 0
        
        score = max_val * w.default_max_weight + avg_val * w.default_avg_weight
        return self._apply_severity_weight(self._clamp(score), criterion)


# ===== SCORER REGISTRY =====

class ScorerRegistry:
    """
    Registry of criterion scorers.
    
    Implements the Registry pattern for managing scorers.
    New scorers can be registered without modifying existing code.
    """
    
    _scorers: List[CriterionScorer] = []
    _default: CriterionScorer = None
    _initialized: bool = False
    
    @classmethod
    def register(cls, scorer: CriterionScorer) -> None:
        """Register a new scorer."""
        cls._scorers.append(scorer)
        logger.debug(f"Registered scorer: {scorer.__class__.__name__} with keywords: {scorer.keywords}")
    
    @classmethod
    def get_scorer(cls, criterion_id: str, criterion: Criterion) -> CriterionScorer:
        """
        Get the appropriate scorer for a criterion.
        
        Returns the first scorer that applies, or the default scorer.
        """
        cls._ensure_initialized()
        
        for scorer in cls._scorers:
            if scorer.applies_to(criterion_id, criterion):
                return scorer
        
        logger.debug(f"No specific scorer for '{criterion_id}', using default")
        return cls._default
    
    @classmethod
    def _ensure_initialized(cls) -> None:
        """Initialize with built-in scorers if not already done."""
        if cls._initialized:
            return
        
        # Create default scorer
        cls._default = DefaultScorer()
        
        # Register built-in scorers
        cls.register(ViolenceScorer())
        cls.register(ProfanityScorer())
        cls.register(SexualContentScorer())
        cls.register(DrugScorer())
        cls.register(HateSpeechScorer())
        cls.register(ControversialScorer())
        cls.register(NegativeSentimentScorer())
        cls.register(SpamScorer())
        
        cls._initialized = True
        logger.info(f"ScorerRegistry initialized with {len(cls._scorers)} scorers")
    
    @classmethod
    def list_scorers(cls) -> List[str]:
        """List registered scorer names."""
        cls._ensure_initialized()
        return [s.__class__.__name__ for s in cls._scorers]
    
    @classmethod
    def reset(cls) -> None:
        """Reset registry (for testing)."""
        cls._scorers = []
        cls._default = None
        cls._initialized = False


# ===== FACTORY =====

class ScorerFactory:
    """
    Factory for creating and caching scorers.
    
    Provides a clean interface for getting scorers.
    """
    
    @staticmethod
    def get_scorer_for_criterion(
        criterion_id: str,
        criterion: Criterion
    ) -> CriterionScorer:
        """Get the appropriate scorer for a criterion."""
        return ScorerRegistry.get_scorer(criterion_id, criterion)
    
    @staticmethod
    def compute_score(
        criterion_id: str,
        criterion: Criterion,
        signals: DetectorSignals
    ) -> float:
        """
        Convenience method to compute score directly.
        
        Args:
            criterion_id: ID of the criterion
            criterion: Criterion definition
            signals: Detector signals
            
        Returns:
            Computed score (0.0 to 1.0)
        """
        scorer = ScorerFactory.get_scorer_for_criterion(criterion_id, criterion)
        return scorer.compute_score(criterion, signals)


# ===== PUBLIC API =====

def compute_criterion_score(
    criterion_id: str,
    criterion: Criterion,
    signals: DetectorSignals
) -> float:
    """
    Compute score for a criterion using the appropriate scorer.
    
    This is the main entry point for score computation.
    
    Args:
        criterion_id: Criterion identifier
        criterion: Criterion definition
        signals: Aggregated detector signals
        
    Returns:
        Score between 0.0 and 1.0
    """
    return ScorerFactory.compute_score(criterion_id, criterion, signals)
