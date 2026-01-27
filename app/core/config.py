"""
Configuration management for SafeVid service.
"""
import os
from typing import Dict, Any
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # API Settings
    app_name: str = "SafeVid - Child Safety Video Analysis"
    version: str = "1.0.0"
    api_prefix: str = "/v1"
    
    # Model Settings
    hf_home: str = os.getenv("HF_HOME", "/models/hf")
    transformers_cache: str = os.getenv("TRANSFORMERS_CACHE", "/models/hf/transformers")
    
    # YOLO26 Vision Model
    yolo26_model_id: str = os.getenv("YOLO26_MODEL_ID", "openvision/yolo26-s")
    yolo26_confidence: float = float(os.getenv("YOLO26_CONFIDENCE", "0.25"))
    
    # Violence Detection Model
    violence_model_id: str = os.getenv(
        "VIOLENCE_MODEL_ID", 
        "microsoft/xclip-base-patch32-16-frames"  # Better multimodal model
    )
    use_xclip_violence: bool = os.getenv("USE_XCLIP_VIOLENCE", "true").lower() == "true"
    
    # Whisper ASR Model
    whisper_model_id: str = os.getenv("WHISPER_MODEL_ID", "openai/whisper-small")
    
    # Text Moderation Model
    profanity_model_id: str = os.getenv("PROFANITY_MODEL_ID", "tarekziade/pardonmyai")
    nli_model_id: str = os.getenv("NLI_MODEL_ID", "facebook/bart-large-mnli")
    
    # LLM Settings (Qwen for local, OpenAI as fallback)
    llm_provider: str = os.getenv("LLM_PROVIDER", "qwen")  # "qwen" or "openai"
    qwen_model_id: str = os.getenv("QWEN_MODEL_ID", "Qwen/Qwen2.5-0.5B-Instruct")  # Use 0.5B for memory efficiency
    
    # OpenAI Settings (fallback)
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    
    # Database Settings
    database_url: str = os.getenv("DATABASE_URL", "postgresql://docker:docker@localhost:5432/safevid")
    
    # MinIO Object Storage Settings
    minio_endpoint: str = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    minio_external_endpoint: str = os.getenv("MINIO_EXTERNAL_ENDPOINT", "localhost:9000")  # For browser access
    minio_access_key: str = os.getenv("MINIO_ACCESS_KEY", "safevid")
    minio_secret_key: str = os.getenv("MINIO_SECRET_KEY", "safevid123")
    minio_bucket: str = os.getenv("MINIO_BUCKET", "safevid")
    minio_secure: bool = os.getenv("MINIO_SECURE", "false").lower() == "true"
    
    # Video Processing Settings
    default_sampling_fps: float = float(os.getenv("DEFAULT_SAMPLING_FPS", "1.0"))
    segment_duration_sec: float = float(os.getenv("SEGMENT_DURATION_SEC", "3.0"))
    violence_frames_per_segment: int = int(os.getenv("VIOLENCE_FRAMES_PER_SEGMENT", "16"))
    ocr_interval_sec: float = float(os.getenv("OCR_INTERVAL_SEC", "2.0"))
    
    # Working Directory
    temp_dir: str = os.getenv("TEMP_DIR", "/tmp/safevid")
    
    # Persistent Data Directory
    data_dir: str = os.getenv("DATA_DIR", "/data/safevid")
    
    # Policy Thresholds
    threshold_unsafe_violence: float = 0.75
    threshold_unsafe_sexual: float = 0.60
    threshold_unsafe_hate: float = 0.60
    threshold_unsafe_drugs: float = 0.70
    
    threshold_caution_violence: float = 0.40
    threshold_caution_profanity: float = 0.40
    threshold_caution_drugs: float = 0.40
    threshold_caution_sexual: float = 0.30
    threshold_caution_hate: float = 0.30
    
    # Evidence score weights
    weight_violence_model: float = 0.6
    weight_yolo_weapons: float = 0.3
    weight_transcript_violence: float = 0.1
    
    weight_transcript_profanity: float = 0.7
    weight_ocr_profanity: float = 0.3
    
    weight_transcript_sexual: float = 0.7
    weight_ocr_sexual: float = 0.2
    weight_vision_sexual: float = 0.1
    
    weight_transcript_drugs: float = 0.5
    weight_yolo_drugs: float = 0.4
    weight_ocr_drugs: float = 0.1
    
    weight_transcript_hate: float = 0.7
    weight_ocr_hate: float = 0.3
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()


