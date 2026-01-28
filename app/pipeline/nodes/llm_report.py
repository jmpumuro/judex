"""
LLM report generation node.

Uses Qwen (local) or OpenAI (cloud) for generating safety reports.
"""
import json
from typing import Dict, Any
from app.pipeline.state import PipelineState
from app.core.config import settings
from app.core.logging import get_logger
from app.utils.progress import send_progress, save_stage_output, format_stage_output

logger = get_logger("node.llm_report")


def generate_llm_report(state: PipelineState) -> PipelineState:
    """Generate human-friendly report using Qwen (local) or OpenAI (cloud)."""
    logger.info("=== LLM Report Node ===")
    
    send_progress(state.get("progress_callback"), "report_generation", "Generating analysis report", 92)
    
    # Prepare evidence summary
    evidence_summary = _prepare_evidence_summary(state)
    prompt = _create_llm_prompt(state, evidence_summary)
    system_prompt = "You are a child safety analyst. Generate clear, concise reports about video content safety based on automated analysis evidence."
    
    # Try Qwen first (local with 4-bit quantization), then OpenAI (cloud), then template
    if settings.llm_provider == "qwen":
        try:
            from app.models import get_qwen_llm, unload_qwen_llm, free_memory_for_llm
            
            # Free memory from models that are done processing
            logger.info("Freeing memory for Qwen LLM...")
            free_memory_for_llm()
            
            qwen = get_qwen_llm()
            
            logger.info("Generating report with Qwen...")
            report = qwen.generate(prompt, system_prompt=system_prompt)
            state["report"] = report
            logger.info("Qwen report generated successfully")
            
            # Unload Qwen immediately to free memory for next video
            unload_qwen_llm()
            
            return state
            
        except Exception as e:
            logger.warning(f"Qwen generation failed: {e}, falling back to OpenAI")
            # Try to unload if it loaded partially
            try:
                from app.models import unload_qwen_llm
                unload_qwen_llm()
            except:
                pass
    
    # Try OpenAI as fallback
    if settings.openai_api_key:
        try:
            import openai
            client = openai.OpenAI(api_key=settings.openai_api_key)
            
            logger.info("Generating report with OpenAI...")
            response = client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            
            state["report"] = response.choices[0].message.content
            logger.info("OpenAI report generated successfully")
            return state
            
        except Exception as e:
            logger.warning(f"OpenAI generation failed: {e}, using template")
    
    # Fallback to template report
    logger.info("Using template report (no LLM available)")
    state["report"] = _generate_template_report(state)
    
    # Save stage output for real-time retrieval
    save_stage_output(state.get("video_id"), "report", format_stage_output(
        "report",
        report_type="template",
        report_preview=state["report"][:500] if state["report"] else None
    ))
    
    return state


def _prepare_evidence_summary(state: PipelineState) -> Dict[str, Any]:
    """Prepare structured evidence summary for LLM."""
    # Extract scores from criteria_scores (new format) or criterion_scores (legacy)
    criteria_scores = state.get("criteria_scores", {})
    criterion_scores = {}
    for crit_id, crit_data in criteria_scores.items():
        if isinstance(crit_data, dict):
            criterion_scores[crit_id] = crit_data.get("score", 0.0)
        else:
            criterion_scores[crit_id] = float(crit_data)
    
    violations = state.get("violations", [])
    evidence = state.get("evidence", {})
    
    # Summarize key findings
    violence_segments = evidence.get("violence_segments", [])
    high_violence = [s for s in violence_segments if s.get("violence_score", 0) > 0.5]
    
    vision_weapons = [d for d in evidence.get("vision", []) if d.get("category") == "weapon"]
    vision_substances = [d for d in evidence.get("vision", []) if d.get("category") == "substance"]
    
    transcript_profanity = []
    for mod in evidence.get("transcript_moderation", []):
        if mod.get("profanity_words"):
            transcript_profanity.extend(mod["profanity_words"])
    
    return {
        "scores": criterion_scores,
        "violations_count": len(violations),
        "violence": {
            "segments_detected": len(high_violence),
            "weapons_detected": len(vision_weapons)
        },
        "profanity": {
            "words_found": list(set(transcript_profanity))[:10]  # Max 10
        },
        "substances": {
            "objects_detected": len(vision_substances)
        }
    }


def _create_llm_prompt(state: PipelineState, evidence_summary: Dict[str, Any]) -> str:
    """Create prompt for LLM report generation."""
    verdict = state.get("verdict", "UNKNOWN")
    violations = state.get("violations", [])
    duration = state.get("duration", 0)
    
    prompt = f"""Analyze this video content safety assessment and generate a concise report.

VIDEO DETAILS:
- Duration: {duration:.1f} seconds
- Verdict: {verdict}

CRITERION SCORES (0-1 scale):
{json.dumps(evidence_summary["scores"], indent=2)}

VIOLATIONS DETECTED: {evidence_summary["violations_count"]}
{json.dumps(violations, indent=2)}

KEY EVIDENCE:
- Violence segments: {evidence_summary["violence"]["segments_detected"]}
- Weapons detected: {evidence_summary["violence"]["weapons_detected"]}
- Profanity words: {", ".join(evidence_summary["profanity"]["words_found"][:5]) if evidence_summary["profanity"]["words_found"] else "none"}
- Substance-related objects: {evidence_summary["substances"]["objects_detected"]}

Generate a report with:
1. A brief summary (2-3 sentences)
2. Specific violations with timestamps (bullet points)
3. Recommended age guidance (if applicable)
4. A limitations note about automated analysis

Keep it factual and concise."""
    
    return prompt


