"""
External HTTP stage plugin - executes YAML-defined external stages.

This plugin makes HTTP calls to customer endpoints with:
- Configurable authentication (Bearer, Basic, API Key, Custom Header)
- Input/output mapping using JSONPath-like expressions
- Timeout and retry handling
- Progress reporting via SSE
"""
import asyncio
import time
from typing import Any, Dict, Optional, Set
import httpx

from app.pipeline.stages.base import StagePlugin, StageSpec
from app.external_stages.schema import ExternalStageConfig, AuthType
from app.core.logging import get_logger

logger = get_logger("external_stages.plugin")


class ExternalHttpStagePlugin(StagePlugin):
    """
    Pipeline stage that calls an external HTTP endpoint.
    
    The stage:
    1. Maps pipeline state to request payload using input_mapping
    2. Calls external endpoint with configured auth
    3. Maps response to state updates using output_mapping
    4. Reports progress via callback
    """
    
    def __init__(self, config: ExternalStageConfig):
        """
        Initialize with stage configuration.
        
        Args:
            config: ExternalStageConfig with endpoint and mapping details
        """
        self._config = config
        self._stage_type = config.id
    
    @property
    def stage_type(self) -> str:
        return self._stage_type
    
    @property
    def is_external(self) -> bool:
        """External HTTP stages return True - used by runner for output persistence."""
        return True
    
    @property
    def display_name(self) -> str:
        return self._config.name
    
    @property
    def input_keys(self) -> Set[str]:
        """Extract input keys from mapping."""
        keys = set()
        for source_path in self._config.mapping.input_mapping.values():
            # Extract top-level key from path like "$.vision_detections"
            if source_path.startswith('$.'):
                top_key = source_path[2:].split('.')[0].split('[')[0]
                keys.add(top_key)
            else:
                keys.add(source_path)
        return keys
    
    @property
    def output_keys(self) -> Set[str]:
        """Extract output keys from mapping."""
        keys = set()
        for state_path in self._config.mapping.output_mapping.keys():
            if state_path.startswith('$.'):
                top_key = state_path[2:].split('.')[0]
                keys.add(top_key)
            else:
                keys.add(state_path)
        return keys
    
    @property
    def config(self) -> ExternalStageConfig:
        """Get the stage configuration."""
        return self._config
    
    def validate_state(self, state: Dict[str, Any], spec: StageSpec) -> Optional[str]:
        """
        Validate state before execution.
        
        For external stages, we're more lenient - missing inputs
        might be acceptable for some endpoints.
        """
        # Check if at least one input key is available
        available_inputs = [k for k in self.input_keys if k in state]
        if not available_inputs and self._config.mapping.input_mapping:
            return f"No input data available for external stage. Expected one of: {self.input_keys}"
        return None
    
    async def run(
        self,
        state: Dict[str, Any],
        spec: StageSpec
    ) -> Dict[str, Any]:
        """
        Execute the external stage by calling the configured endpoint.
        
        Args:
            state: Current pipeline state
            spec: Stage specification (may contain runtime overrides)
            
        Returns:
            Updated state with mapped response values
        """
        # Resolve environment variables in endpoint config
        endpoint = self._config.endpoint.resolve_env_vars()
        
        # Build request payload from state
        payload = self._config.mapping.map_input(state)
        
        # Add context metadata
        payload["_context"] = {
            "stage_id": self._config.id,
            "video_id": state.get("video_id"),
            "evaluation_id": state.get("evaluation_id"),
            "timestamp": time.time(),
        }
        
        logger.info(
            f"Calling external stage '{self._config.id}' at {endpoint.url} "
            f"with {len(payload)} payload keys"
        )
        
        # Build headers
        headers = dict(endpoint.headers)
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"
        headers["X-Judex-Stage"] = self._config.id
        
        # Add authentication
        auth = None
        if endpoint.auth.type == AuthType.BEARER:
            if endpoint.auth.token:
                headers["Authorization"] = f"Bearer {endpoint.auth.token}"
        elif endpoint.auth.type == AuthType.BASIC:
            if endpoint.auth.username and endpoint.auth.password:
                auth = httpx.BasicAuth(endpoint.auth.username, endpoint.auth.password)
        elif endpoint.auth.type == AuthType.API_KEY:
            if endpoint.auth.api_key:
                headers["X-API-Key"] = endpoint.auth.api_key
        elif endpoint.auth.type == AuthType.CUSTOM_HEADER:
            if endpoint.auth.header_name and endpoint.auth.header_value:
                headers[endpoint.auth.header_name] = endpoint.auth.header_value
        
        # Execute with retries
        last_error = None
        for attempt in range(self._config.retries + 1):
            try:
                response = await self._make_request(
                    url=endpoint.url,
                    method=endpoint.method,
                    headers=headers,
                    auth=auth,
                    payload=payload,
                    timeout_ms=self._config.timeout_ms,
                )
                
                # Map response to state updates
                updates = self._config.mapping.map_output(response, state)
                
                # Add stage metadata
                updates[f"external_stage_{self._config.id}"] = {
                    "status": "completed",
                    "response_keys": list(response.keys()) if isinstance(response, dict) else [],
                    "mapped_keys": list(updates.keys()),
                    "attempt": attempt + 1,
                }
                
                logger.info(
                    f"External stage '{self._config.id}' completed, "
                    f"mapped {len(updates)} output keys"
                )
                
                return updates
                
            except httpx.TimeoutException as e:
                last_error = f"Timeout after {self._config.timeout_ms}ms"
                logger.warning(
                    f"External stage '{self._config.id}' timeout (attempt {attempt + 1})"
                )
            except httpx.HTTPStatusError as e:
                last_error = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                logger.warning(
                    f"External stage '{self._config.id}' HTTP error: {last_error} "
                    f"(attempt {attempt + 1})"
                )
            except Exception as e:
                last_error = str(e)
                logger.error(
                    f"External stage '{self._config.id}' error: {e} "
                    f"(attempt {attempt + 1})"
                )
            
            # Wait before retry
            if attempt < self._config.retries:
                await asyncio.sleep(self._config.retry_delay_ms / 1000.0)
        
        # All retries failed
        logger.error(
            f"External stage '{self._config.id}' failed after "
            f"{self._config.retries + 1} attempts: {last_error}"
        )
        
        # Return error state (don't raise - let pipeline continue)
        return {
            f"external_stage_{self._config.id}": {
                "status": "failed",
                "error": last_error,
                "attempts": self._config.retries + 1,
            }
        }
    
    async def _make_request(
        self,
        url: str,
        method: str,
        headers: Dict[str, str],
        auth: Optional[httpx.BasicAuth],
        payload: Dict[str, Any],
        timeout_ms: int,
    ) -> Dict[str, Any]:
        """Make HTTP request to external endpoint."""
        timeout = httpx.Timeout(timeout_ms / 1000.0)
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            if method == "POST":
                response = await client.post(
                    url,
                    json=payload,
                    headers=headers,
                    auth=auth,
                )
            elif method == "PUT":
                response = await client.put(
                    url,
                    json=payload,
                    headers=headers,
                    auth=auth,
                )
            elif method == "GET":
                response = await client.get(
                    url,
                    params=payload,
                    headers=headers,
                    auth=auth,
                )
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            
            # Parse response
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                return response.json()
            else:
                # Wrap non-JSON response
                return {"raw_response": response.text}
    
    def get_stage_output(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Extract stage-specific output for persistence/display."""
        output = {}
        
        # Include output keys
        for key in self.output_keys:
            if key in state:
                output[key] = state[key]
        
        # Include stage status
        status_key = f"external_stage_{self._config.id}"
        if status_key in state:
            output["_status"] = state[status_key]
        
        return output


def create_external_plugin(config: ExternalStageConfig) -> ExternalHttpStagePlugin:
    """Factory function to create an external stage plugin."""
    return ExternalHttpStagePlugin(config)
