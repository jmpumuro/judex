"""
LLM report generation node.

Industry Standard: Uses Factory Pattern for LLM-agnostic report generation.
Supports OpenAI (default), Qwen (local), with automatic fallback.
"""
import json
from typing import Dict, Any, Optional
from langchain_core.runnables import RunnableConfig

from app.pipeline.state import PipelineState
from app.pipeline.callbacks import send_progress
from app.llm import get_llm, LLMProvider
from app.core.logging import get_logger
from app.utils.progress import save_stage_output, format_stage_output

logger = get_logger("node.llm_report")


# System prompt for safety analysis - LLM acts as FINAL JUDGE
SYSTEM_PROMPT = """You are Judex, an expert video content safety analyst and the FINAL AUTHORITY on content safety verdicts.

Your role is to:
1. REVIEW all automated analysis results from multiple AI models (X-CLIP, VideoMAE, YOLO, Whisper, etc.)
2. SYNTHESIZE the evidence from each detection stage into a coherent assessment  
3. MAKE THE FINAL VERDICT - you may OVERRIDE the automated verdict if the evidence warrants it
4. EXPLAIN your reasoning clearly, citing specific evidence from each stage

You have access to reliability-weighted fusion scores, but YOU are the final judge. If you see:
- Conflicting signals between models → Investigate and make a reasoned call
- False positive patterns (sports/gaming violence) → Consider lowering severity
- Multiple specialist models agreeing → Give more weight to their consensus
- Missing or skipped stages → Note the gap in your assessment

Be factual, cite specific timestamps and detections, and provide actionable recommendations."""


def generate_llm_report_impl(state: PipelineState, config: Optional[RunnableConfig] = None) -> PipelineState:
    """
    Generate human-friendly report using configured LLM provider.
    
    Industry Standard: 
    - Uses Factory Pattern to get LLM adapter
    - Automatic fallback: OpenAI → Qwen → Template
    - Centralized LLM configuration via settings
    """
    logger.info("=== LLM Report Node ===")
    
    send_progress(config, "report_generation", "Generating analysis report", 92)
    
    # Prepare evidence summary and prompt
    evidence_summary = _prepare_evidence_summary(state)
    prompt = _create_llm_prompt(state, evidence_summary)
    
    # Get LLM using factory (handles provider selection and fallback)
    llm = get_llm(fallback=True)
    
    if llm:
        try:
            logger.info(f"Generating report with {llm.provider_name}/{llm.model_name}")
            
            response = llm.generate(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                max_tokens=4000,  # Increased for complete reports
                temperature=0.3
            )
            
            state["report"] = response.content
            
            # Save stage output
            save_stage_output(state.get("video_id"), "report", format_stage_output(
                "report",
                provider=llm.provider_name,
                model=llm.model_name,
                tokens_used=response.usage.get("total_tokens") if response.usage else None,
                report_preview=response.content[:500] if response.content else None
            ))
            
            # Unload local models to free memory
            if llm.provider_name == "qwen":
                from app.llm.factory import unload_llm
                unload_llm("qwen")
            
            logger.info(f"Report generated successfully via {llm.provider_name}")
            return state
            
        except Exception as e:
            logger.warning(f"LLM generation failed: {e}, using template")
    
    # Fallback to template report
    logger.info("Using template report (no LLM available)")
    state["report"] = _generate_template_report(state)
    
    save_stage_output(state.get("video_id"), "report", format_stage_output(
        "report",
        provider="template",
        report_preview=state["report"][:500] if state["report"] else None
    ))
    
    return state


# Legacy wrapper for backward compatibility
def generate_llm_report(state: PipelineState) -> PipelineState:
    """Legacy wrapper - calls impl without config."""
    return generate_llm_report_impl(state, None)


