"""
Memory management for ReportChat agent.

Industry Standard: Conversation persistence with summarization policy.
- Store full message history in database
- Summarize older messages when context grows too large
- Efficient retrieval and update patterns
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid
import json

from app.core.logging import get_logger
from app.db.connection import get_db_session
from app.agents.report_chat.state import Message, MessageRole, ToolCall, message_to_dict, dict_to_message

logger = get_logger("agents.report_chat.memory")

# Memory policy constants
MAX_MESSAGES_IN_CONTEXT = 20  # Keep last N messages verbatim
MAX_TOKEN_ESTIMATE = 8000  # Rough token limit before summarization
SUMMARY_TRIGGER = 15  # Start summarizing after this many messages


class ChatMemoryManager:
    """
    Manages conversation memory with persistence and summarization.
    
    Memory Policy:
    1. Keep last MAX_MESSAGES_IN_CONTEXT messages verbatim
    2. Summarize older messages when total exceeds threshold
    3. Store tool call summaries for audit (not full data)
    4. Reference large artifacts by ID, don't embed
    """
    
    def __init__(self, evaluation_id: str, thread_id: str, user_id: Optional[str] = None):
        self.evaluation_id = evaluation_id
        self.thread_id = thread_id
        self.user_id = user_id
    
    def get_thread(self) -> Optional[Dict[str, Any]]:
        """Get thread from database."""
        from app.db.models import ChatThread
        
        with get_db_session() as session:
            thread = session.query(ChatThread).filter(
                ChatThread.id == self.thread_id,
                ChatThread.evaluation_id == self.evaluation_id,
            ).first()
            
            if thread:
                return thread.to_dict()
            return None
    
    def create_thread(self) -> str:
        """Create a new chat thread."""
        from app.db.models import ChatThread
        
        thread_id = self.thread_id or str(uuid.uuid4())[:8]
        
        with get_db_session() as session:
            thread = ChatThread(
                id=thread_id,
                evaluation_id=self.evaluation_id,
                user_id=self.user_id,
            )
            session.add(thread)
            session.commit()
        
        self.thread_id = thread_id
        return thread_id
    
    def get_messages(self, limit: Optional[int] = None) -> List[Message]:
        """Get messages for this thread."""
        from app.db.models import ChatMessage
        
        with get_db_session() as session:
            query = session.query(ChatMessage).filter(
                ChatMessage.thread_id == self.thread_id
            ).order_by(ChatMessage.created_at)
            
            if limit:
                query = query.limit(limit)
            
            messages = []
            for msg in query.all():
                messages.append(Message(
                    id=msg.id,
                    role=MessageRole(msg.role),
                    content=msg.content,
                    tool_calls=[ToolCall(**tc) for tc in (msg.tool_calls or [])],
                    metadata=msg.message_meta or {},
                    timestamp=msg.created_at.isoformat() if msg.created_at else datetime.utcnow().isoformat(),
                ))
            
            return messages
    
    def add_message(
        self, 
        role: MessageRole, 
        content: str,
        tool_calls: List[ToolCall] = None,
        metadata: Dict[str, Any] = None
    ) -> Message:
        """Add a message to the thread."""
        from app.db.models import ChatMessage
        
        message_id = str(uuid.uuid4())[:8]
        
        # Create Message object
        message = Message(
            id=message_id,
            role=role,
            content=content,
            tool_calls=tool_calls or [],
            metadata=metadata or {},
            timestamp=datetime.utcnow().isoformat(),
        )
        
        # Persist to database
        with get_db_session() as session:
            db_message = ChatMessage(
                id=message_id,
                thread_id=self.thread_id,
                role=role.value,
                content=content,
                tool_calls=[tc.model_dump() for tc in (tool_calls or [])],
                message_meta=metadata,
            )
            session.add(db_message)
            
            # Update thread message count
            from app.db.models import ChatThread
            thread = session.query(ChatThread).filter(
                ChatThread.id == self.thread_id
            ).first()
            if thread:
                thread.message_count = (thread.message_count or 0) + 1
                thread.updated_at = datetime.utcnow()
            
            session.commit()
        
        return message
    
    def get_context_messages(self) -> tuple:
        """
        Get messages for LLM context with memory policy applied.
        
        Returns:
            (messages, summary) - Recent messages and summary of older ones
        """
        messages = self.get_messages()
        
        if len(messages) <= MAX_MESSAGES_IN_CONTEXT:
            return messages, None
        
        # Get summary and recent messages
        summary = self._get_or_create_summary(messages[:-MAX_MESSAGES_IN_CONTEXT])
        recent_messages = messages[-MAX_MESSAGES_IN_CONTEXT:]
        
        return recent_messages, summary
    
    def _get_or_create_summary(self, old_messages: List[Message]) -> str:
        """Get existing summary or create one for old messages."""
        from app.db.models import ChatThread
        
        with get_db_session() as session:
            thread = session.query(ChatThread).filter(
                ChatThread.id == self.thread_id
            ).first()
            
            if thread and thread.summary:
                # Check if summary is still valid
                if thread.summarized_up_to >= len(old_messages):
                    return thread.summary
            
            # Generate new summary
            summary = self._summarize_messages(old_messages)
            
            # Store summary
            if thread:
                thread.summary = summary
                thread.summarized_up_to = len(old_messages)
                session.commit()
            
            return summary
    
    def _summarize_messages(self, messages: List[Message]) -> str:
        """Create a summary of messages for context compression."""
        if not messages:
            return ""
        
        # Simple extractive summary - could be enhanced with LLM
        summary_parts = ["Previous conversation summary:"]
        
        # Group by topic/intent
        topics_discussed = set()
        key_findings = []
        
        for msg in messages:
            if msg.role == MessageRole.USER:
                # Extract what user asked about
                content_lower = msg.content.lower()
                if "why" in content_lower and ("flag" in content_lower or "unsafe" in content_lower):
                    topics_discussed.add("verdict explanation")
                elif "evidence" in content_lower:
                    topics_discussed.add("evidence discussion")
                elif "stage" in content_lower or "detection" in content_lower:
                    topics_discussed.add("stage analysis")
            
            elif msg.role == MessageRole.ASSISTANT:
                # Extract key facts from assistant responses
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        if tc.status.value == "success" and tc.result:
                            if isinstance(tc.result, dict):
                                if "verdict" in tc.result:
                                    key_findings.append(f"Verdict: {tc.result['verdict']}")
                                if "score" in tc.result:
                                    key_findings.append(f"Score discussed: {tc.result.get('criterion', 'unknown')}")
        
        if topics_discussed:
            summary_parts.append(f"Topics covered: {', '.join(topics_discussed)}")
        
        if key_findings:
            summary_parts.append(f"Key points: {'; '.join(key_findings[:5])}")
        
        summary_parts.append(f"({len(messages)} earlier messages summarized)")
        
        return "\n".join(summary_parts)
    
    def get_token_estimate(self) -> int:
        """Estimate token count for current context."""
        messages = self.get_messages()
        
        total_chars = sum(len(m.content) for m in messages)
        # Rough estimate: 4 chars per token
        return total_chars // 4
    
    def clear_thread(self) -> None:
        """Clear all messages in thread (for testing)."""
        from app.db.models import ChatMessage, ChatThread
        
        with get_db_session() as session:
            session.query(ChatMessage).filter(
                ChatMessage.thread_id == self.thread_id
            ).delete()
            
            thread = session.query(ChatThread).filter(
                ChatThread.id == self.thread_id
            ).first()
            if thread:
                thread.message_count = 0
                thread.summary = None
                thread.summarized_up_to = 0
            
            session.commit()


def format_messages_for_llm(
    messages: List[Message], 
    summary: Optional[str] = None
) -> List[Dict[str, str]]:
    """
    Format messages for LLM input.
    
    Returns list of {role, content} dicts compatible with chat APIs.
    """
    formatted = []
    
    # Add summary as system context if present
    if summary:
        formatted.append({
            "role": "system",
            "content": summary
        })
    
    # Add messages
    for msg in messages:
        formatted.append({
            "role": msg.role.value,
            "content": msg.content
        })
    
    return formatted
