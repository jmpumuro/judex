"""
LangGraph agent for ReportChat.

Industry Standard: LangGraph workflow with clear node separation.
- Intent classification for routing
- Tool execution for data fetching
- Response synthesis with citations
"""
from typing import Dict, Any, List, Optional, Literal
from datetime import datetime
import uuid
import json

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from app.core.logging import get_logger
from app.llm import get_llm
from app.agents.report_chat.state import ChatState, UserIntent, Message, MessageRole, ToolCall, ToolCallStatus
from app.agents.report_chat.tools import (
    REPORT_CHAT_TOOLS, 
    get_evaluation, 
    list_stage_runs, 
    get_stage_output,
    get_artifacts,
    get_evidence_for_criterion,
)
from app.agents.report_chat.prompts import (
    SYSTEM_PROMPT, 
    INTENT_CLASSIFICATION_PROMPT,
    RESPONSE_SYNTHESIS_PROMPT,
    INITIAL_REPORT_PROMPT,
    get_suggested_questions,
)

logger = get_logger("agents.report_chat.graph")


# =============================================================================
# Graph Nodes
# =============================================================================

def classify_intent(state: ChatState) -> ChatState:
    """
    Node 1: Classify user intent to determine tool plan.
    
    Uses LLM to understand what the user is asking for.
    """
    logger.info(f"[classify_intent] Message: {state.get('current_message', '')[:50]}...")
    
    message = state.get("current_message", "")
    
    # Quick classification for common patterns
    message_lower = message.lower()
    
    # Pattern matching for efficiency (avoid LLM call for obvious cases)
    if any(w in message_lower for w in ["why", "reason", "cause", "explain"]) and \
       any(w in message_lower for w in ["flag", "unsafe", "verdict", "fail"]):
        intent = UserIntent.EXPLAIN_VERDICT.value
    elif any(w in message_lower for w in ["evidence", "proof", "show me", "what was detected"]):
        intent = UserIntent.SHOW_EVIDENCE.value
    elif any(w in message_lower for w in ["stage", "ocr", "transcript", "yolo", "violence", "whisper"]):
        intent = UserIntent.STAGE_DETAILS.value
    elif any(w in message_lower for w in ["video", "artifact", "thumbnail", "download"]):
        intent = UserIntent.ARTIFACT_REQUEST.value
    elif any(w in message_lower for w in ["hello", "hi", "thanks", "thank you", "bye"]):
        intent = UserIntent.GREETING.value
    else:
        intent = UserIntent.GENERAL_QUESTION.value
    
    # Determine tool plan based on intent
    tool_plan = _get_tool_plan(intent, message_lower)
    
    state["intent"] = intent
    state["intent_confidence"] = 0.9  # High confidence for pattern matching
    state["tool_plan"] = tool_plan
    
    # Add trace
    state["step_traces"] = state.get("step_traces", []) + [{
        "node": "classify_intent",
        "intent": intent,
        "tool_plan": tool_plan,
        "timestamp": datetime.utcnow().isoformat(),
    }]
    
    return state


def _get_tool_plan(intent: str, message_lower: str) -> List[str]:
    """Determine which tools to call based on intent."""
    
    if intent == UserIntent.EXPLAIN_VERDICT.value:
        # Need evaluation summary and potentially stage outputs
        plan = ["get_evaluation", "list_stage_runs"]
        # Add specific evidence tools if criterion mentioned
        for criterion in ["violence", "profanity", "drugs", "sexual", "hate", "weapons"]:
            if criterion in message_lower:
                plan.append(f"get_evidence_for_criterion:{criterion}")
                break
        return plan
    
    elif intent == UserIntent.SHOW_EVIDENCE.value:
        return ["get_evaluation", "list_stage_runs"]
    
    elif intent == UserIntent.STAGE_DETAILS.value:
        # Determine which stage
        stages = ["ocr", "yolo26", "yoloworld", "violence", "whisper", "text_moderation", "policy_fusion"]
        for stage in stages:
            if stage in message_lower or stage.replace("_", " ") in message_lower:
                return [f"get_stage_output:{stage}"]
        
        # Check for friendly names
        stage_aliases = {
            "transcript": "whisper",
            "speech": "whisper", 
            "audio": "whisper",
            "text": "ocr",
            "object": "yolo26",
            "scene": "yoloworld",
            "moderation": "text_moderation",
            "fusion": "policy_fusion",
            "score": "policy_fusion",
        }
        for alias, stage in stage_aliases.items():
            if alias in message_lower:
                return [f"get_stage_output:{stage}"]
        
        return ["list_stage_runs"]
    
    elif intent == UserIntent.ARTIFACT_REQUEST.value:
        return ["get_artifacts"]
    
    elif intent == UserIntent.GREETING.value:
        return []  # No tools needed
    
    else:
        # General question - fetch evaluation overview
        return ["get_evaluation"]