def _generate_template_report(state: PipelineState) -> str:
    """Generate template report without LLM (AI-style format)."""
    verdict = state.get("verdict", "UNKNOWN")
    violations = state.get("violations", [])
    
    # Extract scores from criteria_scores (new format)
    criteria_scores = state.get("criteria_scores", {})
    criterion_scores = {}
    for crit_id, crit_data in criteria_scores.items():
        if isinstance(crit_data, dict):
            criterion_scores[crit_id] = crit_data.get("score", 0.0)
        else:
            criterion_scores[crit_id] = float(crit_data)
    
    duration = state.get("duration", 0)
    
    report_lines = []
    
    # AI-Style Summary Header
    report_lines.append(f"## 🎬 Video Safety Analysis")
    report_lines.append(f"")
    
    # Generate natural language summary based on verdict
    summary_text = ""
    if verdict == "SAFE":
        summary_text = f"This {duration:.1f}-second video has been analyzed and appears appropriate for general audiences. No significant safety concerns were detected across violence, profanity, sexual content, substance use, or hate speech categories."
    elif verdict == "CAUTION":
        high_scores = [k for k, v in criterion_scores.items() if v >= 0.4]
        if high_scores:
            summary_text = f"This {duration:.1f}-second video requires caution. Moderate levels of {' and '.join(high_scores[:2])} were detected. Parental guidance or content warnings are recommended."
        else:
            summary_text = f"This {duration:.1f}-second video has some content that may not be suitable for all audiences. Review the detailed findings below."
    elif verdict == "UNSAFE":
        high_scores = [k for k, v in criterion_scores.items() if v >= 0.6]
        if high_scores:
            summary_text = f"This {duration:.1f}-second video contains significant safety concerns. High levels of {' and '.join(high_scores[:2])} were detected and may violate content policies."
        else:
            summary_text = f"This {duration:.1f}-second video is not suitable for general audiences and should be reviewed or restricted."
    else:
        summary_text = f"This {duration:.1f}-second video requires human review. The automated analysis detected ambiguous or borderline content."
    
    report_lines.append(summary_text)
    report_lines.append(f"")
    report_lines.append(f"**Final Verdict:** {verdict}")
    report_lines.append(f"")
    
    # Detailed Findings
    report_lines.append(f"### 📊 Content Analysis")
    report_lines.append(f"")
    for criterion, score in sorted(criterion_scores.items(), key=lambda x: x[1], reverse=True):
        if score >= 0.6:
            status = "⚠️ **High**"
            desc = "significantly elevated"
        elif score >= 0.3:
            status = "⚡ Moderate"
            desc = "moderately elevated"
        else:
            status = "✓ Low"
            desc = "within acceptable range"
        
        report_lines.append(f"- **{criterion.title()}**: {status} (score: {score:.2f}) - {desc}")
    report_lines.append(f"")
    
    # Specific Violations with Timestamps
    if violations:
        report_lines.append(f"### 🚨 Violations Detected")
        report_lines.append(f"")
        for v in violations:
            criterion = v["criterion"]
            severity = v["severity"]
            ranges = v.get("timestamp_ranges", [])
            
            if ranges:
                time_str = ", ".join([f"{r[0]:.1f}s-{r[1]:.1f}s" for r in ranges[:5]])
                report_lines.append(f"**{criterion.title()}** ({severity} severity)")
                report_lines.append(f"- Timestamps: {time_str}")
            else:
                report_lines.append(f"**{criterion.title()}** ({severity} severity)")
            report_lines.append(f"")
    
    # Age Guidance
    report_lines.append(f"### 👥 Recommended Guidance")
    report_lines.append(f"")
    if verdict == "SAFE":
        report_lines.append(f"This content is suitable for general audiences including children.")
    elif verdict == "CAUTION":
        report_lines.append(f"Parental guidance suggested. Content may contain mild violence, language, or themes requiring supervision for younger viewers.")
    elif verdict == "UNSAFE":
        report_lines.append(f"This content is not suitable for minors and should be age-restricted or reviewed for removal.")
    else:
        report_lines.append(f"Manual review required before making final content distribution decisions.")
    report_lines.append(f"")
    
    # Limitations Footer
    report_lines.append(f"---")
    report_lines.append(f"")
    report_lines.append(f"*Note: This is an automated analysis using computer vision, speech recognition, and AI models. Borderline or nuanced cases should be reviewed by human moderators for final determination.*")
    
    return "\n".join(report_lines)
