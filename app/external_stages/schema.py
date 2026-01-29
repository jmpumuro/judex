"""
YAML schema definition and parser for external stages.

Supports this YAML shape:
```yaml
version: v1
stages:
  - id: customer_policy
    name: "Customer Policy (External)"
    type: external_stage
    endpoint:
      url: "https://example.com/stage"
      auth:
        type: bearer
        token: "${CUSTOMER_STAGE_TOKEN}"
    timeout_ms: 2000
    retries: 1
    input_mapping:
      vision: "$.vision_detections"
      transcript: "$.transcript.full_text"
    output_mapping:
      evidence: "$.evidence.customer_policy"
```
"""
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum

import yaml
from app.core.logging import get_logger

logger = get_logger("external_stages.schema")


class AuthType(str, Enum):
    """Supported authentication types."""
    NONE = "none"
    BEARER = "bearer"
    BASIC = "basic"
    API_KEY = "api_key"
    CUSTOM_HEADER = "custom_header"


@dataclass
class AuthConfig:
    """Authentication configuration for external endpoints."""
    type: AuthType = AuthType.NONE
    token: Optional[str] = None  # For bearer auth
    username: Optional[str] = None  # For basic auth
    password: Optional[str] = None  # For basic auth
    api_key: Optional[str] = None  # For API key auth
    header_name: Optional[str] = None  # For custom header
    header_value: Optional[str] = None  # For custom header
    
    def resolve_env_vars(self) -> "AuthConfig":
        """Resolve environment variable references (${VAR_NAME})."""
        def resolve(value: Optional[str]) -> Optional[str]:
            if not value:
                return value
            # Match ${VAR_NAME} pattern
            pattern = r'\$\{([^}]+)\}'
            def replacer(match):
                var_name = match.group(1)
                return os.environ.get(var_name, match.group(0))
            return re.sub(pattern, replacer, value)
        
        return AuthConfig(
            type=self.type,
            token=resolve(self.token),
            username=resolve(self.username),
            password=resolve(self.password),
            api_key=resolve(self.api_key),
            header_name=resolve(self.header_name),
            header_value=resolve(self.header_value),
        )


@dataclass
class StageEndpoint:
    """External endpoint configuration."""
    url: str
    method: str = "POST"
    auth: AuthConfig = field(default_factory=AuthConfig)
    headers: Dict[str, str] = field(default_factory=dict)
    
    def resolve_env_vars(self) -> "StageEndpoint":
        """Resolve environment variables in URL and headers."""
        pattern = r'\$\{([^}]+)\}'
        
        def resolve(value: str) -> str:
            def replacer(match):
                var_name = match.group(1)
                return os.environ.get(var_name, match.group(0))
            return re.sub(pattern, replacer, value)
        
        resolved_headers = {k: resolve(v) for k, v in self.headers.items()}
        
        return StageEndpoint(
            url=resolve(self.url),
            method=self.method,
            auth=self.auth.resolve_env_vars(),
            headers=resolved_headers,
        )