def _prepare_evidence_summary(state: PipelineState) -> Dict[str, Any]:
    """
    Prepare comprehensive evidence summary from ALL stages for LLM.
    
    Reads from BOTH direct state keys AND evidence dict for compatibility.
    """
    # Basic info
    duration = state.get("duration", 0)
    fps = state.get("fps", 30)
    has_audio = state.get("has_audio", False)
    
    # Criteria scores
    criteria_scores = state.get("criteria_scores", {})
    criterion_scores = {}
    for crit_id, crit_data in criteria_scores.items():
        if isinstance(crit_data, dict):
            criterion_scores[crit_id] = crit_data.get("score", 0.0)
        else:
            criterion_scores[crit_id] = float(crit_data)
    
    violations = state.get("violations", [])
    evidence = state.get("evidence", {})
    
    # === YOLO26 Object Detection ===
    # Read from direct state key first, then fallback to evidence dict
    vision_detections = state.get("vision_detections", []) or evidence.get("vision", [])
    logger.info(f"LLM Report - YOLO26 detections: {len(vision_detections)}")
    
    yolo26_summary = {}
    for det in vision_detections:
        label = det.get("label", det.get("class", "unknown"))
        yolo26_summary[label] = yolo26_summary.get(label, 0) + 1
    top_objects = sorted(yolo26_summary.items(), key=lambda x: x[1], reverse=True)[:10]
    
    # Categorize detections
    weapon_classes = {"knife", "gun", "weapon", "pistol", "rifle", "sword"}
    weapons_detected = [d for d in vision_detections if d.get("label", "").lower() in weapon_classes]
    
    # === YOLO-World Scene Analysis ===
    yoloworld_detections = state.get("yoloworld_detections", []) or evidence.get("yoloworld", [])
    logger.info(f"LLM Report - YOLO-World detections: {len(yoloworld_detections)}")
    
    yoloworld_summary = {}
    for det in yoloworld_detections:
        label = det.get("prompt_match", det.get("label", "unknown"))
        yoloworld_summary[label] = yoloworld_summary.get(label, 0) + 1
    
    # === Violence Detection (X-CLIP) ===
    violence_segments = state.get("violence_segments", []) or evidence.get("violence_segments", [])
    logger.info(f"LLM Report - Violence segments: {len(violence_segments)}")
    
    high_violence = [s for s in violence_segments if s.get("violence_score", 0) > 0.5]
    max_violence_score = max([s.get("violence_score", 0) for s in violence_segments], default=0)
    
    # === Audio Transcription (Whisper) ===
    transcript = state.get("transcript", {})
    full_transcript = transcript.get("text", "") if isinstance(transcript, dict) else ""
    transcript_chunks = transcript.get("chunks", []) if isinstance(transcript, dict) else []
    transcript_language = transcript.get("language", "unknown") if isinstance(transcript, dict) else "unknown"
    logger.info(f"LLM Report - Transcript length: {len(full_transcript)} chars")
    
    # === OCR Text Detection ===
    ocr_detections = state.get("ocr_results", []) or evidence.get("ocr", [])
    logger.info(f"LLM Report - OCR detections: {len(ocr_detections)}")
    
    ocr_texts = [d.get("text", "") for d in ocr_detections if d.get("text")]
    
    # === Text Moderation Results ===
    text_moderation = state.get("transcript_moderation", []) or evidence.get("transcript_moderation", [])
    ocr_moderation = state.get("ocr_moderation", [])
    all_moderation = text_moderation + ocr_moderation
    
    flagged_categories = []
    profanity_words = []
    for mod in all_moderation:
        if mod.get("flagged_categories"):
            flagged_categories.extend(mod["flagged_categories"])
        if mod.get("profanity_words"):
            profanity_words.extend(mod["profanity_words"])
    flagged_categories = list(set(flagged_categories))
    profanity_words = list(set(profanity_words))[:15]
    
    # === Window Mining (Candidate Windows) ===
    candidate_windows = state.get("candidate_windows", []) or evidence.get("candidate_windows", [])
    logger.info(f"LLM Report - Candidate windows: {len(candidate_windows)}")
    
    # === VideoMAE Violence Detection ===
    videomae_scores = state.get("videomae_scores", []) or evidence.get("videomae_scores", [])
    logger.info(f"LLM Report - VideoMAE scores: {len(videomae_scores)}")
    
    # VideoMAE uses 'violence_score' key, not 'score'
    videomae_high = [s for s in videomae_scores if s.get("violence_score", s.get("score", 0)) > 0.5]
    videomae_max = max([s.get("violence_score", s.get("score", 0)) for s in videomae_scores], default=0)
    
    # === Pose Heuristics ===
    pose_signals = state.get("pose_signals", []) or evidence.get("pose_signals", [])
    logger.info(f"LLM Report - Pose signals: {len(pose_signals)}")
    
    pose_high_conf = [s for s in pose_signals if s.get("confidence", 0) > 0.5]
    
    # === NSFW Visual Detection ===
    # Industry standard: Visual confirmation for sexual content scoring
    nsfw_results = state.get("nsfw_results", {}) or evidence.get("nsfw_results", {})
    nsfw_frames = nsfw_results.get("nsfw_frames", 0)
    nsfw_max = nsfw_results.get("max_nsfw_score", 0)
    is_nsfw = nsfw_results.get("is_nsfw", False)
    logger.info(f"LLM Report - NSFW: {nsfw_frames} frames, max={nsfw_max:.2f}, is_nsfw={is_nsfw}")
    
    # === Fusion Debug Info ===
    fusion_debug = state.get("fusion_debug", {})
    
    # === External Stage Results ===
    external_verdicts = state.get("external_verdicts", [])
    external_violations = state.get("external_violations", [])
    
    return {
        # Video metadata
        "video": {
            "duration_seconds": duration,
            "fps": fps,
            "has_audio": has_audio,
        },
        # Scoring
        "scores": criterion_scores,
        "violations": violations,
        "violations_count": len(violations),
        # Object detection (YOLO26)
        "object_detection": {
            "total_detections": len(vision_detections),
            "top_objects": dict(top_objects),
            "weapons_found": len(weapons_detected),
            "weapon_types": list(set(d.get("label", "") for d in weapons_detected)),
        },
        # Scene analysis (YOLO-World)
        "scene_analysis": {
            "total_detections": len(yoloworld_detections),
            "detected_concepts": dict(yoloworld_summary),
        },
        # X-CLIP Violence
        "xclip_violence": {
            "segments_analyzed": len(violence_segments),
            "high_violence_segments": len(high_violence),
            "max_violence_score": max_violence_score,
            "timestamps": [(s.get("start_time", 0), s.get("end_time", 0), s.get("violence_score", 0)) 
                          for s in high_violence[:5]],
        },
        # NEW: Window Mining
        "window_mining": {
            "windows_found": len(candidate_windows),
            "windows": [
                {
                    "start": w.get("start_time", 0),
                    "end": w.get("end_time", 0),
                    "reason": w.get("reason", "unknown"),
                    "score": w.get("score", 0)
                }
                for w in candidate_windows[:5]
            ]
        },
        # NEW: VideoMAE Violence
        "videomae_violence": {
            "windows_analyzed": len(videomae_scores),
            "high_violence_windows": len(videomae_high),
            "max_score": videomae_max,
            "detections": [
                {
                    "start": s.get("start_time", 0),
                    "end": s.get("end_time", 0),
                    "score": s.get("violence_score", s.get("score", 0)),
                    "label": s.get("label", "violence")
                }
                for s in videomae_high[:5]
            ]
        },
        # NEW: Pose Heuristics
        "pose_heuristics": {
            "signals_detected": len(pose_signals),
            "high_confidence_signals": len(pose_high_conf),
            "signals": [
                {
                    "timestamp": s.get("timestamp", 0),
                    "type": s.get("signal_type", s.get("type", "unknown")),
                    "confidence": s.get("confidence", 0),
                    "details": s.get("reason", s.get("details", ""))
                }
                for s in pose_high_conf[:5]
            ]
        },
        # NSFW Visual Detection (for sexual content confirmation)
        "nsfw_detection": {
            "analyzed_frames": nsfw_results.get("analyzed_frames", 0),
            "nsfw_frames": nsfw_frames,
            "max_nsfw_score": nsfw_max,
            "is_nsfw": is_nsfw,
            "detections": nsfw_results.get("detections", [])[:5],
        },
        # Audio/Speech
        "audio": {
            "has_audio": has_audio,
            "transcript_language": transcript_language,
            "transcript_preview": full_transcript[:500] if full_transcript else None,
            "transcript_chunks": len(transcript_chunks),
        },
        # OCR
        "ocr": {
            "text_regions_found": len(ocr_detections),
            "texts": ocr_texts[:10],
        },
        # Text moderation
        "text_moderation": {
            "flagged_categories": flagged_categories,
            "profanity_words": profanity_words,
        },
        # Fusion debug
        "fusion_debug": {
            "signals_used": fusion_debug.get("signals_used", {}),
            "reliability_weights": fusion_debug.get("reliability_weights", {}),
            "verdict_rationale": fusion_debug.get("verdict_rationale", "")
        },
        # External stages
        "external_analysis": {
            "verdicts": external_verdicts,
            "violations": external_violations[:5] if external_violations else [],
        }
    }