def get_policy_config(overrides: Dict[str, Any] = None) -> Dict[str, Any]:
    """Get policy configuration with optional overrides."""
    base_config = {
        "thresholds": {
            "unsafe": {
                "violence": settings.threshold_unsafe_violence,
                "sexual": settings.threshold_unsafe_sexual,
                "hate": settings.threshold_unsafe_hate,
                "drugs": settings.threshold_unsafe_drugs,
            },
            "caution": {
                "violence": settings.threshold_caution_violence,
                "profanity": settings.threshold_caution_profanity,
                "drugs": settings.threshold_caution_drugs,
                "sexual": settings.threshold_caution_sexual,
                "hate": settings.threshold_caution_hate,
            }
        },
        "weights": {
            "violence": {
                "violence_model": settings.weight_violence_model,
                "yolo_weapons": settings.weight_yolo_weapons,
                "transcript": settings.weight_transcript_violence,
            },
            "profanity": {
                "transcript": settings.weight_transcript_profanity,
                "ocr": settings.weight_ocr_profanity,
            },
            "sexual": {
                "transcript": settings.weight_transcript_sexual,
                "ocr": settings.weight_ocr_sexual,
                "vision": settings.weight_vision_sexual,
            },
            "drugs": {
                "transcript": settings.weight_transcript_drugs,
                "yolo": settings.weight_yolo_drugs,
                "ocr": settings.weight_ocr_drugs,
            },
            "hate": {
                "transcript": settings.weight_transcript_hate,
                "ocr": settings.weight_ocr_hate,
            }
        },
        "sampling_fps": settings.default_sampling_fps,
        "segment_duration": settings.segment_duration_sec,
        "ocr_interval": settings.ocr_interval_sec,
    }
    
    if overrides:
        # Deep merge overrides
        for key, value in overrides.items():
            if key in base_config and isinstance(base_config[key], dict):
                base_config[key].update(value)
            else:
                base_config[key] = value
    
    return base_config


def get_policy_presets() -> Dict[str, Dict[str, Any]]:
    """Get predefined policy presets for different use cases."""
    return {
        "strict": {
            "name": "Strict (High Sensitivity)",
            "description": "Maximum protection, flags more content",
            "thresholds": {
                "unsafe": {
                    "violence": 0.60,
                    "sexual": 0.45,
                    "hate": 0.45,
                    "drugs": 0.55,
                },
                "caution": {
                    "violence": 0.30,
                    "profanity": 0.30,
                    "drugs": 0.30,
                    "sexual": 0.20,
                    "hate": 0.20,
                }
            }
        },
        "balanced": {
            "name": "Balanced (Default)",
            "description": "Balanced sensitivity, moderate flagging",
            "thresholds": {
                "unsafe": {
                    "violence": 0.75,
                    "sexual": 0.60,
                    "hate": 0.60,
                    "drugs": 0.70,
                },
                "caution": {
                    "violence": 0.40,
                    "profanity": 0.40,
                    "drugs": 0.40,
                    "sexual": 0.30,
                    "hate": 0.30,
                }
            }
        },
        "lenient": {
            "name": "Lenient (Low Sensitivity)",
            "description": "Reduced false positives, flags only clear violations",
            "thresholds": {
                "unsafe": {
                    "violence": 0.85,
                    "sexual": 0.75,
                    "hate": 0.75,
                    "drugs": 0.80,
                },
                "caution": {
                    "violence": 0.55,
                    "profanity": 0.55,
                    "drugs": 0.55,
                    "sexual": 0.45,
                    "hate": 0.45,
                }
            }
        },
        "custom": {
            "name": "Custom",
            "description": "Manually configured thresholds",
            "thresholds": {}
        }
    }

