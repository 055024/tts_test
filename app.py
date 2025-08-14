import json
import os
import time
import threading
import queue
import logging
import sounddevice as sd
import numpy as np
from faster_whisper import WhisperModel
from playsound import playsound
from pynput import keyboard
from rapidfuzz import process, fuzz

# --- Configuration ---
AUDIO_DIR = "audio"
SCRIPT_CUES_FILE = "script_cues.json"
SAMPLE_RATE = 16000  # Whisper model expects 16kHz
CHUNK_SIZE = 1024    # Audio buffer size
WHISPER_MODEL_SIZE = "base"  # or "small", "medium", "large"
LANGUAGE = "en"  # Hindi for transcription
SILENCE_THRESHOLD = 0.01  # Adjust as needed
SILENCE_DURATION = 1.0  # Seconds of silence to consider end of utterance
MATCH_COOLDOWN = 5  # Seconds to ignore new matches after a playback
MATCH_THRESHOLD_SCORE = 60  # Fuzzy match threshold (0-100)

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s.%(msecs)03d] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger(__name__)

# --- Global Variables ---
audio_queue = queue.Queue()
transcription_queue = queue.Queue()
playback_queue = queue.Queue()
script_cues = []
cue_texts = []
last_played_cue_id = None
last_match_time = 0
current_cue_index = -1  # For manual override
keyboard_listener = None
is_playing = False  # Flag to suspend listening during playback

# --- Load Script Cues ---
def load_script_cues():
    global script_cues, cue_texts
    try:
        with open(SCRIPT_CUES_FILE, 'r', encoding='utf-8') as f:
            script_cues = json.load(f)
        cue_texts = [cue['hi_text'] for cue in script_cues]
        log.info(f"Loaded {len(script_cues)} script cues from {SCRIPT_CUES_FILE}")
    except FileNotFoundError:
        log.error(f"Error: {SCRIPT_CUES_FILE} not found.")
        exit(1)
    except json.JSONDecodeError:
        log.error(f"Error: Could not decode JSON from {SCRIPT_CUES_FILE}.")
        exit(1)

# --- Audio Recording Thread ---
def audio_recorder():
    log.info("Starting audio recording...")
    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='float32', blocksize=CHUNK_SIZE) as stream:
            while True:
                if is_playing:
                    time.sleep(0.1)
                    continue
                audio_chunk, overflowed = stream.read(CHUNK_SIZE)
                if overflowed:
                    log.warning("Audio input buffer overflowed!")
                audio_queue.put(audio_chunk.flatten())
    except Exception as e:
        log.error(f"Audio recording error: {e}")

# --- Transcription Thread ---
def transcriber():
    log.info(f"Loading Whisper model: {WHISPER_MODEL_SIZE}...")
    model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
    log.info("Whisper model loaded.")

    full_audio_buffer = np.array([])
    last_speech_time = time.time()

    while True:
        if is_playing:
            time.sleep(0.1)
            continue
        try:
            chunk = audio_queue.get(timeout=1)
            full_audio_buffer = np.concatenate((full_audio_buffer, chunk))
            rms = np.sqrt(np.mean(chunk ** 2))
            if rms > SILENCE_THRESHOLD:
                last_speech_time = time.time()

            if time.time() - last_speech_time > SILENCE_DURATION and full_audio_buffer.size:
                log.info("Silence detected, processing utterance...")
                segments, _ = model.transcribe(full_audio_buffer, language=LANGUAGE)
                text = " ".join(seg.text for seg in segments).strip()
                if text:
                    transcription_queue.put(text)
                full_audio_buffer = np.array([])
                last_speech_time = time.time()

        except queue.Empty:
            if full_audio_buffer.size and time.time() - last_speech_time > SILENCE_DURATION:
                log.info("Timeout/Silence, processing remaining utterance...")
                segments, _ = model.transcribe(full_audio_buffer, language=LANGUAGE)
                text = " ".join(seg.text for seg in segments).strip()
                if text:
                    transcription_queue.put(text)
                full_audio_buffer = np.array([])
                last_speech_time = time.time()
        except Exception as e:
            log.error(f"Transcription error: {e}")

# --- Playback Thread ---
def audio_playback():
    global is_playing
    while True:
        try:
            audio_file = playback_queue.get()
            if audio_file:
                is_playing = True
                log.info(f"Playing '{audio_file}'...")
                playsound(audio_file, block=True)
                is_playing = False
        except Exception as e:
            log.error(f"Audio playback error: {e}")

# --- Main Logic Thread ---
def main_logic():
    global last_match_time, last_played_cue_id, current_cue_index

    while True:
        if is_playing:
            time.sleep(0.1)
            continue
        try:
            transcribed_text = transcription_queue.get(timeout=1)
            log.info(f"Detected: '{transcribed_text}'")

            if time.time() - last_match_time < MATCH_COOLDOWN:
                continue

            match, score, idx = process.extractOne(
                transcribed_text, cue_texts, scorer=fuzz.partial_ratio
            )
            log.info(f"Fuzzy match '{match}' (score {score})")

            if score >= MATCH_THRESHOLD_SCORE:
                cue = script_cues[idx]
                current_cue_index = idx
                log.info(f"Match! Cue {cue['id']} → {cue['en_audio']}")
                playback_queue.put(os.path.join(AUDIO_DIR, cue['en_audio'].split('/')[-1]))
                last_match_time = time.time()
                last_played_cue_id = cue['id']
        except queue.Empty:
            continue
        except Exception as e:
            log.error(f"Main logic error: {e}")

# --- Manual Override Hotkeys ---
def on_press(key):
    global current_cue_index, last_match_time, last_played_cue_id
    try:
        if key == keyboard.Key.esc:
            return False
        if hasattr(key, 'char'):
            c = key.char.lower()
            if c in ('n', 'p', 'r'):
                if c == 'n' and current_cue_index < len(script_cues) - 1:
                    current_cue_index += 1
                elif c == 'p' and current_cue_index > 0:
                    current_cue_index -= 1
                elif c == 'r' and last_played_cue_id is not None:
                    current_cue_index = next((i for i, cue in enumerate(script_cues) if cue['id'] == last_played_cue_id), current_cue_index)
                cue = script_cues[current_cue_index]
                log.info(f"Manual '{c}' → Cue {cue['id']} playing {cue['en_audio']}")
                playback_queue.put(os.path.join(AUDIO_DIR, cue['en_audio'].split('/')[-1]))
                last_played_cue_id = cue['id']
                last_match_time = time.time()
    except Exception:
        pass


def start_keyboard_listener():
    global keyboard_listener
    keyboard_listener = keyboard.Listener(on_press=on_press)
    keyboard_listener.start()
    log.info("Keyboard listener started. Press N/P/R or Esc.")

# --- Main Execution ---
if __name__ == "__main__":
    load_script_cues()

    threading.Thread(target=audio_recorder, daemon=True).start()
    threading.Thread(target=transcriber, daemon=True).start()
    threading.Thread(target=audio_playback, daemon=True).start()
    threading.Thread(target=main_logic, daemon=True).start()

    start_keyboard_listener()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Application interrupted by user.")
    finally:
        if keyboard_listener:
            keyboard_listener.stop()
        log.info("Application shutting down.")