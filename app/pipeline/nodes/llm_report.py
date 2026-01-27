"""
LLM report generation node.
"""
import json
from typing import Dict, Any
from app.pipeline.state import PipelineState
from app.core.config import settings
from app.core.logging import get_logger
from app.utils.progress import send_progress

logger = get_logger("node.llm_report")


def generate_llm_report(state: PipelineState) -> PipelineState:
    """Generate human-friendly report using OpenAI LLM."""
    logger.info("=== LLM Report Node ===")
    
    send_progress(state.get("progress_callback"), "report_generation", "Generating analysis report", 92)
    
    # Check if OpenAI API key is available
    if not settings.openai_api_key:
        logger.warning("No OpenAI API key, using template report")
        state["report"] = _generate_template_report(state)
        return state
    
    try:
        import openai
        client = openai.OpenAI(api_key=settings.openai_api_key)
        
        # Prepare structured evidence for LLM
        evidence_summary = _prepare_evidence_summary(state)
        
        # Create prompt
        prompt = _create_llm_prompt(state, evidence_summary)
        
        # Call OpenAI
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a child safety analyst. Generate clear, concise reports about video content safety based on automated analysis evidence."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3,
            max_tokens=1000
        )
        
        report = response.choices[0].message.content
        state["report"] = report
        
        logger.info("LLM report generated successfully")
        
    except Exception as e:
        logger.error(f"LLM report generation failed: {e}")
        state["report"] = _generate_template_report(state)
    
    return state


def _prepare_evidence_summary(state: PipelineState) -> Dict[str, Any]:
    """Prepare structured evidence summary for LLM."""
    criterion_scores = state.get("criterion_scores", {})
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
    criterion_scores = state.get("criterion_scores", {})
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
