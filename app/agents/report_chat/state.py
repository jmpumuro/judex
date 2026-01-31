"""
State models for ReportChat agent.

Industry Standard: Typed state with Pydantic models for validation.
Follows LangGraph state patterns with clear separation of concerns.
"""
from typing import TypedDict, List, Dict, Any, Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class MessageRole(str, Enum):
    """Message roles in conversation."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ToolCallStatus(str, Enum):
    """Status of a tool call."""
    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"


class ToolCall(BaseModel):
    """Record of a tool invocation."""
    id: str = Field(..., description="Unique tool call ID")
    tool_name: str = Field(..., description="Name of the tool called")
    arguments: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[Any] = Field(None, description="Tool result (if completed)")
    status: ToolCallStatus = Field(ToolCallStatus.PENDING)
    error: Optional[str] = Field(None, description="Error message if failed")
    latency_ms: Optional[int] = Field(None, description="Execution time in ms")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    
    class Config:
        use_enum_values = True


class Message(BaseModel):
    """A single message in the conversation."""
    id: str = Field(..., description="Unique message ID")
    role: MessageRole = Field(..., description="Message author role")
    content: str = Field(..., description="Message content")
    tool_calls: List[ToolCall] = Field(default_factory=list, description="Tools called for this response")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    
    class Config:
        use_enum_values = True


class UserIntent(str, Enum):
    """Classified user intent for routing."""
    EXPLAIN_VERDICT = "explain_verdict"  # Why was this flagged?
    SHOW_EVIDENCE = "show_evidence"  # What evidence exists?
    STAGE_DETAILS = "stage_details"  # Which stage contributed?
    ARTIFACT_REQUEST = "artifact_request"  # Show video/transcript/etc
    COMPARISON = "comparison"  # Compare with other run
    GENERAL_QUESTION = "general_question"  # Other questions
    CLARIFICATION = "clarification"  # Follow-up clarification
    GREETING = "greeting"  # Hello, thanks, etc


class ChatState(TypedDict, total=False):
    """
    LangGraph state for ReportChat agent.
    
    Industry Standard: TypedDict for LangGraph compatibility.
    All fields are optional (total=False) to support partial updates.
    """
    # Core identifiers
    evaluation_id: str
    thread_id: str
    user_id: Optional[str]
    
    # Conversation state
    messages: List[Dict[str, Any]]  # Serialized Message objects
    current_message: str  # Current user input
    
    # Intent classification
    intent: str  # UserIntent value
    intent_confidence: float
    entities: Dict[str, Any]  # Extracted entities (stage names, criteria, etc.)
    
    # Tool execution
    tool_plan: List[str]  # Tools to call
    tool_results: Dict[str, Any]  # Results from tool calls
    pending_tool_calls: List[Dict[str, Any]]  # In-progress tool calls
    
    # Context (fetched data)
    evaluation_context: Dict[str, Any]  # Cached evaluation data
    stage_outputs: Dict[str, Any]  # Fetched stage outputs
    artifacts: Dict[str, Any]  # Fetched artifact references
    
    # Response generation
    response_draft: str
    citations: List[Dict[str, Any]]  # References to evidence
    
    # Memory management
    summary: str  # Summarized older messages
    message_count: int
    token_estimate: int
    
    # Tracing
    trace_id: str
    step_traces: List[Dict[str, Any]]


class ConversationMemory(BaseModel):
    """
    Persistent conversation state.
    
    Stored in database for thread continuity.
    """
    thread_id: str
    evaluation_id: str
    user_id: Optional[str] = None
    
    # Message history
    messages: List[Message] = Field(default_factory=list)
    
    # Summary of older messages (for long conversations)
    summary: Optional[str] = None
    summarized_up_to: int = 0  # Index of last summarized message
    
    # Cached context (avoid re-fetching)
    evaluation_snapshot: Optional[Dict[str, Any]] = None
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    message_count: int = 0
    
    class Config:
        use_enum_values = True


# =============================================================================
# State Helpers
# =============================================================================

def create_initial_state(
    evaluation_id: str,
    thread_id: str,
    user_message: str,
    user_id: Optional[str] = None
) -> ChatState:
    """Create initial state for a new chat turn."""
    return ChatState(
        evaluation_id=evaluation_id,
        thread_id=thread_id,
        user_id=user_id,
        current_message=user_message,
        messages=[],
        tool_plan=[],
        tool_results={},
        pending_tool_calls=[],
        evaluation_context={},
        stage_outputs={},
        artifacts={},
        citations=[],
        step_traces=[],
        message_count=0,
        token_estimate=0,
    )


def message_to_dict(msg: Message) -> Dict[str, Any]:
    """Convert Message to dict for state storage."""
    return msg.model_dump()


def dict_to_message(data: Dict[str, Any]) -> Message:
    """Convert dict back to Message."""
    return Message(**data)
