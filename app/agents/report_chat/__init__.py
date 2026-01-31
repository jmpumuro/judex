"""
ReportChat Agent - LangGraph-based conversational agent for evaluation analysis.

Industry Standard Architecture (LangSmith-style):
- Typed state model for conversation tracking
- Tool layer wrapping internal APIs (no raw HTTP)
- LangGraph workflow with intent routing
- Conversation persistence with memory management
- Tracing for observability

Usage:
    from app.agents.report_chat import ReportChatAgent
    
    agent = ReportChatAgent(evaluation_id="abc123")
    response = await agent.chat("Why was this flagged as unsafe?")
"""
from app.agents.report_chat.agent import ReportChatAgent
from app.agents.report_chat.state import ChatState, Message, ToolCall

__all__ = [
    "ReportChatAgent",
    "ChatState",
    "Message", 
    "ToolCall",
]
