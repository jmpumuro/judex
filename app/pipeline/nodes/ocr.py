"""
OCR extraction node using Tesseract (lightweight alternative to EasyOCR).
"""
from pathlib import Path
from typing import List, Dict, Any
import cv2
import pytesseract
from app.pipeline.state import PipelineState
from app.core.logging import get_logger
from app.utils.hashing import generate_ocr_id
from app.utils.progress import send_progress, save_stage_output, format_stage_output

logger = get_logger("node.ocr")


def preprocess_image_for_ocr(image_path: str) -> Any:
    """Preprocess image to improve OCR accuracy."""
    import numpy as np
    
    # Read image
    img = cv2.imread(image_path)
    
    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Apply thresholding to get a binary image
    # Otsu's thresholding automatically determines optimal threshold
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # Denoise
    denoised = cv2.fastNlMeansDenoising(binary, None, 10, 7, 21)
    
    return denoised


def extract_text_tesseract(image_path: str) -> List[Dict[str, Any]]:
    """
    Extract text from image using Tesseract OCR.
    Returns list of detected text with bounding boxes and confidence.
    """
    try:
        # Preprocess image
        processed_img = preprocess_image_for_ocr(image_path)
        
        # Use Tesseract to get detailed data including bounding boxes
        data = pytesseract.image_to_data(processed_img, output_type=pytesseract.Output.DICT)
        
        # Extract text with confidence > 30
        detections = []
        n_boxes = len(data['text'])
        
        for i in range(n_boxes):
            text = data['text'][i].strip()
            conf = int(data['conf'][i])
            
            # Filter: confidence > 30 and text length > 1
            if conf > 30 and len(text) > 1:
                x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
                
                detections.append({
                    "text": text,
                    "confidence": conf / 100.0,  # Normalize to 0-1
                    "bbox": [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
                })
        
        return detections
    
    except Exception as e:
        logger.error(f"Tesseract OCR failed on {image_path}: {e}")
        return []


def run_ocr(state: PipelineState) -> PipelineState:
    """Run OCR on sampled frames using Tesseract."""
    logger.info("=== OCR Node (Tesseract) ===")
    
    send_progress(state.get("progress_callback"), "ocr_extraction", "Preparing OCR analysis", 60)
    
    sampled_frames = state.get("sampled_frames", [])
    policy_config = state.get("policy_config", {})
    
    if not sampled_frames:
        logger.warning("No sampled frames available")
        return state
    
    # Sample frames for OCR (not every frame, too expensive)
    # Reduced interval for better text capture
    ocr_interval_sec = policy_config.get("ocr_interval", 1.5)  # More frequent sampling
    sampling_fps = policy_config.get("sampling_fps", 1.0)
    
    # Select frames at OCR interval
    frame_interval = int(ocr_interval_sec * sampling_fps)
    if frame_interval < 1:
        frame_interval = 1
    
    ocr_frames = sampled_frames[::frame_interval]
    
    if not ocr_frames:
        ocr_frames = sampled_frames[:5]  # At least first 5 frames
    
    logger.info(f"Running Tesseract OCR on {len(ocr_frames)} frames (interval: {ocr_interval_sec}s)")
    
    send_progress(state.get("progress_callback"), "ocr_extraction", f"Extracting text from {len(ocr_frames)} frames", 75)
    
    ocr_results = []
    frames_with_text = 0
    
    for frame_info in ocr_frames:
        frame_path = frame_info["path"]
        timestamp = frame_info["timestamp"]
        frame_index = frame_info["frame_index"]
        
        try:
            # Run Tesseract OCR
            detections = extract_text_tesseract(frame_path)
            
            if detections:
                combined_text = " ".join([d["text"] for d in detections])
                
                ocr_results.append({
                    "id": generate_ocr_id(frame_index),
                    "timestamp": timestamp,
                    "frame_index": frame_index,
                    "text": combined_text,
                    "detections": detections,
                    "detection_count": len(detections)
                })
                
                frames_with_text += 1
                logger.info(f"Frame {frame_index} ({timestamp:.1f}s): OCR found {len(detections)} text(s) - '{combined_text[:80]}{'...' if len(combined_text) > 80 else ''}'")
        
        except Exception as e:
            logger.warning(f"OCR failed on frame {frame_index}: {e}")
    
    state["ocr_results"] = ocr_results
    
    logger.info(f"OCR completed: {frames_with_text}/{len(ocr_frames)} frames with text, {sum(r['detection_count'] for r in ocr_results)} total detections")
    
    # Save stage output for real-time retrieval
    save_stage_output(state.get("video_id"), "ocr", format_stage_output(
        "ocr",
        frames_analyzed=len(ocr_frames),
        frames_with_text=frames_with_text,
        total_detections=sum(r['detection_count'] for r in ocr_results),
        texts=[r['text'] for r in ocr_results[:10]]  # First 10 texts
    ))
    
    return state
