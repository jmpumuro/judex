"""
Text moderation node for transcript and OCR text.
"""
from app.pipeline.state import PipelineState
from app.core.logging import get_logger
from app.models import get_text_moderator
from app.utils.hashing import generate_asr_id
from app.utils.progress import send_progress, save_stage_output, format_stage_output

logger = get_logger("node.text_moderation")


def run_text_moderation(state: PipelineState) -> PipelineState:
    """Run text moderation on transcript and OCR text."""
    logger.info("=== Text Moderation Node ===")
    
    send_progress(state.get("progress_callback"), "text_moderation", "Loading moderation models", 70)
    
    transcript = state.get("transcript", {})
    ocr_results = state.get("ocr_results", [])
    
    moderator = get_text_moderator()
    
    # Moderate transcript chunks
    transcript_moderation = []
    
    chunks = transcript.get("chunks", [])
    if chunks:
        send_progress(state.get("progress_callback"), "text_moderation", f"Moderating {len(chunks)} transcript chunks", 80)
        
        logger.info(f"Moderating {len(chunks)} transcript chunks")
        
        for chunk in chunks:
            text = chunk["text"]
            timestamp = (chunk["start_time"] + chunk["end_time"]) / 2
            
            result = moderator.moderate_text(text, timestamp)
            result["id"] = generate_asr_id(chunk["chunk_index"])
            result["start_time"] = chunk["start_time"]
            result["end_time"] = chunk["end_time"]
            
            transcript_moderation.append(result)
            
            # Log high scores
            if any([
                result["profanity_score"] > 0.5,
                result["violence_score"] > 0.5,
                result["sexual_score"] > 0.5,
                result["drugs_score"] > 0.5,
                result["hate_score"] > 0.5
            ]):
                logger.info(f"High moderation scores at {timestamp:.1f}s: {result}")
    
    state["transcript_moderation"] = transcript_moderation
    
    # Moderate OCR text
    ocr_moderation = []
    
    if ocr_results:
        logger.info(f"Moderating {len(ocr_results)} OCR texts")
        
        for ocr_item in ocr_results:
            text = ocr_item["text"]
            timestamp = ocr_item["timestamp"]
            
            result = moderator.moderate_text(text, timestamp)
            result["id"] = ocr_item["id"]
            
            ocr_moderation.append(result)
            
            # Log high scores
            if any([
                result["profanity_score"] > 0.5,
                result["violence_score"] > 0.5,
                result["sexual_score"] > 0.5,
                result["drugs_score"] > 0.5,
                result["hate_score"] > 0.5
            ]):
                logger.info(f"High OCR moderation scores at {timestamp:.1f}s: {result}")
    
    state["ocr_moderation"] = ocr_moderation
    
    logger.info(f"Text moderation completed: {len(transcript_moderation)} transcript + {len(ocr_moderation)} OCR")
    
    # Save stage output for real-time retrieval
    # Find flagged content
    flagged_transcript = [
        m for m in transcript_moderation 
        if any([m.get("profanity_score", 0) > 0.5, m.get("violence_score", 0) > 0.5,
                m.get("sexual_score", 0) > 0.5, m.get("drugs_score", 0) > 0.5, m.get("hate_score", 0) > 0.5])
    ]
    flagged_ocr = [
        m for m in ocr_moderation
        if any([m.get("profanity_score", 0) > 0.5, m.get("violence_score", 0) > 0.5,
                m.get("sexual_score", 0) > 0.5, m.get("drugs_score", 0) > 0.5, m.get("hate_score", 0) > 0.5])
    ]
    
    save_stage_output(state.get("video_id"), "text_moderation", format_stage_output(
        "text_moderation",
        transcript_chunks_analyzed=len(transcript_moderation),
        ocr_items_analyzed=len(ocr_moderation),
        flagged_transcript_count=len(flagged_transcript),
        flagged_ocr_count=len(flagged_ocr),
        # Include full moderation results for UI display
        transcript_moderation=[
            {
                "text": m.get("text", "")[:200],
                "start_time": m.get("start_time"),
                "end_time": m.get("end_time"),
                "profanity_score": round(m.get("profanity_score", 0), 3),
                "violence_score": round(m.get("violence_score", 0), 3),
                "sexual_score": round(m.get("sexual_score", 0), 3),
                "drugs_score": round(m.get("drugs_score", 0), 3),
                "hate_score": round(m.get("hate_score", 0), 3),
                "profanity_words": m.get("profanity_words", []),
                "sexual_words": m.get("sexual_words", [])
            }
            for m in transcript_moderation[:10]
        ],
        ocr_moderation=[
            {
                "text": m.get("text", "")[:100],
                "timestamp": m.get("timestamp"),
                "profanity_score": round(m.get("profanity_score", 0), 3),
                "violence_score": round(m.get("violence_score", 0), 3),
                "sexual_score": round(m.get("sexual_score", 0), 3),
                "drugs_score": round(m.get("drugs_score", 0), 3),
                "hate_score": round(m.get("hate_score", 0), 3)
            }
            for m in ocr_moderation[:10]
        ],
        # Legacy: flagged items for backward compatibility
        flagged_transcript=[
            {
                "text": m.get("text", "")[:100],
                "start_time": m.get("start_time"),
                "end_time": m.get("end_time"),
                "profanity": round(m.get("profanity_score", 0), 3),
                "violence": round(m.get("violence_score", 0), 3)
            }
            for m in flagged_transcript[:5]
        ],
        flagged_ocr=[
            {
                "text": m.get("text", "")[:100],
                "timestamp": m.get("timestamp")
            }
            for m in flagged_ocr[:5]
        ]
    ))
    
    return state