@dataclass
class StageMapping:
    """Input/output mapping using JSONPath-like expressions."""
    input_mapping: Dict[str, str] = field(default_factory=dict)
    output_mapping: Dict[str, str] = field(default_factory=dict)
    
    def map_input(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map pipeline state to request payload using input_mapping.
        
        Mapping format: "target_key": "$.source.path"
        - $.field - Top level field
        - $.field.nested - Nested field access
        - $.field[0] - Array index access
        """
        result = {}
        for target_key, source_path in self.input_mapping.items():
            value = self._extract_value(state, source_path)
            if value is not None:
                result[target_key] = value
        return result
    
    def map_output(self, response: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map response to state updates using output_mapping.
        
        Mapping format: "$.state.path": "$.response.path" or "state_key": "$.response.path"
        """
        updates = {}
        for state_path, response_path in self.output_mapping.items():
            value = self._extract_value(response, response_path)
            if value is not None:
                # Determine target key (strip leading $. if present)
                target = state_path.lstrip('$.')
                updates[target] = value
        return updates
    
    def _extract_value(self, data: Dict[str, Any], path: str) -> Any:
        """Extract value from nested dict using JSONPath-like expression."""
        if not path.startswith('$.'):
            return data.get(path)
        
        # Remove $. prefix
        path = path[2:]
        
        current = data
        for part in path.split('.'):
            # Handle array index: field[0]
            match = re.match(r'(\w+)\[(\d+)\]', part)
            if match:
                field_name, index = match.groups()
                if not isinstance(current, dict) or field_name not in current:
                    return None
                current = current[field_name]
                if not isinstance(current, list) or int(index) >= len(current):
                    return None
                current = current[int(index)]
            else:
                if not isinstance(current, dict) or part not in current:
                    return None
                current = current[part]
        
        return current


@dataclass
class ExternalStageConfig:
    """Configuration for a single external stage."""
    id: str
    name: str
    type: str = "external_stage"
    endpoint: StageEndpoint = field(default_factory=lambda: StageEndpoint(url=""))
    mapping: StageMapping = field(default_factory=StageMapping)
    timeout_ms: int = 5000
    retries: int = 1
    retry_delay_ms: int = 500
    enabled: bool = True
    description: str = ""
    
    # Metadata for UI
    display_color: str = "#8B5CF6"  # Purple for external stages
    icon: str = "external-link"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "endpoint": {
                "url": self.endpoint.url,
                "method": self.endpoint.method,
                "auth": {
                    "type": self.endpoint.auth.type.value,
                    "token": self.endpoint.auth.token,
                    "header_name": self.endpoint.auth.header_name,
                },
                "headers": self.endpoint.auth.headers if hasattr(self.endpoint.auth, 'headers') else {},
            },
            "timeout_ms": self.timeout_ms,
            "retries": self.retries,
            "retry_delay_ms": self.retry_delay_ms,
            "enabled": self.enabled,
            "description": self.description,
            "input_mapping": self.mapping.input_mapping,
            "output_mapping": self.mapping.output_mapping,
            "display_color": self.display_color,
            "icon": self.icon,
        }


@dataclass
class ExternalStagesDefinition:
    """Root document for external stages YAML."""
    version: str = "v1"
    stages: List[ExternalStageConfig] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "version": self.version,
            "stages": [s.to_dict() for s in self.stages],
        }


class ValidationError(Exception):
    """YAML validation error with user-friendly message."""
    def __init__(self, message: str, path: str = "", line: int = None):
        self.message = message
        self.path = path
        self.line = line
        super().__init__(self._format_message())
    
    def _format_message(self) -> str:
        parts = [self.message]
        if self.path:
            parts.append(f"at path: {self.path}")
        if self.line:
            parts.append(f"(line {self.line})")
        return " ".join(parts)


def parse_auth_config(data: Dict[str, Any]) -> AuthConfig:
    """Parse authentication configuration from dict."""
    if not data:
        return AuthConfig()
    
    auth_type_str = data.get("type", "none").lower()
    try:
        auth_type = AuthType(auth_type_str)
    except ValueError:
        raise ValidationError(
            f"Invalid auth type: '{auth_type_str}'. "
            f"Valid types: {[t.value for t in AuthType]}"
        )
    
    return AuthConfig(
        type=auth_type,
        token=data.get("token"),
        username=data.get("username"),
        password=data.get("password"),
        api_key=data.get("api_key"),
        header_name=data.get("header_name"),
        header_value=data.get("header_value"),
    )


def parse_endpoint(data: Dict[str, Any], path: str = "endpoint") -> StageEndpoint:
    """Parse endpoint configuration from dict."""
    if not data:
        raise ValidationError("Endpoint configuration is required", path)
    
    url = data.get("url")
    if not url:
        raise ValidationError("Endpoint URL is required", f"{path}.url")
    
    return StageEndpoint(
        url=url,
        method=data.get("method", "POST").upper(),
        auth=parse_auth_config(data.get("auth", {})),
        headers=data.get("headers", {}),
    )


