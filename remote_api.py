#!/usr/bin/env python3
"""
Remote API adapter for the TTS trigger-to-playback system.
Provides HTTP endpoints to control the existing app.py backend without modifying it.
"""

import os
import time
import threading
import queue
import subprocess
import tempfile
import logging
from typing import Optional, Dict, Any
import numpy as np

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import uvicorn

# Import the existing app module
import app

# --- Configuration ---
API_TOKEN = os.getenv("API_TOKEN")  # Optional bearer token
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
BIND_HOST = os.getenv("BIND_HOST", "0.0.0.0")
BIND_PORT = int(os.getenv("BIND_PORT", "8001"))  # Changed default to 8001

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# --- Global State ---
command_queue = queue.Queue()
is_listening = True
is_frontend_mode = False
last_match_info = {"id": None, "score": 0.0, "spoken_text": ""}
start_time = time.time()

# --- Security ---
security = HTTPBearer(auto_error=False)

def verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    if API_TOKEN:
        if not credentials or credentials.credentials != API_TOKEN:
            raise HTTPException(status_code=401, detail="Invalid or missing token")
    return True

# --- Request Models ---
class CommandRequest(BaseModel):
    cmd: str
    arg: Optional[Any] = None

class ManualPlayRequest(BaseModel):
    cue_id: int

# --- FastAPI App ---
app_api = FastAPI(title="TTS Remote Controller", version="1.0.0")

# CORS middleware
app_api.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Command Processing Thread ---
def command_processor():
    """Process commands from the API queue and execute them on the app module."""
    global is_listening, last_match_info
    
    while True:
        try:
            cmd_data = command_queue.get(timeout=1)
            cmd = cmd_data["cmd"]
            
            log.info(f"Processing command: {cmd}")
            
            if cmd == "next":
                if app.current_cue_index < len(app.script_cues) - 1:
                    app.current_cue_index += 1
                    cue = app.script_cues[app.current_cue_index]
                    app.playback_queue.put(os.path.join(app.AUDIO_DIR, cue['en_audio'].split('/')[-1]))
                    app.last_played_cue_id = cue['id']
                    app.last_match_time = time.time()
                    log.info(f"Next: Playing cue {cue['id']}")
                    
            elif cmd == "prev":
                if app.current_cue_index > 0:
                    app.current_cue_index -= 1
                    cue = app.script_cues[app.current_cue_index]
                    app.playback_queue.put(os.path.join(app.AUDIO_DIR, cue['en_audio'].split('/')[-1]))
                    app.last_played_cue_id = cue['id']
                    app.last_match_time = time.time()
                    log.info(f"Previous: Playing cue {cue['id']}")
                    
            elif cmd == "replay":
                if app.last_played_cue_id is not None:
                    cue = next((c for c in app.script_cues if c['id'] == app.last_played_cue_id), None)
                    if cue:
                        app.playback_queue.put(os.path.join(app.AUDIO_DIR, cue['en_audio'].split('/')[-1]))
                        app.last_match_time = time.time()
                        log.info(f"Replay: Playing cue {cue['id']}")
                        
            elif cmd == "pause_listen":
                is_listening = False
                log.info("Listening paused")
                
            elif cmd == "resume_listen":
                is_listening = True
                log.info("Listening resumed")
                
        except queue.Empty:
            continue
        except Exception as e:
            log.error(f"Command processing error: {e}")