def gather_context(state: ChatState) -> ChatState:
    """
    Node 2: Execute tools to gather necessary context.
    
    Fetches data from internal APIs via typed tools.
    """
    logger.info(f"[gather_context] Tool plan: {state.get('tool_plan', [])}")
    
    tool_plan = state.get("tool_plan", [])
    evaluation_id = state.get("evaluation_id")
    tool_results = {}
    tool_calls = []
    
    for tool_spec in tool_plan:
        # Parse tool spec (may include args like "get_stage_output:ocr")
        if ":" in tool_spec:
            tool_name, tool_arg = tool_spec.split(":", 1)
        else:
            tool_name = tool_spec
            tool_arg = None
        
        tool_call_id = str(uuid.uuid4())[:8]
        start_time = datetime.utcnow()
        
        try:
            # Execute tool
            result = _execute_tool(tool_name, evaluation_id, tool_arg)
            
            latency_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            tool_calls.append(ToolCall(
                id=tool_call_id,
                tool_name=tool_name,
                arguments={"evaluation_id": evaluation_id, "arg": tool_arg},
                result=result,
                status=ToolCallStatus.SUCCESS,
                latency_ms=latency_ms,
            ))
            
            tool_results[tool_name] = result
            
            logger.info(f"[gather_context] {tool_name} completed in {latency_ms}ms")
            
        except Exception as e:
            logger.error(f"[gather_context] {tool_name} failed: {e}")
            tool_calls.append(ToolCall(
                id=tool_call_id,
                tool_name=tool_name,
                arguments={"evaluation_id": evaluation_id, "arg": tool_arg},
                status=ToolCallStatus.ERROR,
                error=str(e),
            ))
            tool_results[tool_name] = {"error": str(e)}
    
    state["tool_results"] = tool_results
    state["pending_tool_calls"] = [tc.model_dump() for tc in tool_calls]
    
    # Cache evaluation context if fetched
    if "get_evaluation" in tool_results:
        state["evaluation_context"] = tool_results["get_evaluation"]
    
    # Add trace
    state["step_traces"] = state.get("step_traces", []) + [{
        "node": "gather_context",
        "tools_called": len(tool_calls),
        "tools_succeeded": len([tc for tc in tool_calls if tc.status == ToolCallStatus.SUCCESS]),
        "timestamp": datetime.utcnow().isoformat(),
    }]
    
    return state


def _execute_tool(tool_name: str, evaluation_id: str, tool_arg: Optional[str]) -> Dict[str, Any]:
    """Execute a specific tool."""
    
    if tool_name == "get_evaluation":
        return get_evaluation.invoke({"evaluation_id": evaluation_id})
    
    elif tool_name == "list_stage_runs":
        return list_stage_runs.invoke({"evaluation_id": evaluation_id})
    
    elif tool_name == "get_stage_output":
        return get_stage_output.invoke({
            "evaluation_id": evaluation_id,
            "stage_id": tool_arg or "policy_fusion"
        })
    
    elif tool_name == "get_artifacts":
        return get_artifacts.invoke({"evaluation_id": evaluation_id})
    
    elif tool_name == "get_evidence_for_criterion":
        from app.agents.report_chat.tools import get_evidence_for_criterion
        return get_evidence_for_criterion.invoke({
            "evaluation_id": evaluation_id,
            "criterion": tool_arg or "violence"
        })
    
    elif tool_name == "get_criteria_details":
        from app.agents.report_chat.tools import get_criteria_details
        return get_criteria_details.invoke({"evaluation_id": evaluation_id})
    
    elif tool_name == "search_text":
        from app.agents.report_chat.tools import search_text
        return search_text.invoke({
            "evaluation_id": evaluation_id,
            "query": tool_arg or ""
        })
    
    else:
        return {"error": f"Unknown tool: {tool_name}"}