def parse_stage_config(data: Dict[str, Any], index: int = 0) -> ExternalStageConfig:
    """Parse a single stage configuration from dict."""
    path = f"stages[{index}]"
    
    # Required fields
    stage_id = data.get("id")
    if not stage_id:
        raise ValidationError("Stage ID is required", f"{path}.id")
    
    if not re.match(r'^[a-z][a-z0-9_]*$', stage_id):
        raise ValidationError(
            f"Stage ID '{stage_id}' is invalid. "
            "Must start with lowercase letter and contain only lowercase letters, numbers, and underscores.",
            f"{path}.id"
        )
    
    name = data.get("name") or stage_id.replace("_", " ").title()
    
    # Endpoint
    endpoint = parse_endpoint(data.get("endpoint", {}), f"{path}.endpoint")
    
    # Mappings
    input_mapping = data.get("input_mapping", {})
    output_mapping = data.get("output_mapping", {})
    
    # Validate mappings format
    for key, value in input_mapping.items():
        if not isinstance(value, str):
            raise ValidationError(
                f"Input mapping value must be a string path",
                f"{path}.input_mapping.{key}"
            )
    
    for key, value in output_mapping.items():
        if not isinstance(value, str):
            raise ValidationError(
                f"Output mapping value must be a string path",
                f"{path}.output_mapping.{key}"
            )
    
    mapping = StageMapping(
        input_mapping=input_mapping,
        output_mapping=output_mapping,
    )
    
    # Optional fields with defaults
    timeout_ms = data.get("timeout_ms", 5000)
    if not isinstance(timeout_ms, int) or timeout_ms < 100:
        raise ValidationError(
            "timeout_ms must be an integer >= 100",
            f"{path}.timeout_ms"
        )
    
    retries = data.get("retries", 1)
    if not isinstance(retries, int) or retries < 0 or retries > 5:
        raise ValidationError(
            "retries must be an integer between 0 and 5",
            f"{path}.retries"
        )
    
    return ExternalStageConfig(
        id=stage_id,
        name=name,
        type=data.get("type", "external_stage"),
        endpoint=endpoint,
        mapping=mapping,
        timeout_ms=timeout_ms,
        retries=retries,
        retry_delay_ms=data.get("retry_delay_ms", 500),
        enabled=data.get("enabled", True),
        description=data.get("description", ""),
        display_color=data.get("display_color", "#8B5CF6"),
        icon=data.get("icon", "external-link"),
    )


def parse_stage_yaml(yaml_content: str) -> ExternalStagesDefinition:
    """
    Parse YAML content into ExternalStagesDefinition.
    
    Args:
        yaml_content: Raw YAML string
        
    Returns:
        Parsed ExternalStagesDefinition
        
    Raises:
        ValidationError: If YAML is invalid or doesn't match schema
    """
    try:
        data = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        raise ValidationError(f"Invalid YAML syntax: {e}")
    
    if not isinstance(data, dict):
        raise ValidationError("YAML root must be a mapping/object")
    
    # Version check
    version = data.get("version", "v1")
    if version not in ("v1",):
        raise ValidationError(f"Unsupported schema version: {version}. Supported: v1")
    
    # Parse stages
    stages_data = data.get("stages", [])
    if not isinstance(stages_data, list):
        raise ValidationError("'stages' must be a list", "stages")
    
    if not stages_data:
        raise ValidationError("At least one stage is required", "stages")
    
    stages = []
    seen_ids = set()
    for i, stage_data in enumerate(stages_data):
        if not isinstance(stage_data, dict):
            raise ValidationError(f"Stage definition must be a mapping", f"stages[{i}]")
        
        stage = parse_stage_config(stage_data, i)
        
        # Check for duplicate IDs
        if stage.id in seen_ids:
            raise ValidationError(f"Duplicate stage ID: '{stage.id}'", f"stages[{i}].id")
        seen_ids.add(stage.id)
        
        stages.append(stage)
    
    return ExternalStagesDefinition(version=version, stages=stages)


def validate_stage_config(yaml_content: str) -> Dict[str, Any]:
    """
    Validate YAML and return validation result.
    
    Returns:
        {
            "valid": bool,
            "error": str or None,
            "stages": list of stage summaries if valid
        }
    """
    try:
        definition = parse_stage_yaml(yaml_content)
        return {
            "valid": True,
            "error": None,
            "stages": [
                {"id": s.id, "name": s.name, "endpoint": s.endpoint.url}
                for s in definition.stages
            ]
        }
    except ValidationError as e:
        return {
            "valid": False,
            "error": str(e),
            "stages": []
        }
    except Exception as e:
        logger.error(f"Unexpected error validating YAML: {e}")
        return {
            "valid": False,
            "error": f"Unexpected error: {str(e)}",
            "stages": []
        }
