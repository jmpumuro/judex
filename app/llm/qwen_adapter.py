"""
Qwen LLM Adapter - Local LLM using HuggingFace Transformers.

Industry Standard: Uses 4-bit quantization for memory efficiency.
"""
from typing import Optional, Dict, Any
import torch
from app.llm.base import LLMAdapter, LLMResponse
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("llm.qwen")


class QwenAdapter(LLMAdapter):
    """
    Qwen LLM adapter using HuggingFace Transformers.
    
    Features:
    - 4-bit quantization for ~75% memory reduction
    - Automatic GPU/CPU detection
    - Memory management with unload()
    """
    
    def __init__(self, model_id: Optional[str] = None):
        self._model_id = model_id or settings.qwen_model_id
        self._model = None
        self._tokenizer = None
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
    
    @property
    def provider_name(self) -> str:
        return "qwen"
    
    @property
    def model_name(self) -> str:
        return self._model_id
    
    def is_available(self) -> bool:
        """Qwen is available if we can load transformers."""
        try:
            import transformers
            return True
        except ImportError:
            return False
    
    def _load_model(self):
        """Load Qwen model with 4-bit quantization."""
        if self._model is not None:
            return
        
        logger.info(f"Loading Qwen model: {self._model_id}")
        
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
            
            # Load tokenizer
            self._tokenizer = AutoTokenizer.from_pretrained(
                self._model_id,
                cache_dir=settings.transformers_cache,
                trust_remote_code=True
            )
            
            # Configure 4-bit quantization for GPU
            if self._device == "cuda":
                try:
                    quantization_config = BitsAndBytesConfig(
                        load_in_4bit=True,
                        bnb_4bit_quant_type="nf4",
                        bnb_4bit_compute_dtype=torch.float16,
                        bnb_4bit_use_double_quant=True,
                    )
                    
                    self._model = AutoModelForCausalLM.from_pretrained(
                        self._model_id,
                        cache_dir=settings.transformers_cache,
                        quantization_config=quantization_config,
                        device_map="auto",
                        trust_remote_code=True,
                        low_cpu_mem_usage=True
                    )
                    logger.info(f"Qwen loaded with 4-bit quantization on GPU")
                except Exception as e:
                    logger.warning(f"4-bit quantization failed: {e}, falling back to CPU")
                    self._device = "cpu"
            
            # CPU fallback
            if self._device == "cpu" and self._model is None:
                logger.warning("Running Qwen on CPU - inference will be slow")
                self._model = AutoModelForCausalLM.from_pretrained(
                    self._model_id,
                    cache_dir=settings.transformers_cache,
                    torch_dtype=torch.float32,
                    trust_remote_code=True,
                    low_cpu_mem_usage=True
                )
                self._model = self._model.to(self._device)
            
            self._model.eval()
            logger.info(f"Qwen model loaded on {self._device}")
            
        except Exception as e:
            logger.error(f"Failed to load Qwen model: {e}")
            raise
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 800,
        temperature: float = 0.3,
        **kwargs
    ) -> LLMResponse:
        """Generate completion using local Qwen model."""
        self._load_model()
        
        try:
            # Format messages for chat
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            # Apply chat template
            text = self._tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )
            
            # Tokenize
            inputs = self._tokenizer(text, return_tensors="pt")
            input_length = inputs['input_ids'].shape[1]
            
            # Move to device
            if self._device == "cuda" and hasattr(self._model, 'hf_device_map'):
                inputs = {k: v.to("cuda") for k, v in inputs.items()}
            else:
                inputs = {k: v.to(self._device) for k, v in inputs.items()}
            
            logger.info(f"Generating with Qwen (input: {input_length} tokens)...")
            
            # Generate
            with torch.no_grad():
                outputs = self._model.generate(
                    **inputs,
                    max_new_tokens=max_tokens,
                    temperature=temperature if temperature > 0 else 1.0,
                    do_sample=temperature > 0,
                    pad_token_id=self._tokenizer.eos_token_id,
                    use_cache=True,
                )
            
            # Decode response (skip input tokens)
            output_length = outputs.shape[1]
            content = self._tokenizer.decode(
                outputs[0][input_length:],
                skip_special_tokens=True
            ).strip()
            
            logger.info(f"Qwen generation successful ({output_length - input_length} new tokens)")
            
            return LLMResponse(
                content=content,
                model=self._model_id,
                provider=self.provider_name,
                usage={
                    "prompt_tokens": input_length,
                    "completion_tokens": output_length - input_length,
                    "total_tokens": output_length,
                },
                finish_reason="stop",
                raw_response=outputs
            )
            
        except Exception as e:
            logger.error(f"Qwen generation failed: {e}")
            raise
    
    def unload(self) -> None:
        """Unload model to free memory."""
        if self._model is not None:
            del self._model
            self._model = None
        if self._tokenizer is not None:
            del self._tokenizer
            self._tokenizer = None
        
        if self._device == "cuda":
            torch.cuda.empty_cache()
            logger.info("Qwen model unloaded, GPU memory freed")
    
    def health_check(self) -> Dict[str, Any]:
        """Check Qwen model health."""
        base = super().health_check()
        base["device"] = self._device
        base["model_loaded"] = self._model is not None
        if self._device == "cuda":
            base["gpu_memory_gb"] = torch.cuda.memory_allocated() / 1024**3
        return base