def _create_llm_prompt(state: PipelineState, evidence_summary: Dict[str, Any]) -> str:
    """
    Create comprehensive prompt with all stage outputs for LLM to act as FINAL JUDGE.
    """
    verdict = state.get("verdict", "UNKNOWN")
    confidence = state.get("confidence", 0.0)
    
    # Pre-format conditional sections
    has_audio_str = "Yes" if evidence_summary['video']['has_audio'] else "No"
    audio_present_str = "Yes" if evidence_summary['audio']['has_audio'] else "No"
    
    weapon_types_str = ""
    if evidence_summary['object_detection']['weapons_found'] > 0:
        weapon_types_str = f"⚠️ Weapon types: {evidence_summary['object_detection']['weapon_types']}"
    
    # X-CLIP violence
    xclip_timestamps_str = "No significant violence detected by X-CLIP."
    if evidence_summary['xclip_violence']['high_violence_segments'] > 0:
        xclip_timestamps_str = f"⚠️ Violence timestamps (start, end, score): {evidence_summary['xclip_violence']['timestamps']}"
    
    # VideoMAE violence (new)
    videomae_str = "VideoMAE: No analysis performed or no violence detected."
    if evidence_summary['videomae_violence']['windows_analyzed'] > 0:
        videomae_detections = evidence_summary['videomae_violence']['detections']
        if videomae_detections:
            det_strs = [f"[{d['start']:.1f}s-{d['end']:.1f}s: {d['label']} @ {d['score']:.2f}]" for d in videomae_detections]
            videomae_str = f"⚠️ VideoMAE detections: {', '.join(det_strs)}"
        else:
            videomae_str = f"VideoMAE analyzed {evidence_summary['videomae_violence']['windows_analyzed']} windows, max score: {evidence_summary['videomae_violence']['max_score']:.2f}"
    
    # Pose heuristics (new)
    pose_str = "Pose Analysis: No violence patterns detected."
    if evidence_summary['pose_heuristics']['high_confidence_signals'] > 0:
        pose_signals = evidence_summary['pose_heuristics']['signals']
        sig_strs = [f"[{s['timestamp']:.1f}s: {s['type']} @ {s['confidence']:.2f}]" for s in pose_signals]
        pose_str = f"⚠️ Pose signals: {', '.join(sig_strs)}"
    
    # Window mining (new)
    windows_str = "Window Mining: No candidate windows identified."
    if evidence_summary['window_mining']['windows_found'] > 0:
        windows = evidence_summary['window_mining']['windows']
        win_strs = [f"[{w['start']:.1f}s-{w['end']:.1f}s: {w['reason']}]" for w in windows]
        windows_str = f"Candidate windows: {', '.join(win_strs)}"
    
    transcript_preview_str = "No speech detected."
    if evidence_summary['audio']['transcript_preview']:
        preview = evidence_summary['audio']['transcript_preview']
        transcript_preview_str = f'Transcript preview: "{preview}"'
    
    ocr_text_str = "No on-screen text detected."
    if evidence_summary['ocr']['texts']:
        ocr_text_str = f"Detected text: {evidence_summary['ocr']['texts']}"
    
    flagged_str = evidence_summary['text_moderation']['flagged_categories'] if evidence_summary['text_moderation']['flagged_categories'] else "None"
    profanity_str = evidence_summary['text_moderation']['profanity_words'] if evidence_summary['text_moderation']['profanity_words'] else "None"
    
    external_verdicts_str = evidence_summary['external_analysis']['verdicts'] if evidence_summary['external_analysis']['verdicts'] else "None"
    external_violations_str = json.dumps(evidence_summary['external_analysis']['violations']) if evidence_summary['external_analysis']['violations'] else "None"
    
    violations_str = json.dumps(evidence_summary['violations'], indent=2) if evidence_summary['violations'] else "No policy violations detected."
    
    # Fusion debug info
    fusion_rationale = evidence_summary['fusion_debug'].get('verdict_rationale', 'Not available')
    signals_used = evidence_summary['fusion_debug'].get('signals_used', {})
    
    # Build detailed prompt with all stage context
    prompt = f"""You are JUDEX, the FINAL JUDGE for video content safety. Review ALL automated analysis below and render your verdict.

╔═══════════════════════════════════════════════════════════════════════════════╗
║                        VIDEO CONTENT SAFETY ANALYSIS                          ║
║                    You are the FINAL AUTHORITY on this verdict                ║
╚═══════════════════════════════════════════════════════════════════════════════╝

═══════════════════════════════════════════════════════════════
📹 VIDEO METADATA
═══════════════════════════════════════════════════════════════
- Duration: {evidence_summary['video']['duration_seconds']:.1f} seconds
- Frame Rate: {evidence_summary['video']['fps']} fps  
- Has Audio: {has_audio_str}

═══════════════════════════════════════════════════════════════
⚖️ AUTOMATED VERDICT (Pre-LLM Fusion)
═══════════════════════════════════════════════════════════════
- Automated Verdict: {verdict}
- Confidence: {confidence:.0%}
- Fusion Rationale: {fusion_rationale}

NOTE: This is the automated verdict. As the FINAL JUDGE, you may:
- CONFIRM this verdict if evidence supports it
- OVERRIDE to a different verdict if you see conflicting/insufficient evidence
- Explain any disagreement with the automated system

═══════════════════════════════════════════════════════════════
📊 CRITERION SCORES (0.0 = Safe, 1.0 = Unsafe)
═══════════════════════════════════════════════════════════════
{json.dumps(evidence_summary['scores'], indent=2)}

═══════════════════════════════════════════════════════════════
🔍 STAGE 1: OBJECT DETECTION (YOLO26)
═══════════════════════════════════════════════════════════════
Total objects detected: {evidence_summary['object_detection']['total_detections']}
Top objects found: {json.dumps(evidence_summary['object_detection']['top_objects'])}
Weapons detected: {evidence_summary['object_detection']['weapons_found']}
{weapon_types_str}

═══════════════════════════════════════════════════════════════
🎬 STAGE 2: SCENE ANALYSIS (YOLO-World)
═══════════════════════════════════════════════════════════════
Total scene detections: {evidence_summary['scene_analysis']['total_detections']}
Detected concepts: {json.dumps(evidence_summary['scene_analysis']['detected_concepts'])}

═══════════════════════════════════════════════════════════════
🎯 STAGE 3: CANDIDATE WINDOW MINING
═══════════════════════════════════════════════════════════════
{windows_str}

═══════════════════════════════════════════════════════════════
⚔️ STAGE 4: X-CLIP VIOLENCE DETECTION
═══════════════════════════════════════════════════════════════
Segments analyzed: {evidence_summary['xclip_violence']['segments_analyzed']}
High violence segments: {evidence_summary['xclip_violence']['high_violence_segments']}
Maximum violence score: {evidence_summary['xclip_violence']['max_violence_score']:.2f}
{xclip_timestamps_str}

═══════════════════════════════════════════════════════════════
🎥 STAGE 5: VideoMAE ACTION VIOLENCE (Specialist Model)
═══════════════════════════════════════════════════════════════
Windows analyzed: {evidence_summary['videomae_violence']['windows_analyzed']}
High-risk windows: {evidence_summary['videomae_violence']['high_violence_windows']}
Max score: {evidence_summary['videomae_violence']['max_score']:.2f}
{videomae_str}

═══════════════════════════════════════════════════════════════
🤸 STAGE 6: POSE INTERACTION HEURISTICS
═══════════════════════════════════════════════════════════════
Signals detected: {evidence_summary['pose_heuristics']['signals_detected']}
High confidence: {evidence_summary['pose_heuristics']['high_confidence_signals']}
{pose_str}

═══════════════════════════════════════════════════════════════
🎤 STAGE 7: AUDIO TRANSCRIPTION (Whisper)
═══════════════════════════════════════════════════════════════
Audio present: {audio_present_str}
Language detected: {evidence_summary['audio']['transcript_language']}
Transcript chunks: {evidence_summary['audio']['transcript_chunks']}
{transcript_preview_str}

═══════════════════════════════════════════════════════════════
📝 STAGE 8: TEXT RECOGNITION (OCR)
═══════════════════════════════════════════════════════════════
Text regions found: {evidence_summary['ocr']['text_regions_found']}
{ocr_text_str}

═══════════════════════════════════════════════════════════════
🚫 STAGE 9: TEXT MODERATION
═══════════════════════════════════════════════════════════════
Flagged categories: {flagged_str}
Profanity detected: {profanity_str}

═══════════════════════════════════════════════════════════════
🔗 EXTERNAL/CUSTOM ANALYSIS
═══════════════════════════════════════════════════════════════
External verdicts: {external_verdicts_str}
External violations: {external_violations_str}

═══════════════════════════════════════════════════════════════
🚨 POLICY VIOLATIONS ({evidence_summary['violations_count']} total)
═══════════════════════════════════════════════════════════════
{violations_str}

╔═══════════════════════════════════════════════════════════════════════════════╗
║                           YOUR FINAL JUDGMENT                                  ║
╚═══════════════════════════════════════════════════════════════════════════════╝

As JUDEX, the final authority, generate your comprehensive verdict report using this structure:

## 🔒 Final Verdict

| Metric | Value |
|--------|-------|
| **Your Final Verdict** | [SAFE / CAUTION / NEEDS_REVIEW / UNSAFE] |
| **Confidence** | [Your confidence as percentage] |
| **Primary Concern** | [Highest-risk criterion or "None"] |
| **Agrees with Automated?** | [Yes/No - explain if different] |

## 📋 Executive Summary
A clear 2-3 sentence summary of your findings and verdict rationale.

## 🔍 Evidence Analysis

### Violence Assessment
- **X-CLIP:** [Your interpretation of X-CLIP results]
- **VideoMAE:** [Your interpretation of VideoMAE specialist model]  
- **Pose Analysis:** [Your interpretation of pose heuristics]
- **Weapons:** [YOLO weapon detections if any]
- **Overall Violence Risk:** [Your assessment combining all violence signals]

### Content Moderation
- **Speech Analysis:** [Key findings from transcript]
- **Visual Text:** [OCR findings]
- **Flagged Categories:** [Moderation flags]

## ⚠️ Key Findings
List the most significant safety-relevant findings with timestamps.

## 📊 Risk Assessment
Explain your reasoning for the final verdict, citing specific evidence from each stage.

## 💡 Recommendations
Based on your verdict:
- **SAFE:** Approval recommendation
- **CAUTION:** Content warnings or age restrictions needed
- **NEEDS_REVIEW:** Specific areas requiring human moderator attention
- **UNSAFE:** Required actions (restriction, removal, escalation)

---
*Analysis by Judex AI Safety System. {evidence_summary['video']['duration_seconds']:.1f}s video processed through {9 + len(evidence_summary['external_analysis'].get('verdicts', []))} detection stages.*"""
    
    return prompt