def generate_response(state: ChatState) -> ChatState:
    """
    Node 3: Generate response using LLM with tool results.
    
    Synthesizes tool results into a helpful answer.
    """
    logger.info(f"[generate_response] Intent: {state.get('intent')}")
    
    intent = state.get("intent", "")
    tool_results = state.get("tool_results", {})
    current_message = state.get("current_message", "")
    messages = state.get("messages", [])
    
    # Handle greeting without LLM
    if intent == UserIntent.GREETING.value:
        eval_context = state.get("evaluation_context", {})
        verdict = eval_context.get("verdict", "unknown")
        
        response = f"Hello! I'm here to help you understand this video evaluation. "
        response += f"The current verdict is **{verdict}**. "
        response += "Feel free to ask me anything about the analysis results."
        
        state["response_draft"] = response
        return state
    
    # Format tool results for LLM
    tool_results_str = json.dumps(tool_results, indent=2, default=str)
    
    # Format conversation history
    context_str = ""
    if messages:
        recent = messages[-4:]  # Last 2 exchanges
        for msg in recent:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:200]
            context_str += f"{role}: {content}\n"
    
    # Build prompt
    prompt = RESPONSE_SYNTHESIS_PROMPT.format(
        question=current_message,
        tool_results=tool_results_str[:4000],  # Limit size
        context=context_str or "No previous context",
    )
    
    try:
        # Get LLM (with fallback)
        llm = get_llm(fallback=True)
        
        if llm:
            response = llm.generate(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                max_tokens=1500,
                temperature=0.3,
            )
            state["response_draft"] = response.content
        else:
            # Fallback to template response
            state["response_draft"] = _generate_template_response(intent, tool_results)
            
    except Exception as e:
        logger.error(f"[generate_response] LLM failed: {e}")
        state["response_draft"] = _generate_template_response(intent, tool_results)
    
    # Extract citations from tool results
    citations = []
    for tool_name, result in tool_results.items():
        if isinstance(result, dict) and not result.get("error"):
            citations.append({
                "source": tool_name,
                "type": "tool_result",
            })
    state["citations"] = citations
    
    # Add trace
    state["step_traces"] = state.get("step_traces", []) + [{
        "node": "generate_response",
        "response_length": len(state.get("response_draft", "")),
        "citations_count": len(citations),
        "timestamp": datetime.utcnow().isoformat(),
    }]
    
    return state


def _generate_template_response(intent: str, tool_results: Dict[str, Any]) -> str:
    """Generate a template response when LLM is unavailable."""
    
    eval_data = tool_results.get("get_evaluation", {})
    stages_data = tool_results.get("list_stage_runs", {})
    
    if eval_data.get("error"):
        return f"I couldn't fetch the evaluation data. Error: {eval_data['error']}"
    
    verdict = eval_data.get("verdict", "unknown")
    confidence = eval_data.get("confidence")
    scores = eval_data.get("criteria_scores", {})
    violations = eval_data.get("violations", [])
    
    response_parts = []
    
    if intent == UserIntent.EXPLAIN_VERDICT.value:
        response_parts.append(f"## Verdict Explanation\n")
        response_parts.append(f"The evaluation resulted in **{verdict}**")
        if confidence:
            response_parts.append(f" with {confidence:.0%} confidence")
        response_parts.append(".\n\n")
        
        if scores:
            response_parts.append("**Criterion Scores:**\n")
            # Handle both flat scores and nested score dicts
            for criterion, score_data in sorted(scores.items(), key=lambda x: x[1].get('score', x[1]) if isinstance(x[1], dict) else x[1], reverse=True):
                if isinstance(score_data, dict):
                    score_val = score_data.get('score', 0)
                    severity = score_data.get('severity', '')
                    response_parts.append(f"- {criterion}: {score_val:.0%}{f' ({severity})' if severity else ''}\n")
                elif isinstance(score_data, (int, float)):
                    response_parts.append(f"- {criterion}: {score_data:.0%}\n")
        
        if violations:
            response_parts.append(f"\n**Violations ({len(violations)}):**\n")
            for v in violations[:5]:
                response_parts.append(f"- {v.get('criterion', 'unknown')}: {v.get('severity', 'unknown')} severity\n")
    
    elif intent == UserIntent.STAGE_DETAILS.value:
        stage_output = tool_results.get("get_stage_output", {})
        if stage_output and not stage_output.get("error"):
            response_parts.append(f"## {stage_output.get('stage_name', 'Stage')} Results\n\n")
            response_parts.append(f"{stage_output.get('summary', 'No summary available')}\n\n")
            findings = stage_output.get("key_findings", [])
            if findings:
                response_parts.append("**Key Findings:**\n")
                for f in findings:
                    response_parts.append(f"- {f}\n")
        else:
            response_parts.append("Stage output not available.")
    
    else:
        response_parts.append(f"The evaluation verdict is **{verdict}**. ")
        if stages_data:
            completed = stages_data.get("completed", 0)
            total = stages_data.get("total_stages", 0)
            response_parts.append(f"{completed}/{total} stages completed successfully.")
    
    return "".join(response_parts)


# =============================================================================
# Router
# =============================================================================

def should_gather_context(state: ChatState) -> Literal["gather", "respond"]:
    """Decide if we need to gather context or can respond directly."""
    tool_plan = state.get("tool_plan", [])
    
    if not tool_plan:
        return "respond"  # No tools needed (e.g., greeting)
    
    return "gather"


