"""
Chat API endpoints for ReportChat agent.

Endpoints:
- POST /v1/evaluations/{id}/chat - Send message to chat
- GET /v1/evaluations/{id}/chat/{thread_id} - Get thread history
- POST /v1/evaluations/{id}/chat/start - Start new thread with initial report
"""
from typing import Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.agents.report_chat import ReportChatAgent

logger = get_logger("api.chat")

router = APIRouter(prefix="/v1/evaluations", tags=["chat"])


# =============================================================================
# Request/Response Models
# =============================================================================

class ChatRequest(BaseModel):
    """Request to send a chat message."""
    message: str = Field(..., description="User's message", min_length=1)
    thread_id: Optional[str] = Field(None, description="Thread ID (required for continued conversations)")


class ChatResponse(BaseModel):
    """Response from chat endpoint."""
    thread_id: str
    evaluation_id: str
    messages: list  # List of message dicts
    tool_trace: Optional[Dict[str, Any]] = None
    suggested_questions: Optional[list] = None


class ThreadResponse(BaseModel):
    """Response with full thread history."""
    thread_id: str
    evaluation_id: str
    messages: list
    message_count: int
    created_at: Optional[str]
    updated_at: Optional[str]


class StartThreadRequest(BaseModel):
    """Request to start a new thread."""
    thread_id: Optional[str] = Field(None, description="Optional custom thread ID")


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/{evaluation_id}/chat/start", response_model=ChatResponse)
async def start_chat_thread(
    evaluation_id: str,
    request: StartThreadRequest = None,
):
    """
    Start a new chat thread with the initial report.
    
    This creates a new thread and generates the initial assistant message
    containing the evaluation report summary.
    
    Returns:
        Chat response with initial report and suggested questions
    """
    logger.info(f"[start_chat_thread] evaluation_id={evaluation_id}")
    
    try:
        agent = ReportChatAgent(evaluation_id=evaluation_id)
        
        thread_id = request.thread_id if request else None
        result = await agent.start_thread(thread_id=thread_id)
        
        return ChatResponse(
            thread_id=result["thread_id"],
            evaluation_id=evaluation_id,
            messages=result["messages"],
            suggested_questions=result.get("suggested_questions", []),
        )
        
    except Exception as e:
        logger.error(f"[start_chat_thread] Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{evaluation_id}/chat", response_model=ChatResponse)
async def send_chat_message(
    evaluation_id: str,
    request: ChatRequest,
):
    """
    Send a message to the chat agent.
    
    Requires thread_id for continued conversations.
    Use /chat/start first to create a thread.
    
    Returns:
        Chat response with user message and assistant reply
    """
    logger.info(f"[send_chat_message] evaluation_id={evaluation_id}, thread_id={request.thread_id}")
    
    if not request.thread_id:
        raise HTTPException(
            status_code=400, 
            detail="thread_id is required. Use POST /chat/start to create a new thread first."
        )
    
    try:
        agent = ReportChatAgent(evaluation_id=evaluation_id)
        
        result = await agent.chat(
            message=request.message,
            thread_id=request.thread_id,
        )
        
        return ChatResponse(
            thread_id=result["thread_id"],
            evaluation_id=evaluation_id,
            messages=result["messages"],
            tool_trace=result.get("tool_trace"),
        )
        
    except Exception as e:
        logger.error(f"[send_chat_message] Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{evaluation_id}/chat/{thread_id}", response_model=ThreadResponse)
async def get_chat_thread(
    evaluation_id: str,
    thread_id: str,
):
    """
    Get full chat thread history.
    
    Returns all messages in the thread.
    """
    logger.info(f"[get_chat_thread] evaluation_id={evaluation_id}, thread_id={thread_id}")
    
    try:
        agent = ReportChatAgent(evaluation_id=evaluation_id)
        
        result = await agent.get_thread(thread_id=thread_id)
        
        if result.get("error"):
            raise HTTPException(status_code=404, detail=result["error"])
        
        return ThreadResponse(
            thread_id=result["thread_id"],
            evaluation_id=result["evaluation_id"],
            messages=result["messages"],
            message_count=result["message_count"],
            created_at=result.get("created_at"),
            updated_at=result.get("updated_at"),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[get_chat_thread] Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{evaluation_id}/chat/questions")
async def get_suggested_questions(
    evaluation_id: str,
):
    """
    Get suggested questions for an evaluation.
    
    Questions are contextual based on the verdict.
    """
    try:
        agent = ReportChatAgent(evaluation_id=evaluation_id)
        questions = agent.get_suggested_questions()
        
        return {
            "evaluation_id": evaluation_id,
            "questions": questions,
        }
        
    except Exception as e:
        logger.error(f"[get_suggested_questions] Failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