def _generate_template_report(state: PipelineState) -> str:
    """Generate template report without LLM (comprehensive format with all stages)."""
    verdict = state.get("verdict", "UNKNOWN")
    violations = state.get("violations", [])
    
    criteria_scores = state.get("criteria_scores", {})
    criterion_scores = {}
    for crit_id, crit_data in criteria_scores.items():
        if isinstance(crit_data, dict):
            criterion_scores[crit_id] = crit_data.get("score", 0.0)
        else:
            criterion_scores[crit_id] = float(crit_data)
    
    duration = state.get("duration", 0)
    
    # Get all stage outputs
    violence_segments = state.get("violence_segments", [])
    videomae_scores = state.get("videomae_scores", [])
    pose_signals = state.get("pose_signals", [])
    vision_detections = state.get("vision_detections", [])
    candidate_windows = state.get("candidate_windows", [])
    fusion_debug = state.get("fusion_debug", {})
    
    report_lines = []
    
    report_lines.append(f"## 🔒 Judex Safety Analysis")
    report_lines.append(f"")
    
    # Verdict summary
    summary_text = ""
    if verdict == "SAFE":
        summary_text = f"This {duration:.1f}-second video has been analyzed across {8 + len(videomae_scores)} detection models and appears appropriate for general audiences. No significant safety concerns were detected."
    elif verdict == "CAUTION":
        high_scores = [k for k, v in criterion_scores.items() if v >= 0.4]
        if high_scores:
            summary_text = f"This {duration:.1f}-second video requires caution. Moderate levels of {' and '.join(high_scores[:2])} were detected. Parental guidance or content warnings are recommended."
        else:
            summary_text = f"This {duration:.1f}-second video has some content that may not be suitable for all audiences."
    elif verdict == "UNSAFE":
        high_scores = [k for k, v in criterion_scores.items() if v >= 0.6]
        if high_scores:
            summary_text = f"This {duration:.1f}-second video contains significant safety concerns. High levels of {' and '.join(high_scores[:2])} were detected and may violate content policies."
        else:
            summary_text = f"This {duration:.1f}-second video is not suitable for general audiences."
    else:
        summary_text = f"This {duration:.1f}-second video requires human review. The automated analysis detected ambiguous or borderline content."
    
    report_lines.append(summary_text)
    report_lines.append(f"")
    
    # Verdict table
    report_lines.append(f"| Metric | Value |")
    report_lines.append(f"|--------|-------|")
    report_lines.append(f"| **Final Verdict** | {verdict} |")
    highest_criterion = max(criterion_scores.items(), key=lambda x: x[1], default=("none", 0))
    report_lines.append(f"| **Primary Concern** | {highest_criterion[0].title()} ({highest_criterion[1]:.2f}) |")
    report_lines.append(f"")
    
    # Criterion scores
    report_lines.append(f"### 📊 Criterion Scores")
    report_lines.append(f"")
    for criterion, score in sorted(criterion_scores.items(), key=lambda x: x[1], reverse=True):
        if score >= 0.6:
            status = "⚠️ **HIGH**"
        elif score >= 0.3:
            status = "⚡ MODERATE"
        else:
            status = "✓ Low"
        report_lines.append(f"- **{criterion.title()}**: {status} ({score:.2f})")
    report_lines.append(f"")
    
    # Violence Analysis (enhanced)
    report_lines.append(f"### ⚔️ Violence Analysis")
    report_lines.append(f"")
    
    # X-CLIP
    xclip_max = max([s.get("violence_score", 0) for s in violence_segments], default=0)
    xclip_high = len([s for s in violence_segments if s.get("violence_score", 0) > 0.5])
    report_lines.append(f"**X-CLIP Violence Detection:**")
    report_lines.append(f"- Segments analyzed: {len(violence_segments)}")
    report_lines.append(f"- High-risk segments: {xclip_high}")
    report_lines.append(f"- Max score: {xclip_max:.2f}")
    report_lines.append(f"")
    
    # VideoMAE
    if videomae_scores:
        vmae_max = max([s.get("score", 0) for s in videomae_scores], default=0)
        vmae_high = len([s for s in videomae_scores if s.get("score", 0) > 0.5])
        report_lines.append(f"**VideoMAE Action Violence (Specialist):**")
        report_lines.append(f"- Windows analyzed: {len(videomae_scores)}")
        report_lines.append(f"- High-risk windows: {vmae_high}")
        report_lines.append(f"- Max score: {vmae_max:.2f}")
        if vmae_high > 0:
            for s in videomae_scores[:3]:
                if s.get("score", 0) > 0.5:
                    report_lines.append(f"  - [{s.get('start_time', 0):.1f}s - {s.get('end_time', 0):.1f}s]: {s.get('label', 'violence')} ({s.get('score', 0):.2f})")
        report_lines.append(f"")
    
    # Pose Analysis
    if pose_signals:
        pose_high = len([s for s in pose_signals if s.get("confidence", 0) > 0.5])
        report_lines.append(f"**Pose Interaction Heuristics:**")
        report_lines.append(f"- Signals detected: {len(pose_signals)}")
        report_lines.append(f"- High-confidence: {pose_high}")
        if pose_high > 0:
            for s in pose_signals[:3]:
                if s.get("confidence", 0) > 0.5:
                    signal_type = s.get("signal_type", s.get("type", "unknown"))
                    report_lines.append(f"  - [{s.get('timestamp', 0):.1f}s]: {signal_type} ({s.get('confidence', 0):.2f})")
        report_lines.append(f"")
    
    # Weapons
    weapon_classes = {"knife", "gun", "weapon", "pistol", "rifle", "sword", "machete"}
    weapons = [d for d in vision_detections if d.get("category") == "weapon" or d.get("label", "").lower() in weapon_classes]
    if weapons:
        report_lines.append(f"**Weapon Detection:**")
        report_lines.append(f"- ⚠️ Weapons found: {len(weapons)}")
        weapon_types = list(set(d.get("label", "unknown") for d in weapons))
        report_lines.append(f"- Types: {', '.join(weapon_types)}")
        report_lines.append(f"")
    
    # Violations
    if violations:
        report_lines.append(f"### 🚨 Policy Violations")
        report_lines.append(f"")
        for v in violations:
            criterion = v["criterion"]
            severity = v["severity"]
            ranges = v.get("timestamp_ranges", [])
            
            severity_icon = "🔴" if severity == "high" else "🟡"
            report_lines.append(f"{severity_icon} **{criterion.title()}** ({severity} severity)")
            if ranges:
                time_str = ", ".join([f"{r[0]:.1f}s-{r[1]:.1f}s" for r in ranges[:5]])
                report_lines.append(f"- Timestamps: {time_str}")
            report_lines.append(f"")
    
    # Fusion Debug
    if fusion_debug:
        report_lines.append(f"### 🔧 Fusion Analysis")
        report_lines.append(f"")
        rationale = fusion_debug.get("verdict_rationale", "No rationale available")
        report_lines.append(f"{rationale}")
        report_lines.append(f"")
    
    # Recommendations
    report_lines.append(f"### 💡 Recommendations")
    report_lines.append(f"")
    if verdict == "SAFE":
        report_lines.append(f"✅ This content is suitable for general audiences including children.")
    elif verdict == "CAUTION":
        report_lines.append(f"⚠️ Parental guidance suggested. Consider adding content warnings for:")
        for crit, score in criterion_scores.items():
            if score >= 0.3:
                report_lines.append(f"- {crit.title()}")
    elif verdict == "UNSAFE":
        report_lines.append(f"🚫 This content is not suitable for minors and should be:")
        report_lines.append(f"- Age-restricted")
        report_lines.append(f"- Reviewed by human moderator")
        report_lines.append(f"- Potentially removed if policy-violating")
    else:
        report_lines.append(f"🔍 Manual review required. Key areas to examine:")
        for crit, score in criterion_scores.items():
            if score >= 0.3:
                report_lines.append(f"- {crit.title()} signals (score: {score:.2f})")
    report_lines.append(f"")
    
    report_lines.append(f"---")
    report_lines.append(f"")
    report_lines.append(f"*Analysis by Judex Safety System • {duration:.1f}s video • Multi-model fusion with reliability weighting*")
    
    return "\n".join(report_lines)
