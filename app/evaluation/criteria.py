"""
User-facing evaluation criteria schema.

This is the schema users interact with - no detector implementation details.
The system automatically routes criteria to appropriate detectors.

Example YAML:
```yaml
name: My Custom Policy
version: "1.0"
criteria:
  violence:
    label: Violence Detection
    description: Physical violence, weapons, fighting
    severity: high
    thresholds:
      safe: 0.3
      caution: 0.6
      unsafe: 0.7
  profanity:
    label: Profane Language
    severity: medium
    thresholds:
      safe: 0.4
      caution: 0.6
      unsafe: 0.75
options:
  generate_report: true
  generate_labeled_video: true
  explain_verdict: true
```
"""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, field_validator
from enum import Enum
import yaml
import json


class Severity(str, Enum):
    """Severity levels for criteria."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


SEVERITY_WEIGHTS = {
    Severity.LOW: 0.5,
    Severity.MEDIUM: 1.0,
    Severity.HIGH: 1.5,
    Severity.CRITICAL: 2.0
}


class Thresholds(BaseModel):
    """Score thresholds for verdict determination."""
    safe: float = Field(default=0.3, ge=0.0, le=1.0, description="Below this = SAFE")
    caution: float = Field(default=0.6, ge=0.0, le=1.0, description="Below this = CAUTION")
    unsafe: float = Field(default=0.7, ge=0.0, le=1.0, description="Above this = UNSAFE")
    
    @field_validator('unsafe')
    @classmethod
    def unsafe_must_be_highest(cls, v, info):
        safe = info.data.get('safe', 0.3)
        caution = info.data.get('caution', 0.6)
        if v < caution:
            raise ValueError('unsafe threshold must be >= caution threshold')
        return v


class Criterion(BaseModel):
    """A single evaluation criterion."""
    label: str = Field(..., description="Human-readable name")
    description: Optional[str] = Field(None, description="What this criterion detects")
    severity: Severity = Field(default=Severity.MEDIUM, description="How serious violations are")
    enabled: bool = Field(default=True, description="Whether to evaluate this criterion")
    thresholds: Thresholds = Field(default_factory=Thresholds)
    
    @property
    def weight(self) -> float:
        """Get numeric weight from severity."""
        return SEVERITY_WEIGHTS.get(self.severity, 1.0)


class OutputOptions(BaseModel):
    """What to include in evaluation output."""
    generate_report: bool = Field(default=True, description="Generate AI summary report")
    generate_labeled_video: bool = Field(default=True, description="Create video with detections overlaid")
    explain_verdict: bool = Field(default=True, description="Include detailed explanation")
    max_violations: int = Field(default=50, ge=1, le=500, description="Max violations to return")
    verdict_strategy: Optional[str] = Field(
        default=None, 
        description="Strategy for final verdict: any_unsafe, majority_unsafe, weighted_average, critical_only"
    )


class EvaluationCriteria(BaseModel):
    """
    User-facing evaluation criteria configuration.
    
    This is what users create/edit - no detector details.
    """
    name: str = Field(..., description="Name of this criteria set")
    version: str = Field(default="1.0", description="Schema version")
    description: Optional[str] = Field(None, description="Description of this criteria set")
    criteria: Dict[str, Criterion] = Field(..., description="Criteria to evaluate")
    options: OutputOptions = Field(default_factory=OutputOptions)
    
    @classmethod
    def from_yaml(cls, yaml_str: str) -> "EvaluationCriteria":
        """Parse from YAML string."""
        try:
            data = yaml.safe_load(yaml_str)
            return cls.model_validate(data)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML: {e}")
    
    @classmethod
    def from_json(cls, json_str: str) -> "EvaluationCriteria":
        """Parse from JSON string."""
        try:
            data = json.loads(json_str)
            return cls.model_validate(data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")
    
    @classmethod
    def from_file(cls, file_path: str) -> "EvaluationCriteria":
        """Load from YAML or JSON file."""
        with open(file_path, 'r') as f:
            content = f.read()
        
        if file_path.endswith(('.yml', '.yaml')):
            return cls.from_yaml(content)
        elif file_path.endswith('.json'):
            return cls.from_json(content)
        else:
            # Try YAML first, then JSON
            try:
                return cls.from_yaml(content)
            except ValueError:
                return cls.from_json(content)
    
    def to_yaml(self) -> str:
        """Export to YAML string."""
        data = self.model_dump(mode='json')
        return yaml.dump(data, default_flow_style=False, sort_keys=False)
    
    def to_json(self, indent: int = 2) -> str:
        """Export to JSON string."""
        return self.model_dump_json(indent=indent)
    
    def get_enabled_criteria(self) -> Dict[str, Criterion]:
        """Get only enabled criteria."""
        return {k: v for k, v in self.criteria.items() if v.enabled}


# ===== BUILT-IN PRESETS =====

CHILD_SAFETY_CRITERIA = EvaluationCriteria(
    name="Child Safety",
    description="Evaluates content for child-appropriate viewing",
    criteria={
        "violence": Criterion(
            label="Violence",
            description="Physical violence, weapons, blood, fighting, assault",
            severity=Severity.HIGH,
            thresholds=Thresholds(safe=0.3, caution=0.6, unsafe=0.7)
        ),
        "profanity": Criterion(
            label="Profanity",
            description="Explicit language, curse words, vulgar content",
            severity=Severity.MEDIUM,
            thresholds=Thresholds(safe=0.4, caution=0.6, unsafe=0.75)
        ),
        "sexual": Criterion(
            label="Sexual Content",
            description="Nudity, sexual acts, adult themes",
            severity=Severity.CRITICAL,
            thresholds=Thresholds(safe=0.2, caution=0.4, unsafe=0.5)
        ),
        "drugs": Criterion(
            label="Drugs & Substances",
            description="Drug use, paraphernalia, substance abuse",
            severity=Severity.HIGH,
            thresholds=Thresholds(safe=0.3, caution=0.5, unsafe=0.6)
        ),
        "hate": Criterion(
            label="Hate Speech",
            description="Discrimination, harassment, slurs, extremism",
            severity=Severity.CRITICAL,
            thresholds=Thresholds(safe=0.2, caution=0.4, unsafe=0.5)
        )
    }
)

BRAND_SAFETY_CRITERIA = EvaluationCriteria(
    name="Brand Safety",
    description="Evaluates content for brand-safe advertising placement",
    criteria={
        "violence": Criterion(
            label="Violence",
            description="Any violent content or imagery",
            severity=Severity.HIGH,
            thresholds=Thresholds(safe=0.2, caution=0.4, unsafe=0.5)
        ),
        "adult": Criterion(
            label="Adult Content",
            description="Sexual, suggestive, or mature content",
            severity=Severity.CRITICAL,
            thresholds=Thresholds(safe=0.1, caution=0.3, unsafe=0.4)
        ),
        "controversial": Criterion(
            label="Controversial Topics",
            description="Political, religious, or divisive content",
            severity=Severity.MEDIUM,
            thresholds=Thresholds(safe=0.4, caution=0.6, unsafe=0.7)
        ),
        "negative": Criterion(
            label="Negative Sentiment",
            description="Sad, disturbing, or negative emotional content",
            severity=Severity.LOW,
            thresholds=Thresholds(safe=0.5, caution=0.7, unsafe=0.8)
        )
    }
)

GENERAL_MODERATION_CRITERIA = EvaluationCriteria(
    name="General Moderation",
    description="Standard content moderation for user-generated content",
    criteria={
        "violence": Criterion(
            label="Violence",
            description="Physical violence or gore",
            severity=Severity.HIGH,
            thresholds=Thresholds(safe=0.4, caution=0.6, unsafe=0.7)
        ),
        "nudity": Criterion(
            label="Nudity",
            description="Nudity or explicit imagery",
            severity=Severity.HIGH,
            thresholds=Thresholds(safe=0.3, caution=0.5, unsafe=0.6)
        ),
        "hate": Criterion(
            label="Hate & Harassment",
            description="Hate speech, bullying, harassment",
            severity=Severity.CRITICAL,
            thresholds=Thresholds(safe=0.3, caution=0.5, unsafe=0.6)
        ),
        "spam": Criterion(
            label="Spam & Scams",
            description="Spammy or scam content",
            severity=Severity.LOW,
            thresholds=Thresholds(safe=0.5, caution=0.7, unsafe=0.8)
        )
    }
)

# Registry of built-in presets
BUILT_IN_PRESETS: Dict[str, EvaluationCriteria] = {
    "child_safety": CHILD_SAFETY_CRITERIA,
    "brand_safety": BRAND_SAFETY_CRITERIA,
    "general_moderation": GENERAL_MODERATION_CRITERIA,
}


def get_preset(preset_id: str) -> EvaluationCriteria:
    """Get a built-in preset by ID."""
    if preset_id not in BUILT_IN_PRESETS:
        raise ValueError(f"Unknown preset: {preset_id}. Available: {list(BUILT_IN_PRESETS.keys())}")
    return BUILT_IN_PRESETS[preset_id]


def list_presets() -> Dict[str, str]:
    """List available presets with their names."""
    return {pid: preset.name for pid, preset in BUILT_IN_PRESETS.items()}


def parse_criteria(data: dict) -> EvaluationCriteria:
    """
    Parse criteria from a dictionary.
    
    Accepts raw dict, typically from JSON or YAML parsing.
    """
    return EvaluationCriteria.model_validate(data)
