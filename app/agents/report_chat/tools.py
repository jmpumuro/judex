"""
Tool layer for ReportChat agent.

Industry Standard: Typed tool wrappers for internal APIs.
- Each tool has validated inputs/outputs
- Tools return structured data, not raw responses
- Error handling returns "not available" instead of raising
- No secrets or sensitive data in tool outputs

Design: Few but powerful tools > many narrow ones
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from langchain_core.tools import tool

from app.core.logging import get_logger
from app.db.connection import get_db_session
from app.db.models import (
    Evaluation, EvaluationItem, EvaluationResult, EvaluationEvidence,
    Criteria, EvaluationStatus as DBEvaluationStatus
)

logger = get_logger("agents.report_chat.tools")


# =============================================================================
# Tool Input/Output Models
# =============================================================================

class EvaluationSummary(BaseModel):
    """Summary of an evaluation."""
    id: str
    status: str
    verdict: Optional[str] = None
    confidence: Optional[float] = None
    criteria_id: Optional[str] = None
    criteria_name: Optional[str] = None
    items_total: int = 0
    items_completed: int = 0
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: Optional[float] = None
    criteria_scores: Dict[str, Any] = Field(default_factory=dict)  # Can be float or nested dict
    violations: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None


class StageRunInfo(BaseModel):
    """Information about a stage execution."""
    stage_id: str
    stage_name: str
    status: str  # completed, skipped, failed, pending
    duration_ms: Optional[int]
    skip_reason: Optional[str]
    error: Optional[str]
    output_summary: Optional[str]  # Brief description of what stage produced


class StageOutput(BaseModel):
    """Detailed output from a specific stage."""
    stage_id: str
    stage_name: str
    status: str
    data: Dict[str, Any]  # Full stage output
    summary: str  # Human-readable summary
    key_findings: List[str] = Field(default_factory=list)


class ArtifactInfo(BaseModel):
    """Information about an artifact."""
    artifact_type: str  # uploaded_video, labeled_video, thumbnail, transcript
    available: bool
    url: Optional[str]
    path: Optional[str]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TextSearchResult(BaseModel):
    """Result of searching transcript/OCR text."""
    matches: List[Dict[str, Any]]
    total_matches: int
    search_query: str
    sources: List[str]  # transcript, ocr


# =============================================================================
# Tool Implementations
# =============================================================================

@tool
def get_evaluation(evaluation_id: str) -> Dict[str, Any]:
    """
    Get evaluation summary including verdict, confidence, criteria scores, and violations.
    
    Use this to understand what the evaluation concluded and why.
    
    Args:
        evaluation_id: The evaluation ID to fetch
        
    Returns:
        Evaluation summary with verdict, scores, and violations
    """
    try:
        with get_db_session() as session:
            evaluation = session.query(Evaluation).filter(
                Evaluation.id == evaluation_id
            ).first()
            
            if not evaluation:
                return {"error": f"Evaluation {evaluation_id} not found"}
            
            # Get the first item's result for detailed scores
            item = evaluation.items[0] if evaluation.items else None
            result = None
            if item:
                result = session.query(EvaluationResult).filter(
                    EvaluationResult.item_id == item.id
                ).first()
            
            # Get criteria name if available
            criteria_name = None
            if evaluation.criteria_id:
                criteria = session.query(Criteria).filter(
                    Criteria.id == evaluation.criteria_id
                ).first()
                if criteria:
                    criteria_name = criteria.name
            
            # Process criteria scores - handle both flat floats and nested dicts
            raw_scores = result.criteria_scores or {} if result else {}
            processed_scores = {}
            
            # First try criteria_scores
            for key, val in raw_scores.items():
                if isinstance(val, dict):
                    # Extract score from nested dict
                    processed_scores[key] = {
                        "score": val.get("score", 0),
                        "severity": val.get("severity", "unknown"),
                        "verdict": val.get("verdict", "unknown"),
                    }
                else:
                    # Flat float value
                    processed_scores[key] = {"score": float(val) if val else 0}
            
            # If criteria_scores is empty, extract from violations
            if not processed_scores and result and result.violations:
                for v in result.violations:
                    criterion = v.get("criterion", "unknown")
                    processed_scores[criterion] = {
                        "score": v.get("score", 0),
                        "severity": v.get("severity", "unknown"),
                        "label": v.get("label", criterion),
                    }
            
            summary = EvaluationSummary(
                id=evaluation.id,
                status=evaluation.status.value if evaluation.status else "unknown",
                verdict=evaluation.overall_verdict.value if evaluation.overall_verdict else None,
                confidence=result.confidence if result else None,
                criteria_id=evaluation.criteria_id,
                criteria_name=criteria_name,
                items_total=evaluation.items_total or 0,
                items_completed=evaluation.items_completed or 0,
                created_at=evaluation.created_at.isoformat() if evaluation.created_at else None,
                completed_at=evaluation.completed_at.isoformat() if evaluation.completed_at else None,
                duration_seconds=(
                    (evaluation.completed_at - evaluation.started_at).total_seconds()
                    if evaluation.completed_at and evaluation.started_at else None
                ),
                criteria_scores=processed_scores,
                violations=result.violations or [] if result else [],
            )
            
            return summary.model_dump()
            
    except Exception as e:
        logger.error(f"Error fetching evaluation {evaluation_id}: {e}")
        return {"error": f"Failed to fetch evaluation: {str(e)}"}


@tool
def list_stage_runs(evaluation_id: str) -> Dict[str, Any]:
    """
    List all stages that ran for this evaluation with their status, timing, and outcomes.
    
    Use this to understand which stages contributed to the analysis and if any were skipped or failed.
    
    Args:
        evaluation_id: The evaluation ID
        
    Returns:
        List of stage runs with status, timing, and skip/fail reasons
    """
    try:
        with get_db_session() as session:
            evaluation = session.query(Evaluation).filter(
                Evaluation.id == evaluation_id
            ).first()
            
            if not evaluation:
                return {"error": f"Evaluation {evaluation_id} not found"}
            
            item = evaluation.items[0] if evaluation.items else None
            if not item:
                return {"error": "No items in evaluation"}
            
            # Get stage outputs from the item
            stage_outputs = item.stage_outputs or {}
            
            # Check if evaluation completed successfully (stages ran but weren't logged individually)
            eval_completed = evaluation.status and evaluation.status.value == "completed"
            has_result = item.status and item.status.value == "completed"
            
            # Define expected stages and their display names
            stage_names = {
                "ingest": "Video Upload & Normalization",
                "segment": "Frame Extraction & Segmentation",
                "yolo26": "Object Detection (YOLO26)",
                "yoloworld": "Scene Analysis (YOLO-World)",
                "window_mining": "Candidate Window Mining",
                "violence": "Violence Detection (X-CLIP)",
                "videomae_violence": "VideoMAE Action Violence",
                "pose_heuristics": "Pose Interaction Heuristics",
                "nsfw_detection": "NSFW Visual Detection",
                "whisper": "Speech Transcription (Whisper)",
                "ocr": "Text Recognition (OCR)",
                "text_moderation": "Text Content Moderation",
                "policy_fusion": "Policy Scoring & Fusion",
                "report": "Report Generation",
            }
            
            stages = []
            for stage_id, display_name in stage_names.items():
                output = stage_outputs.get(stage_id, {})
                
                # Determine status
                if output:
                    if output.get("status") == "skipped":
                        status = "skipped"
                    elif output.get("error"):
                        status = "failed"
                    else:
                        status = "completed"
                elif eval_completed and has_result:
                    # If evaluation completed but no stage_outputs, infer stages ran
                    status = "completed (inferred)"
                else:
                    status = "not_run"
                
                stages.append(StageRunInfo(
                    stage_id=stage_id,
                    stage_name=display_name,
                    status=status,
                    duration_ms=output.get("duration_ms"),
                    skip_reason=output.get("skip_reason"),
                    error=output.get("error"),
                    output_summary=_summarize_stage_output(stage_id, output) if output else ("Completed" if eval_completed else None),
                ).model_dump())
            
            return {
                "evaluation_id": evaluation_id,
                "stages": stages,
                "total_stages": len(stages),
                "completed": len([s for s in stages if "completed" in s["status"]]),
                "skipped": len([s for s in stages if s["status"] == "skipped"]),
                "failed": len([s for s in stages if s["status"] == "failed"]),
                "evaluation_status": evaluation.status.value if evaluation.status else "unknown",
            }
            
    except Exception as e:
        logger.error(f"Error listing stages for {evaluation_id}: {e}")
        return {"error": f"Failed to list stages: {str(e)}"}


@tool
def get_stage_output(evaluation_id: str, stage_id: str) -> Dict[str, Any]:
    """
    Get detailed output from a specific analysis stage.
    
    Use this when you need specifics about what a stage detected or produced.
    Available stages: ingest, segment, yolo26, yoloworld, violence, whisper, ocr, text_moderation, policy_fusion, report
    
    Args:
        evaluation_id: The evaluation ID
        stage_id: The stage to fetch (e.g., 'yolo26', 'violence', 'ocr')
        
    Returns:
        Detailed stage output with data and human-readable summary
    """
    try:
        with get_db_session() as session:
            evaluation = session.query(Evaluation).filter(
                Evaluation.id == evaluation_id
            ).first()
            
            if not evaluation:
                return {"error": f"Evaluation {evaluation_id} not found"}
            
            item = evaluation.items[0] if evaluation.items else None
            if not item:
                return {"error": "No items in evaluation"}
            
            stage_outputs = item.stage_outputs or {}
            output = stage_outputs.get(stage_id)
            
            if not output:
                return {"error": f"Stage '{stage_id}' output not found"}
            
            # Generate human-readable summary and key findings
            summary, findings = _analyze_stage_output(stage_id, output)
            
            stage_names = {
                "ingest": "Video Upload & Normalization",
                "segment": "Frame Extraction",
                "yolo26": "Object Detection (YOLO26)",
                "yoloworld": "Scene Analysis (YOLO-World)",
                "window_mining": "Candidate Window Mining",
                "violence": "Violence Detection (X-CLIP)",
                "videomae_violence": "VideoMAE Action Violence",
                "pose_heuristics": "Pose Interaction Heuristics",
                "nsfw_detection": "NSFW Visual Detection",
                "whisper": "Speech Transcription",
                "ocr": "Text Recognition (OCR)",
                "text_moderation": "Text Moderation",
                "policy_fusion": "Policy Fusion",
                "report": "Report Generation",
            }
            
            return StageOutput(
                stage_id=stage_id,
                stage_name=stage_names.get(stage_id, stage_id),
                status=output.get("status", "completed"),
                data=output,
                summary=summary,
                key_findings=findings,
            ).model_dump()
            
    except Exception as e:
        logger.error(f"Error fetching stage {stage_id} for {evaluation_id}: {e}")
        return {"error": f"Failed to fetch stage output: {str(e)}"}


@tool
def get_artifacts(evaluation_id: str) -> Dict[str, Any]:
    """
    Get available artifacts for this evaluation (videos, transcripts, thumbnails).
    
    Use this to provide links to evidence the user can view.
    
    Args:
        evaluation_id: The evaluation ID
        
    Returns:
        List of available artifacts with URLs/paths
    """
    try:
        with get_db_session() as session:
            evaluation = session.query(Evaluation).filter(
                Evaluation.id == evaluation_id
            ).first()
            
            if not evaluation:
                return {"error": f"Evaluation {evaluation_id} not found"}
            
            item = evaluation.items[0] if evaluation.items else None
            if not item:
                return {"error": "No items in evaluation"}
            
            artifacts = []
            
            # Uploaded video
            if item.uploaded_video_path:
                artifacts.append(ArtifactInfo(
                    artifact_type="uploaded_video",
                    available=True,
                    path=item.uploaded_video_path,
                    url=f"/v1/evaluations/{evaluation_id}/artifacts/uploaded_video?item_id={item.id}",
                    metadata={"duration": item.duration, "fps": item.fps}
                ).model_dump())
            
            # Labeled video
            if item.labeled_video_path:
                artifacts.append(ArtifactInfo(
                    artifact_type="labeled_video",
                    available=True,
                    path=item.labeled_video_path,
                    url=f"/v1/evaluations/{evaluation_id}/artifacts/labeled_video?item_id={item.id}",
                    metadata={"has_detections": True}
                ).model_dump())
            
            # Thumbnail
            if item.thumbnail_path:
                artifacts.append(ArtifactInfo(
                    artifact_type="thumbnail",
                    available=True,
                    path=item.thumbnail_path,
                    url=f"/v1/evaluations/{evaluation_id}/artifacts/thumbnail?item_id={item.id}",
                ).model_dump())
            
            # Transcript (from stage outputs)
            stage_outputs = item.stage_outputs or {}
            whisper_output = stage_outputs.get("whisper", {})
            if whisper_output.get("full_text") or whisper_output.get("transcript"):
                artifacts.append(ArtifactInfo(
                    artifact_type="transcript",
                    available=True,
                    metadata={
                        "language": whisper_output.get("language"),
                        "chunks": whisper_output.get("chunks_count", 0),
                    }
                ).model_dump())
            
            return {
                "evaluation_id": evaluation_id,
                "item_id": item.id,
                "artifacts": artifacts,
                "total": len(artifacts),
            }
            
    except Exception as e:
        logger.error(f"Error fetching artifacts for {evaluation_id}: {e}")
        return {"error": f"Failed to fetch artifacts: {str(e)}"}


@tool
def get_criteria_details(evaluation_id: str) -> Dict[str, Any]:
    """
    Get details about the criteria/policy used for this evaluation.
    
    Use this to explain what rules and thresholds were applied.
    
    Args:
        evaluation_id: The evaluation ID
        
    Returns:
        Criteria configuration including thresholds and weights
    """
    try:
        with get_db_session() as session:
            evaluation = session.query(Evaluation).filter(
                Evaluation.id == evaluation_id
            ).first()
            
            if not evaluation:
                return {"error": f"Evaluation {evaluation_id} not found"}
            
            # Get criteria from snapshot or database
            if evaluation.criteria_snapshot:
                return {
                    "source": "snapshot",
                    "criteria": evaluation.criteria_snapshot
                }
            
            if evaluation.criteria_id:
                criteria = session.query(Criteria).filter(
                    Criteria.id == evaluation.criteria_id
                ).first()
                
                if criteria:
                    return {
                        "source": "database",
                        "criteria_id": criteria.id,
                        "name": criteria.name,
                        "description": criteria.description,
                        "config": criteria.config_data,
                    }
            
            return {"error": "No criteria information available for this evaluation"}
            
    except Exception as e:
        logger.error(f"Error fetching criteria for {evaluation_id}: {e}")
        return {"error": f"Failed to fetch criteria: {str(e)}"}


@tool
def search_text(evaluation_id: str, query: str) -> Dict[str, Any]:
    """
    Search transcript and OCR text for specific words or phrases.
    
    Use this when the user asks about specific spoken words or on-screen text.
    
    Args:
        evaluation_id: The evaluation ID
        query: Text to search for (case-insensitive)
        
    Returns:
        Matches from transcript and OCR with context
    """
    try:
        with get_db_session() as session:
            evaluation = session.query(Evaluation).filter(
                Evaluation.id == evaluation_id
            ).first()
            
            if not evaluation:
                return {"error": f"Evaluation {evaluation_id} not found"}
            
            item = evaluation.items[0] if evaluation.items else None
            if not item:
                return {"error": "No items in evaluation"}
            
            stage_outputs = item.stage_outputs or {}
            matches = []
            sources = []
            query_lower = query.lower()
            
            # Search transcript
            whisper_output = stage_outputs.get("whisper", {})
            transcript_text = whisper_output.get("full_text", "")
            if query_lower in transcript_text.lower():
                sources.append("transcript")
                # Find context around match
                idx = transcript_text.lower().find(query_lower)
                start = max(0, idx - 50)
                end = min(len(transcript_text), idx + len(query) + 50)
                matches.append({
                    "source": "transcript",
                    "text": transcript_text[start:end],
                    "position": idx,
                    "context": f"...{transcript_text[start:end]}..."
                })
            
            # Search OCR
            ocr_output = stage_outputs.get("ocr", {})
            ocr_texts = ocr_output.get("texts", [])
            for i, text in enumerate(ocr_texts):
                if isinstance(text, str) and query_lower in text.lower():
                    sources.append("ocr")
                    matches.append({
                        "source": "ocr",
                        "text": text,
                        "frame_index": i,
                    })
            
            return TextSearchResult(
                matches=matches,
                total_matches=len(matches),
                search_query=query,
                sources=list(set(sources)),
            ).model_dump()
            
    except Exception as e:
        logger.error(f"Error searching text for {evaluation_id}: {e}")
        return {"error": f"Failed to search text: {str(e)}"}


@tool  
def get_evidence_for_criterion(evaluation_id: str, criterion: str) -> Dict[str, Any]:
    """
    Get specific evidence that contributed to a criterion score.
    
    Use this when asked why a specific criterion (violence, profanity, drugs, etc.) scored high.
    
    Args:
        evaluation_id: The evaluation ID
        criterion: The criterion name (e.g., 'violence', 'profanity', 'drugs', 'sexual', 'hate')
        
    Returns:
        Evidence from relevant stages that contributed to this criterion
    """
    try:
        with get_db_session() as session:
            evaluation = session.query(Evaluation).filter(
                Evaluation.id == evaluation_id
            ).first()
            
            if not evaluation:
                return {"error": f"Evaluation {evaluation_id} not found"}
            
            item = evaluation.items[0] if evaluation.items else None
            if not item:
                return {"error": "No items in evaluation"}
            
            # Get the result for score info
            result = session.query(EvaluationResult).filter(
                EvaluationResult.item_id == item.id
            ).first()
            
            criterion_score = None
            if result and result.criteria_scores:
                criterion_score = result.criteria_scores.get(criterion)
            
            stage_outputs = item.stage_outputs or {}
            evidence = {
                "criterion": criterion,
                "score": criterion_score,
                "contributing_evidence": []
            }
            
            # Map criteria to relevant stages
            criterion_stages = {
                "violence": ["violence", "yolo26", "yoloworld"],
                "profanity": ["whisper", "text_moderation"],
                "drugs": ["yolo26", "yoloworld", "ocr", "text_moderation"],
                "sexual": ["yolo26", "yoloworld", "text_moderation"],
                "hate": ["whisper", "ocr", "text_moderation"],
                "weapons": ["yolo26", "yoloworld"],
            }
            
            relevant_stages = criterion_stages.get(criterion.lower(), ["policy_fusion"])
            
            for stage_id in relevant_stages:
                output = stage_outputs.get(stage_id, {})
                if output:
                    summary, findings = _analyze_stage_output(stage_id, output)
                    if findings:
                        evidence["contributing_evidence"].append({
                            "stage": stage_id,
                            "summary": summary,
                            "findings": findings,
                        })
            
            return evidence
            
    except Exception as e:
        logger.error(f"Error fetching evidence for criterion {criterion}: {e}")
        return {"error": f"Failed to fetch evidence: {str(e)}"}


# =============================================================================
# Helper Functions
# =============================================================================

def _summarize_stage_output(stage_id: str, output: Dict[str, Any]) -> str:
    """Generate a brief summary of stage output."""
    if not output:
        return "No output"
    
    if output.get("status") == "skipped":
        return f"Skipped: {output.get('skip_reason', 'Stage disabled')}"
    
    summaries = {
        "ingest": lambda o: f"Video: {o.get('duration', 0):.1f}s, {o.get('width', 0)}x{o.get('height', 0)}",
        "segment": lambda o: f"{o.get('frames_extracted', 0)} frames extracted",
        "yolo26": lambda o: f"{o.get('total_detections', 0)} objects detected",
        "yoloworld": lambda o: f"{o.get('total_detections', 0)} scene detections",
        # New safety stack stages
        "window_mining": lambda o: f"{len(o.get('candidate_windows', []))} candidate windows identified",
        "violence": lambda o: f"X-CLIP: {len(o.get('violence_segments', []))} segments, max score: {o.get('max_score', 0):.0%}",
        "videomae_violence": lambda o: f"VideoMAE: {o.get('windows_analyzed', len(o.get('scores', [])))} windows, max: {o.get('max_violence_score', max([s.get('violence_score', s.get('score', 0)) for s in o.get('scores', [])], default=0)):.0%}",
        "pose_heuristics": lambda o: f"Pose: {len(o.get('pose_signals', []))} signals detected",
        "nsfw_detection": lambda o: f"NSFW: {o.get('nsfw_frames', 0)}/{o.get('analyzed_frames', 0)} frames, max: {o.get('max_nsfw_score', 0):.0%}",
        # Audio/text stages
        "whisper": lambda o: f"{o.get('chunks_count', 0)} speech chunks, language: {o.get('language', 'unknown')}",
        "ocr": lambda o: f"{o.get('total_detections', 0)} text regions found",
        "text_moderation": lambda o: f"Analyzed {o.get('transcript_chunks_analyzed', 0)} transcript + {o.get('ocr_items_analyzed', 0)} OCR items",
        "policy_fusion": lambda o: f"Verdict: {o.get('verdict', 'unknown')}, {len(o.get('violations', []))} violations",
        "report": lambda o: f"Report generated via {o.get('provider', 'template')}",
    }
    
    summarizer = summaries.get(stage_id)
    if summarizer:
        try:
            return summarizer(output)
        except:
            pass
    
    return "Output available"


def _analyze_stage_output(stage_id: str, output: Dict[str, Any]) -> tuple:
    """Analyze stage output and return (summary, key_findings)."""
    summary = _summarize_stage_output(stage_id, output)
    findings = []
    
    if stage_id == "yolo26":
        detection_summary = output.get("detection_summary", {})
        for obj, count in sorted(detection_summary.items(), key=lambda x: x[1], reverse=True)[:5]:
            findings.append(f"Detected {count}x {obj}")
        if output.get("safety_signals", {}).get("has_weapons"):
            findings.append(f"⚠️ Weapons detected: {output['safety_signals'].get('weapon_count', 0)}")
    
    elif stage_id == "yoloworld":
        matched_prompts = output.get("matched_prompts", [])
        for prompt in matched_prompts[:5]:
            findings.append(f"Scene match: {prompt}")
    
    elif stage_id == "violence":
        segments = output.get("violence_segments", [])
        high_violence = [s for s in segments if s.get("violence_score", 0) > 0.5]
        for seg in high_violence[:3]:
            findings.append(f"⚠️ X-CLIP violence at {seg.get('start_time', 0):.1f}s-{seg.get('end_time', 0):.1f}s (score: {seg.get('violence_score', 0):.0%})")
    
    elif stage_id == "window_mining":
        windows = output.get("candidate_windows", [])
        findings.append(f"Found {len(windows)} candidate windows for analysis")
        for win in windows[:3]:
            findings.append(f"Window: {win.get('start_time', 0):.1f}s-{win.get('end_time', 0):.1f}s ({win.get('reason', 'unknown')})")
    
    elif stage_id == "videomae_violence":
        scores = output.get("videomae_scores", output.get("scores", []))
        high_scores = [s for s in scores if s.get("violence_score", s.get("score", 0)) > 0.5]
        if high_scores:
            findings.append(f"⚠️ VideoMAE detected {len(high_scores)} high-risk windows")
            for s in high_scores[:3]:
                score_val = s.get("violence_score", s.get("score", 0))
                findings.append(f"⚠️ {s.get('label', 'violence')} at {s.get('start_time', 0):.1f}s-{s.get('end_time', 0):.1f}s (score: {score_val:.0%})")
        else:
            findings.append(f"VideoMAE analyzed {len(scores)} windows, no high-risk content")
    
    elif stage_id == "pose_heuristics":
        signals = output.get("pose_signals", [])
        high_conf = [s for s in signals if s.get("confidence", 0) > 0.5]
        if high_conf:
            findings.append(f"⚠️ Detected {len(high_conf)} pose-based violence signals")
            for s in high_conf[:3]:
                signal_type = s.get("signal_type", s.get("type", "interaction"))
                findings.append(f"⚠️ {signal_type} at {s.get('timestamp', 0):.1f}s (confidence: {s.get('confidence', 0):.0%})")
        else:
            findings.append(f"Analyzed poses in {len(signals)} frames, no violence patterns")
    
    elif stage_id == "nsfw_detection":
        is_nsfw = output.get("is_nsfw", False)
        nsfw_frames = output.get("nsfw_frames", 0)
        analyzed = output.get("analyzed_frames", 0)
        max_score = output.get("max_nsfw_score", 0)
        detections = output.get("detections", [])
        
        if is_nsfw or nsfw_frames > 0:
            findings.append(f"⚠️ NSFW visual content detected: {nsfw_frames}/{analyzed} frames")
            findings.append(f"⚠️ Maximum NSFW score: {max_score:.0%}")
            for d in detections[:3]:
                findings.append(f"⚠️ Frame at {d.get('timestamp', 0):.1f}s (score: {d.get('nsfw_score', 0):.0%})")
        else:
            findings.append(f"✓ No NSFW visual content detected in {analyzed} frames")
            findings.append("(Profanity alone does not trigger sexual content)")
    
    elif stage_id == "whisper":
        if output.get("full_text"):
            text = output["full_text"][:200]
            findings.append(f'Transcript: "{text}..."' if len(output["full_text"]) > 200 else f'Transcript: "{text}"')
    
    elif stage_id == "ocr":
        texts = output.get("texts", [])[:3]
        for text in texts:
            findings.append(f'On-screen text: "{text[:50]}"')
    
    elif stage_id == "text_moderation":
        flagged = output.get("flagged_transcript_count", 0) + output.get("flagged_ocr_count", 0)
        if flagged > 0:
            findings.append(f"⚠️ {flagged} text items flagged for moderation")
    
    elif stage_id == "policy_fusion":
        scores = output.get("scores", {})
        for criterion, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
            if score > 0.3:
                findings.append(f"{criterion}: {score:.0%}")
        violations = output.get("violations", [])
        for v in violations[:3]:
            findings.append(f"⚠️ Violation: {v.get('criterion')} ({v.get('severity', 'unknown')} severity)")
    
    return summary, findings


# =============================================================================
# Additional Debug & System Tools
# =============================================================================

@tool
def get_fusion_debug(evaluation_id: str) -> Dict[str, Any]:
    """
    Get detailed fusion debug information including reliability weights, signal sources, and scoring breakdown.
    
    Use this when asked to explain WHY a score was calculated, how signals were combined, or to debug scoring issues.
    
    Args:
        evaluation_id: The evaluation ID
        
    Returns:
        Fusion debug info: reliability weights, signal sources, agreement metrics, calibration
    """
    try:
        with get_db_session() as session:
            evaluation = session.query(Evaluation).filter(
                Evaluation.id == evaluation_id
            ).first()
            
            if not evaluation:
                return {"error": f"Evaluation {evaluation_id} not found"}
            
            item = evaluation.items[0] if evaluation.items else None
            if not item:
                return {"error": "No items in evaluation"}
            
            stage_outputs = item.stage_outputs or {}
            fusion_output = stage_outputs.get("policy_fusion", {})
            
            # Get fusion debug from result
            result = session.query(EvaluationResult).filter(
                EvaluationResult.item_id == item.id
            ).first()
            
            debug_info = {
                "fusion_output": {
                    "verdict": fusion_output.get("verdict"),
                    "scores": fusion_output.get("scores", {}),
                    "violations": fusion_output.get("violations", []),
                },
                "fusion_debug": fusion_output.get("debug", {}),
                "signal_sources": [],
                "reliability_weights": {},
            }
            
            # Extract signal sources from various stages
            if stage_outputs.get("violence"):
                debug_info["signal_sources"].append({
                    "source": "X-CLIP",
                    "type": "violence",
                    "segments": len(stage_outputs["violence"].get("violence_segments", [])),
                    "max_score": stage_outputs["violence"].get("max_score", 0),
                })
            
            if stage_outputs.get("videomae_violence"):
                scores = stage_outputs["videomae_violence"].get("scores", [])
                max_score = max([s.get("violence_score", s.get("score", 0)) for s in scores], default=0)
                debug_info["signal_sources"].append({
                    "source": "VideoMAE",
                    "type": "violence",
                    "windows": len(scores),
                    "max_score": max_score,
                })
            
            if stage_outputs.get("text_moderation"):
                debug_info["signal_sources"].append({
                    "source": "Text Moderation",
                    "type": "language",
                    "flagged_transcript": stage_outputs["text_moderation"].get("flagged_transcript_count", 0),
                    "flagged_ocr": stage_outputs["text_moderation"].get("flagged_ocr_count", 0),
                })
            
            if stage_outputs.get("nsfw_detection"):
                debug_info["signal_sources"].append({
                    "source": "NSFW Detector",
                    "type": "sexual",
                    "nsfw_frames": stage_outputs["nsfw_detection"].get("nsfw_frames", 0),
                    "max_score": stage_outputs["nsfw_detection"].get("max_nsfw_score", 0),
                })
            
            # Standard reliability weights (from research_fusion.py)
            debug_info["reliability_weights"] = {
                "VideoMAE": 0.85,
                "X-CLIP": 0.50,
                "YOLO Objects": 0.75,
                "Text Moderation": 0.70,
                "OCR": 0.35,
                "NSFW Visual": 0.80,
            }
            
            return debug_info
            
    except Exception as e:
        logger.error(f"Error fetching fusion debug for {evaluation_id}: {e}")
        return {"error": f"Failed to fetch fusion debug: {str(e)}"}


@tool
def get_video_metadata(evaluation_id: str) -> Dict[str, Any]:
    """
    Get detailed video metadata including duration, resolution, FPS, audio availability, and processing info.
    
    Use this when asked about the video's technical properties or processing details.
    
    Args:
        evaluation_id: The evaluation ID
        
    Returns:
        Video technical metadata
    """
    try:
        with get_db_session() as session:
            evaluation = session.query(Evaluation).filter(
                Evaluation.id == evaluation_id
            ).first()
            
            if not evaluation:
                return {"error": f"Evaluation {evaluation_id} not found"}
            
            item = evaluation.items[0] if evaluation.items else None
            if not item:
                return {"error": "No items in evaluation"}
            
            stage_outputs = item.stage_outputs or {}
            ingest = stage_outputs.get("ingest", {})
            segment = stage_outputs.get("segment", {})
            
            metadata = {
                "video_id": item.id,
                "filename": item.filename,
                "duration_seconds": item.duration or ingest.get("duration", 0),
                "resolution": {
                    "width": item.width or ingest.get("width", 0),
                    "height": item.height or ingest.get("height", 0),
                },
                "fps": item.fps or ingest.get("fps", 0),
                "has_audio": ingest.get("has_audio", item.has_audio),
                "frames_extracted": segment.get("frames_extracted", 0),
                "segments_created": segment.get("segments_created", 0),
                "original_metadata": ingest.get("original_metadata", {}),
                "format_info": {
                    "codec": ingest.get("codec"),
                    "container": ingest.get("container"),
                    "bitrate": ingest.get("bitrate"),
                },
            }
            
            return metadata
            
    except Exception as e:
        logger.error(f"Error fetching video metadata for {evaluation_id}: {e}")
        return {"error": f"Failed to fetch video metadata: {str(e)}"}


@tool
def get_timings(evaluation_id: str) -> Dict[str, Any]:
    """
    Get timing breakdown showing how long each pipeline stage took.
    
    Use this to answer performance questions or identify slow stages.
    
    Args:
        evaluation_id: The evaluation ID
        
    Returns:
        Stage timing breakdown in milliseconds
    """
    try:
        with get_db_session() as session:
            evaluation = session.query(Evaluation).filter(
                Evaluation.id == evaluation_id
            ).first()
            
            if not evaluation:
                return {"error": f"Evaluation {evaluation_id} not found"}
            
            item = evaluation.items[0] if evaluation.items else None
            if not item:
                return {"error": "No items in evaluation"}
            
            stage_outputs = item.stage_outputs or {}
            timings = {}
            total_ms = 0
            
            for stage_id, output in stage_outputs.items():
                if isinstance(output, dict) and "duration_ms" in output:
                    ms = output["duration_ms"]
                    timings[stage_id] = {
                        "duration_ms": ms,
                        "duration_seconds": ms / 1000 if ms else 0,
                    }
                    total_ms += ms or 0
            
            # Sort by duration
            sorted_timings = dict(sorted(timings.items(), key=lambda x: x[1].get("duration_ms", 0), reverse=True))
            
            # Calculate total pipeline time
            pipeline_duration = None
            if evaluation.completed_at and evaluation.started_at:
                pipeline_duration = (evaluation.completed_at - evaluation.started_at).total_seconds()
            
            return {
                "stage_timings": sorted_timings,
                "total_stage_time_ms": total_ms,
                "total_stage_time_seconds": total_ms / 1000,
                "pipeline_duration_seconds": pipeline_duration,
                "slowest_stage": list(sorted_timings.keys())[0] if sorted_timings else None,
            }
            
    except Exception as e:
        logger.error(f"Error fetching timings for {evaluation_id}: {e}")
        return {"error": f"Failed to fetch timings: {str(e)}"}


@tool
def get_system_info() -> Dict[str, Any]:
    """
    Get system information including loaded models, available stages, and health status.
    
    Use this when asked about what models/detectors are available or system capabilities.
    
    Returns:
        System health, loaded models, and available stages
    """
    try:
        from app.pipeline.stages.registry import get_stage_registry
        
        registry = get_stage_registry()
        available_stages = registry.list_stages()
        
        # Get stage display info
        stage_info = []
        for stage_type in available_stages:
            try:
                plugin = registry.get(stage_type)
                stage_info.append({
                    "id": stage_type,
                    "name": plugin.display_name,
                    "description": getattr(plugin, "description", ""),
                })
            except:
                stage_info.append({"id": stage_type, "name": stage_type, "description": ""})
        
        return {
            "status": "healthy",
            "available_stages": stage_info,
            "total_stages": len(available_stages),
            "capabilities": {
                "violence_detection": "xclip" in available_stages or "videomae_violence" in available_stages,
                "object_detection": "yolo26" in available_stages,
                "speech_transcription": "whisper" in available_stages,
                "text_moderation": "text_moderation" in available_stages,
                "nsfw_detection": "nsfw_detection" in available_stages,
                "pose_analysis": "pose_heuristics" in available_stages,
            },
            "models": [
                {"name": "YOLO26", "purpose": "Object detection (weapons, items)"},
                {"name": "YOLO-World", "purpose": "Open-vocabulary threat scanning"},
                {"name": "X-CLIP", "purpose": "Action-based violence detection"},
                {"name": "VideoMAE", "purpose": "Specialist violence recognition"},
                {"name": "Whisper", "purpose": "Speech-to-text transcription"},
                {"name": "NSFW Detector", "purpose": "Visual adult content detection"},
            ],
        }
        
    except Exception as e:
        logger.error(f"Error fetching system info: {e}")
        return {"error": f"Failed to fetch system info: {str(e)}"}


@tool
def get_detection_details(evaluation_id: str, detection_type: str) -> Dict[str, Any]:
    """
    Get detailed detections of a specific type (objects, violence, text, etc).
    
    Use this when asked for specific details about what was detected.
    
    Args:
        evaluation_id: The evaluation ID
        detection_type: Type of detection - 'objects', 'violence', 'text', 'nsfw', 'weapons', 'persons'
        
    Returns:
        Detailed list of detections with timestamps and confidence
    """
    try:
        with get_db_session() as session:
            evaluation = session.query(Evaluation).filter(
                Evaluation.id == evaluation_id
            ).first()
            
            if not evaluation:
                return {"error": f"Evaluation {evaluation_id} not found"}
            
            item = evaluation.items[0] if evaluation.items else None
            if not item:
                return {"error": "No items in evaluation"}
            
            stage_outputs = item.stage_outputs or {}
            detection_type = detection_type.lower()
            
            if detection_type in ["objects", "all"]:
                yolo26 = stage_outputs.get("yolo26", {})
                detections = yolo26.get("detections", [])
                summary = yolo26.get("detection_summary", {})
                return {
                    "type": "objects",
                    "source": "YOLO26",
                    "total": len(detections),
                    "summary": summary,
                    "detections": detections[:50],  # Limit to 50
                }
            
            elif detection_type == "violence":
                violence = stage_outputs.get("violence", {})
                videomae = stage_outputs.get("videomae_violence", {})
                return {
                    "type": "violence",
                    "xclip": {
                        "segments": violence.get("violence_segments", []),
                        "max_score": violence.get("max_score", 0),
                    },
                    "videomae": {
                        "scores": videomae.get("scores", []),
                        "max_score": max([s.get("violence_score", 0) for s in videomae.get("scores", [])], default=0),
                    },
                }
            
            elif detection_type in ["text", "ocr"]:
                ocr = stage_outputs.get("ocr", {})
                whisper = stage_outputs.get("whisper", {})
                return {
                    "type": "text",
                    "ocr_texts": ocr.get("texts", [])[:20],
                    "transcript": whisper.get("full_text", "")[:2000],
                    "transcript_chunks": whisper.get("chunks", [])[:20],
                }
            
            elif detection_type == "nsfw":
                nsfw = stage_outputs.get("nsfw_detection", {})
                return {
                    "type": "nsfw",
                    "is_nsfw": nsfw.get("is_nsfw", False),
                    "max_score": nsfw.get("max_nsfw_score", 0),
                    "nsfw_frames": nsfw.get("nsfw_frames", 0),
                    "analyzed_frames": nsfw.get("analyzed_frames", 0),
                    "detections": nsfw.get("detections", [])[:10],
                }
            
            elif detection_type == "weapons":
                yolo26 = stage_outputs.get("yolo26", {})
                safety = yolo26.get("safety_signals", {})
                return {
                    "type": "weapons",
                    "has_weapons": safety.get("has_weapons", False),
                    "weapon_count": safety.get("weapon_count", 0),
                    "weapon_types": safety.get("weapon_types", []),
                    "dangerous_items": safety.get("dangerous_items", []),
                }
            
            elif detection_type == "persons":
                yolo26 = stage_outputs.get("yolo26", {})
                pose = stage_outputs.get("pose_heuristics", {})
                summary = yolo26.get("detection_summary", {})
                return {
                    "type": "persons",
                    "person_count": summary.get("person", 0),
                    "pose_signals": pose.get("pose_signals", []),
                    "interactions_detected": len([s for s in pose.get("pose_signals", []) if s.get("confidence", 0) > 0.5]),
                }
            
            return {"error": f"Unknown detection type: {detection_type}. Use: objects, violence, text, nsfw, weapons, persons"}
            
    except Exception as e:
        logger.error(f"Error fetching detections for {evaluation_id}: {e}")
        return {"error": f"Failed to fetch detections: {str(e)}"}


@tool
def explain_verdict(evaluation_id: str) -> Dict[str, Any]:
    """
    Get a comprehensive explanation of why the evaluation reached its verdict.
    
    Use this when asked "why was this flagged?" or "explain the verdict".
    
    Args:
        evaluation_id: The evaluation ID
        
    Returns:
        Structured explanation with contributing factors and evidence summary
    """
    try:
        with get_db_session() as session:
            evaluation = session.query(Evaluation).filter(
                Evaluation.id == evaluation_id
            ).first()
            
            if not evaluation:
                return {"error": f"Evaluation {evaluation_id} not found"}
            
            item = evaluation.items[0] if evaluation.items else None
            if not item:
                return {"error": "No items in evaluation"}
            
            result = session.query(EvaluationResult).filter(
                EvaluationResult.item_id == item.id
            ).first()
            
            stage_outputs = item.stage_outputs or {}
            fusion = stage_outputs.get("policy_fusion", {})
            
            # Build explanation
            verdict = evaluation.overall_verdict.value if evaluation.overall_verdict else "unknown"
            scores = fusion.get("scores", {})
            violations = fusion.get("violations", [])
            
            explanation = {
                "verdict": verdict,
                "confidence": result.confidence if result else None,
                "summary": f"The video was marked as {verdict}.",
                "primary_factors": [],
                "contributing_signals": [],
                "verdict_reasoning": "",
            }
            
            # Identify primary factors (scores > 0.5)
            high_scores = [(k, v) for k, v in scores.items() if v > 0.5]
            for criterion, score in sorted(high_scores, key=lambda x: x[1], reverse=True):
                explanation["primary_factors"].append({
                    "criterion": criterion,
                    "score": score,
                    "severity": "high" if score > 0.7 else "moderate",
                })
            
            # Add contributing signals from stages
            if stage_outputs.get("violence", {}).get("max_score", 0) > 0.3:
                explanation["contributing_signals"].append("X-CLIP detected violent action patterns")
            
            if stage_outputs.get("videomae_violence", {}).get("scores"):
                max_vm = max([s.get("violence_score", 0) for s in stage_outputs["videomae_violence"]["scores"]], default=0)
                if max_vm > 0.3:
                    explanation["contributing_signals"].append(f"VideoMAE confirmed violence (max: {max_vm:.0%})")
            
            if stage_outputs.get("text_moderation", {}).get("flagged_transcript_count", 0) > 0:
                explanation["contributing_signals"].append("Flagged language in audio transcript")
            
            if stage_outputs.get("nsfw_detection", {}).get("is_nsfw"):
                explanation["contributing_signals"].append("Visual adult content detected")
            
            if stage_outputs.get("yolo26", {}).get("safety_signals", {}).get("has_weapons"):
                explanation["contributing_signals"].append("Weapons detected in video frames")
            
            # Build verdict reasoning
            if verdict == "fail":
                if violations:
                    v_list = ", ".join([v.get("criterion", "unknown") for v in violations[:3]])
                    explanation["verdict_reasoning"] = f"The video failed due to violations in: {v_list}."
                else:
                    explanation["verdict_reasoning"] = "The video failed due to policy threshold violations."
            elif verdict == "pass":
                explanation["verdict_reasoning"] = "All safety criteria were within acceptable thresholds."
            else:
                explanation["verdict_reasoning"] = "The verdict requires manual review due to borderline scores."
            
            return explanation
            
    except Exception as e:
        logger.error(f"Error explaining verdict for {evaluation_id}: {e}")
        return {"error": f"Failed to explain verdict: {str(e)}"}


# =============================================================================
# Tool Registry
# =============================================================================

REPORT_CHAT_TOOLS = [
    # Core evaluation tools
    get_evaluation,
    list_stage_runs,
    get_stage_output,
    get_artifacts,
    get_criteria_details,
    # Search and evidence
    search_text,
    get_evidence_for_criterion,
    # Debug and analysis tools
    get_fusion_debug,
    get_video_metadata,
    get_timings,
    get_detection_details,
    explain_verdict,
    # System info
    get_system_info,
]


def get_tool_descriptions() -> str:
    """Get formatted descriptions of all available tools."""
    descriptions = []
    for tool in REPORT_CHAT_TOOLS:
        descriptions.append(f"- **{tool.name}**: {tool.description}")
    return "\n".join(descriptions)
