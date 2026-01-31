"""
ReportChatAgent - Main agent class.

Industry Standard: Clean interface for chat interactions.
Orchestrates graph, memory, and tracing.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid

from app.core.logging import get_logger
from app.agents.report_chat.state import (
    ChatState, Message, MessageRole, ToolCall,
    create_initial_state, message_to_dict
)
from app.agents.report_chat.memory import ChatMemoryManager, format_messages_for_llm
from app.agents.report_chat.graph import get_report_chat_graph, generate_initial_report
from app.agents.report_chat.prompts import get_suggested_questions

logger = get_logger("agents.report_chat.agent")


class ReportChatAgent:
    """
    Interactive agent for discussing video evaluation results.
    
    Usage:
        agent = ReportChatAgent(evaluation_id="abc123")
        
        # Start new thread with initial report
        response = await agent.start_thread()
        
        # Continue conversation
        response = await agent.chat("Why was this flagged?", thread_id=response["thread_id"])
    """
    
    def __init__(
        self, 
        evaluation_id: str,
        user_id: Optional[str] = None,
    ):
        """
        Initialize agent for an evaluation.
        
        Args:
            evaluation_id: The evaluation to discuss
            user_id: Optional user ID for access control
        """
        self.evaluation_id = evaluation_id
        self.user_id = user_id
        self.graph = get_report_chat_graph()
    
    async def start_thread(self, thread_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Start a new chat thread with the initial report.
        
        Returns:
            {
                "thread_id": str,
                "messages": [initial_report_message],
                "suggested_questions": [str, ...]
            }
        """
        logger.info(f"[start_thread] evaluation_id={self.evaluation_id}")
        
        # Create thread ID
        thread_id = thread_id or str(uuid.uuid4())[:8]
        
        # Initialize memory manager
        memory = ChatMemoryManager(
            evaluation_id=self.evaluation_id,
            thread_id=thread_id,
            user_id=self.user_id,
        )
        
        # Create thread in database
        memory.create_thread()
        
        # Generate initial report
        initial_report = await generate_initial_report(self.evaluation_id)
        
        # Save as first assistant message
        message = memory.add_message(
            role=MessageRole.ASSISTANT,
            content=initial_report,
            metadata={"is_initial_report": True}
        )
        
        # Get suggested questions based on verdict
        from app.agents.report_chat.tools import get_evaluation
        eval_data = get_evaluation.invoke({"evaluation_id": self.evaluation_id})
        verdict = eval_data.get("verdict", "UNKNOWN")
        suggested = get_suggested_questions(verdict)
        
        return {
            "thread_id": thread_id,
            "messages": [message_to_dict(message)],
            "suggested_questions": suggested,
            "evaluation_id": self.evaluation_id,
        }
    
    async def chat(
        self, 
        message: str, 
        thread_id: str,
    ) -> Dict[str, Any]:
        """
        Process a user message and generate a response.
        
        Args:
            message: User's message
            thread_id: Thread ID for conversation continuity
            
        Returns:
            {
                "thread_id": str,
                "messages": [user_message, assistant_message],
                "tool_trace": {...},  # Debug info
            }
        """
        logger.info(f"[chat] thread={thread_id}, message={message[:50]}...")
        
        # Initialize memory manager
        memory = ChatMemoryManager(
            evaluation_id=self.evaluation_id,
            thread_id=thread_id,
            user_id=self.user_id,
        )
        
        # Save user message
        user_msg = memory.add_message(
            role=MessageRole.USER,
            content=message,
        )
        
        # Get context (recent messages + summary of older)
        context_messages, summary = memory.get_context_messages()
        
        # Create initial state for graph
        state = create_initial_state(
            evaluation_id=self.evaluation_id,
            thread_id=thread_id,
            user_message=message,
            user_id=self.user_id,
        )
        
        # Add message history to state
        state["messages"] = [message_to_dict(m) for m in context_messages]
        
        # Run the graph
        try:
            result = self.graph.invoke(state)
            
            # Extract response
            response_content = result.get("response_draft", "I couldn't generate a response.")
            tool_calls = [ToolCall(**tc) for tc in result.get("pending_tool_calls", [])]
            citations = result.get("citations", [])
            step_traces = result.get("step_traces", [])
            
        except Exception as e:
            logger.error(f"[chat] Graph execution failed: {e}")
            response_content = f"I encountered an error processing your request: {str(e)}"
            tool_calls = []
            citations = []
            step_traces = [{"error": str(e)}]
        
        # Save assistant response
        assistant_msg = memory.add_message(
            role=MessageRole.ASSISTANT,
            content=response_content,
            tool_calls=tool_calls,
            metadata={"citations": citations}
        )
        
        return {
            "thread_id": thread_id,
            "messages": [
                message_to_dict(user_msg),
                message_to_dict(assistant_msg),
            ],
            "tool_trace": {
                "steps": step_traces,
                "tools_called": len(tool_calls),
            },
            "evaluation_id": self.evaluation_id,
        }
    
    async def get_thread(self, thread_id: str) -> Dict[str, Any]:
        """
        Get full thread history.
        
        Args:
            thread_id: Thread ID
            
        Returns:
            {
                "thread_id": str,
                "evaluation_id": str,
                "messages": [Message, ...],
                "message_count": int,
            }
        """
        memory = ChatMemoryManager(
            evaluation_id=self.evaluation_id,
            thread_id=thread_id,
            user_id=self.user_id,
        )
        
        thread = memory.get_thread()
        if not thread:
            return {"error": f"Thread {thread_id} not found"}
        
        messages = memory.get_messages()
        
        return {
            "thread_id": thread_id,
            "evaluation_id": self.evaluation_id,
            "messages": [message_to_dict(m) for m in messages],
            "message_count": len(messages),
            "created_at": thread.get("created_at"),
            "updated_at": thread.get("updated_at"),
        }
    
    def get_suggested_questions(self) -> List[str]:
        """Get contextual suggested questions for this evaluation."""
        from app.agents.report_chat.tools import get_evaluation
        eval_data = get_evaluation.invoke({"evaluation_id": self.evaluation_id})
        verdict = eval_data.get("verdict", "UNKNOWN")
        return get_suggested_questions(verdict)