# --- Audio Processing Functions ---
def convert_webm_to_pcm(webm_data: bytes) -> np.ndarray:
    """Convert WebM/Opus audio to 16kHz mono PCM using ffmpeg."""
    try:
        with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as temp_input:
            temp_input.write(webm_data)
            temp_input_path = temp_input.name
            
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_output:
            temp_output_path = temp_output.name
            
        # Convert using ffmpeg
        cmd = [
            'ffmpeg', '-y', '-i', temp_input_path,
            '-ar', '16000', '-ac', '1', '-f', 'wav',
            temp_output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log.error(f"FFmpeg error: {result.stderr}")
            raise Exception("Audio conversion failed")
            
        # Read the converted audio
        import wave
        with wave.open(temp_output_path, 'rb') as wav_file:
            frames = wav_file.readframes(wav_file.getnframes())
            audio_data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
            
        # Cleanup
        os.unlink(temp_input_path)
        os.unlink(temp_output_path)
        
        return audio_data
        
    except Exception as e:
        log.error(f"Audio conversion error: {e}")
        raise

def feed_audio_to_app(audio_data: np.ndarray):
    """Feed converted audio data to the app's audio queue in chunks."""
    chunk_size = app.CHUNK_SIZE
    for i in range(0, len(audio_data), chunk_size):
        chunk = audio_data[i:i + chunk_size]
        if len(chunk) < chunk_size:
            # Pad the last chunk if necessary
            chunk = np.pad(chunk, (0, chunk_size - len(chunk)), 'constant')
        app.audio_queue.put(chunk)

# --- API Endpoints ---
@app_api.post("/api/cmd")
async def execute_command(request: CommandRequest, _: bool = Depends(verify_token)):
    """Execute a control command (next, prev, replay, pause_listen, resume_listen)."""
    valid_commands = ["next", "prev", "replay", "pause_listen", "resume_listen"]
    
    if request.cmd not in valid_commands:
        raise HTTPException(status_code=400, detail=f"Invalid command. Valid: {valid_commands}")
    
    command_queue.put({"cmd": request.cmd, "arg": request.arg})
    return {"status": "ok", "command": request.cmd}

@app_api.post("/api/manual")
async def manual_play(request: ManualPlayRequest, _: bool = Depends(verify_token)):
    """Manually play a cue by ID."""
    cue = next((c for c in app.script_cues if c['id'] == request.cue_id), None)
    if not cue:
        raise HTTPException(status_code=404, detail=f"Cue ID {request.cue_id} not found")
    
    app.current_cue_index = next((i for i, c in enumerate(app.script_cues) if c['id'] == request.cue_id), -1)
    app.playback_queue.put(os.path.join(app.AUDIO_DIR, cue['en_audio'].split('/')[-1]))
    app.last_played_cue_id = cue['id']
    app.last_match_time = time.time()
    
    log.info(f"Manual play: Cue {cue['id']} → {cue['en_audio']}")
    return {"status": "ok", "cue_id": request.cue_id, "audio_file": cue['en_audio']}

@app_api.post("/api/ingest")
async def ingest_audio(request: Request, _: bool = Depends(verify_token)):
    """Ingest audio data from browser and feed to the processing pipeline."""
    global is_frontend_mode
    
    try:
        # Read the raw audio data
        audio_data = await request.body()
        if not audio_data:
            raise HTTPException(status_code=400, detail="No audio data received")
        
        # Set frontend mode to disable local mic
        is_frontend_mode = True
        
        # Convert audio to PCM format
        content_type = request.headers.get("content-type", "")
        
        if "audio/webm" in content_type or "audio/ogg" in content_type:
            pcm_data = convert_webm_to_pcm(audio_data)
        elif "audio/wav" in content_type:
            # Assume it's already in the right format, just convert to float32
            pcm_data = np.frombuffer(audio_data[44:], dtype=np.int16).astype(np.float32) / 32768.0
        else:
            # Try to convert anyway
            pcm_data = convert_webm_to_pcm(audio_data)
        
        # Feed to the app's audio processing pipeline
        feed_audio_to_app(pcm_data)
        
        return {"status": "ok", "samples_received": len(pcm_data)}
        
    except Exception as e:
        log.error(f"Audio ingest error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app_api.get("/api/status")
async def get_status(_: bool = Depends(verify_token)):
    """Get current system status."""
    return {
        "current_cue_index": app.current_cue_index,
        "last_match": {
            "id": last_match_info["id"],
            "score": last_match_info["score"],
            "spoken_text": last_match_info["spoken_text"]
        },
        "is_listening": is_listening and not is_frontend_mode,
        "is_playing": app.is_playing,
        "uptime_s": int(time.time() - start_time),
        "total_cues": len(app.script_cues),
        "frontend_mode": is_frontend_mode
    }

# --- Enhanced Main Logic Monitor ---
def monitor_transcriptions():
    """Monitor transcription queue to capture match information for status API."""
    global last_match_info
    
    # We'll hook into the existing transcription processing
    original_main_logic = app.main_logic
    
    def enhanced_main_logic():
        global last_match_info
        
        while True:
            if app.is_playing or (is_frontend_mode and not is_listening):
                time.sleep(0.1)
                continue
            try:
                transcribed_text = app.transcription_queue.get(timeout=1)
                log.info(f"Detected: '{transcribed_text}'")
                
                # Update last match info
                last_match_info["spoken_text"] = transcribed_text
                
                if time.time() - app.last_match_time < app.MATCH_COOLDOWN:
                    continue
                
                from rapidfuzz import process, fuzz
                match, score, idx = process.extractOne(
                    transcribed_text, app.cue_texts, scorer=fuzz.partial_ratio
                )
                log.info(f"Fuzzy match '{match}' (score {score})")
                
                last_match_info["score"] = score
                
                if score >= app.MATCH_THRESHOLD_SCORE:
                    cue = app.script_cues[idx]
                    app.current_cue_index = idx
                    last_match_info["id"] = cue['id']
                    log.info(f"Match! Cue {cue['id']} → {cue['en_audio']}")
                    app.playback_queue.put(os.path.join(app.AUDIO_DIR, cue['en_audio'].split('/')[-1]))
                    app.last_match_time = time.time()
                    app.last_played_cue_id = cue['id']
            except queue.Empty:
                continue
            except Exception as e:
                log.error(f"Enhanced main logic error: {e}")
    
    # Replace the main logic function
    app.main_logic = enhanced_main_logic

# --- Modified Audio Recorder ---
def setup_frontend_audio_recorder():
    """Setup audio recorder that can be disabled when in frontend mode."""
    original_audio_recorder = app.audio_recorder
    
    def frontend_aware_audio_recorder():
        log.info("Starting frontend-aware audio recording...")
        try:
            import sounddevice as sd
            # Test if audio device is available
            try:
                sd.check_input_settings(samplerate=app.SAMPLE_RATE, channels=1, dtype='float32')
            except Exception as device_error:
                log.warning(f"Audio device not available: {device_error}")
                log.info("Audio recording disabled - will rely on frontend audio ingest only")
                while True:
                    time.sleep(1)  # Keep thread alive but don't try to record
                return
                
            with sd.InputStream(samplerate=app.SAMPLE_RATE, channels=1, dtype='float32', blocksize=app.CHUNK_SIZE) as stream:
                while True:
                    if app.is_playing or is_frontend_mode:
                        time.sleep(0.1)
                        continue
                    audio_chunk, overflowed = stream.read(app.CHUNK_SIZE)
                    if overflowed:
                        log.warning("Audio input buffer overflowed!")
                    app.audio_queue.put(audio_chunk.flatten())
        except Exception as e:
            log.error(f"Audio recording error: {e}")
            log.info("Continuing without local audio recording - frontend audio ingest will still work")
            while True:
                time.sleep(1)  # Keep thread alive
    
    app.audio_recorder = frontend_aware_audio_recorder

# --- Startup ---
def start_api_server():
    """Start the API server and background threads."""
    log.info("Starting TTS Remote API server...")
    
    # Load script cues
    app.load_script_cues()
    
    # Setup enhanced monitoring
    monitor_transcriptions()
    setup_frontend_audio_recorder()
    
    # Start the original app threads
    threading.Thread(target=app.audio_recorder, daemon=True).start()
    threading.Thread(target=app.transcriber, daemon=True).start()
    threading.Thread(target=app.audio_playback, daemon=True).start()
    threading.Thread(target=app.main_logic, daemon=True).start()
    
    # Start our command processor
    threading.Thread(target=command_processor, daemon=True).start()
    
    log.info(f"API server starting on {BIND_HOST}:{BIND_PORT}")
    log.info(f"CORS origins: {CORS_ORIGINS}")
    log.info(f"Authentication: {'Enabled' if API_TOKEN else 'Disabled'}")
    
    # Start the FastAPI server
    uvicorn.run(app_api, host=BIND_HOST, port=BIND_PORT, log_level="info")

if __name__ == "__main__":
    start_api_server()