# =============================================================================
# Graph Builder
# =============================================================================

def build_report_chat_graph() -> StateGraph:
    """
    Build the LangGraph workflow for ReportChat agent.
    
    Flow:
    1. classify_intent → Understand what user wants
    2. gather_context (conditional) → Fetch data via tools
    3. generate_response → Create answer with citations
    """
    
    workflow = StateGraph(ChatState)
    
    # Add nodes
    workflow.add_node("classify_intent", classify_intent)
    workflow.add_node("gather_context", gather_context)
    workflow.add_node("generate_response", generate_response)
    
    # Set entry point
    workflow.set_entry_point("classify_intent")
    
    # Add edges with conditional routing
    workflow.add_conditional_edges(
        "classify_intent",
        should_gather_context,
        {
            "gather": "gather_context",
            "respond": "generate_response",
        }
    )
    
    workflow.add_edge("gather_context", "generate_response")
    workflow.add_edge("generate_response", END)
    
    return workflow.compile()


# =============================================================================
# Initial Report Generation
# =============================================================================

async def generate_initial_report(evaluation_id: str) -> str:
    """
    Generate the initial report message when a chat thread is created.
    
    This reuses the existing report or generates a summary.
    """
    logger.info(f"[generate_initial_report] evaluation_id={evaluation_id}")
    
    # Fetch evaluation data
    eval_data = get_evaluation.invoke({"evaluation_id": evaluation_id})
    stages_data = list_stage_runs.invoke({"evaluation_id": evaluation_id})
    
    if eval_data.get("error"):
        return f"Unable to load evaluation data: {eval_data['error']}"
    
    # Check if we have a pre-generated report
    try:
        report_output = get_stage_output.invoke({
            "evaluation_id": evaluation_id,
            "stage_id": "report"
        })
        
        if report_output and not report_output.get("error"):
            data = report_output.get("data", {})
            if data.get("report_preview") or data.get("report"):
                return data.get("report_preview") or data.get("report")
    except:
        pass
    
    # Generate summary report
    verdict = eval_data.get("verdict", "UNKNOWN")
    confidence = eval_data.get("confidence")
    scores = eval_data.get("criteria_scores", {})
    violations = eval_data.get("violations", [])
    
    report_parts = [
        f"# Video Content Safety Report\n\n",
        f"## Summary\n",
        f"**Verdict:** {verdict}",
    ]
    
    if confidence:
        report_parts.append(f" ({confidence:.0%} confidence)")
    report_parts.append("\n\n")
    
    # Add scores
    if scores:
        report_parts.append("## Criterion Scores\n")
        report_parts.append("| Criterion | Score | Severity |\n|-----------|-------|----------|\n")
        # Handle both flat scores and nested score dicts
        for criterion, score_data in sorted(scores.items(), key=lambda x: x[1].get('score', x[1]) if isinstance(x[1], dict) else x[1], reverse=True):
            if isinstance(score_data, dict):
                score_val = score_data.get('score', 0)
                severity = score_data.get('severity', '-')
                score_pct = f"{score_val:.0%}" if isinstance(score_val, (int, float)) else str(score_val)
                report_parts.append(f"| {criterion} | {score_pct} | {severity} |\n")
            elif isinstance(score_data, (int, float)):
                score_pct = f"{score_data:.0%}"
                report_parts.append(f"| {criterion} | {score_pct} | - |\n")
        report_parts.append("\n")
    
    # Add violations
    if violations:
        report_parts.append(f"## Violations ({len(violations)})\n")
        for v in violations[:5]:
            report_parts.append(f"- **{v.get('criterion', 'unknown')}**: {v.get('severity', 'unknown')} severity\n")
        report_parts.append("\n")
    
    # Add stage summary
    if stages_data and not stages_data.get("error"):
        completed = stages_data.get("completed", 0)
        total = stages_data.get("total_stages", 0)
        report_parts.append(f"## Analysis Summary\n")
        report_parts.append(f"- **Stages completed:** {completed}/{total}\n")
        
        stages = stages_data.get("stages", [])
        key_stages = [s for s in stages if s.get("status") == "completed" and s.get("output_summary")]
        for stage in key_stages[:5]:
            report_parts.append(f"- **{stage['stage_name']}:** {stage['output_summary']}\n")
    
    report_parts.append("\n---\n")
    report_parts.append("*Ask me any questions about this evaluation!*")
    
    return "".join(report_parts)


# Create singleton graph instance
_graph = None

def get_report_chat_graph() -> StateGraph:
    """Get or create the ReportChat graph."""
    global _graph
    if _graph is None:
        _graph = build_report_chat_graph()
    return _graph
