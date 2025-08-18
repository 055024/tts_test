import json
import os
import time
import threading
import queue
import logging
import sounddevice as sd
import numpy as np
from faster_whisper import WhisperModel
import simpleaudio as sa
import wave
from pynput import keyboard
from rapidfuzz import process, fuzz

# --- Configuration ---
AUDIO_DIR = "audio"
SCRIPT_CUES_FILE = "script_cues.json"
SAMPLE_RATE = 16000  # Whisper model expects 16kHz
CHUNK_SIZE = 1024    # Audio buffer size
WHISPER_MODEL_SIZE = "base"  # or "small", "medium", "large"
LANGUAGE = "hi"  # Hindi for transcription
SILENCE_THRESHOLD = 0.01  # Adjust as needed
SILENCE_DURATION = 5.0  # Seconds of silence to consider end of utterance
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
play_obj = None   # simpleaudio playback object

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
    global play_obj
    log.info(f"Loading Whisper model: {WHISPER_MODEL_SIZE}...")
    model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
    # model = WhisperModel(WHISPER_MODEL_SIZE, device="cuda", compute_type="float16")

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
                # interrupt current playback on voice detected
                if play_obj and play_obj.is_playing():
                    log.info("Voice detected: interrupting playback.")
                    play_obj.stop()
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
    global is_playing, play_obj
    while True:
        try:
            audio_file = playback_queue.get()
            if audio_file:
                is_playing = True
                # stop any existing playback
                if play_obj and play_obj.is_playing():
                    play_obj.stop()
                log.info(f"Playing '{audio_file}'...")
                # load WAV file
                wf = wave.open(audio_file, 'rb')
                data = wf.readframes(wf.getnframes())
                play_obj = sa.play_buffer(
                    data,
                    num_channels=wf.getnchannels(),
                    bytes_per_sample=wf.getsampwidth(),
                    sample_rate=wf.getframerate()
                )
                wf.close()
                play_obj.wait_done() # Wait until playback is finished
                is_playing = False
        except Exception as e:
            log.error(f"Audio playback error: {e}")

# --- Main Logic Thread ---
def main_logic(app_instance):
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
                try:
                    app_instance._update_last_match(cue['id'], int(score))
                except Exception:
                    pass
        except queue.Empty:
            continue
        except Exception as e:
            log.error(f"Main logic error: {e}")

# --- Manual Override Hotkeys ---
def on_press(key):
    global current_cue_index, last_match_time, last_played_cue_id, play_obj
    try:
        if key == keyboard.Key.esc:
            return False
        if hasattr(key, 'char'):
            c = key.char.lower()
            # interrupt playback on any manual key
            if play_obj and play_obj.is_playing():
                play_obj.stop()
            if c == 'n' and current_cue_index < len(script_cues) - 1:
                current_cue_index += 1
                cue = script_cues[current_cue_index]
                log.info(f"[⏩ Next] Playing cue {cue['id']} → '{cue['en_audio']}'")
                playback_queue.put(os.path.join(AUDIO_DIR, cue['en_audio']))
                last_played_cue_id = cue['id']
                last_match_time = time.time()
            elif c == 'p' and current_cue_index > 0:
                current_cue_index -= 1
                cue = script_cues[current_cue_index]
                log.info(f"[⏪ Previous] Playing cue {cue['id']} → '{cue['en_audio']}'")
                playback_queue.put(os.path.join(AUDIO_DIR, cue['en_audio']))
                last_played_cue_id = cue['id']
                last_match_time = time.time()
            elif c == 'r' and last_played_cue_id is not None:
                cue = next((c for c in script_cues if c['id'] == last_played_cue_id), None)
                if cue:
                    log.info(f"[🔁 Repeat] Repeating cue {cue['id']} → '{cue['en_audio']}'")
                    playback_queue.put(os.path.join(AUDIO_DIR, cue['en_audio']))
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

    # Create the AppAPI instance first
    global app
    app = AppAPI()

    threading.Thread(target=audio_recorder, daemon=True).start()
    threading.Thread(target=transcriber, daemon=True).start()
    threading.Thread(target=audio_playback, daemon=True).start()
    threading.Thread(target=main_logic, args=(app,), daemon=True).start()

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
# ==== Web Adapter for FastAPI ====
_ADAPTER_MODEL = None  # lazy-init faster-whisper

def _get_model():
    global _ADAPTER_MODEL
    if _ADAPTER_MODEL is None:
        log.info(f"[Adapter] Loading Whisper model: {WHISPER_MODEL_SIZE} ...")
        _ADAPTER_MODEL = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
        log.info("[Adapter] Whisper model ready.")
    return _ADAPTER_MODEL

class AppAPI:
    def __init__(self):
        self.start_ts = time.time()
        self.listening_paused = False
        self.last_spoken_text = ""
        self.last_match = {"id": None, "score": None, "spoken_text": ""}
        load_script_cues()
        # keep only playback + matcher threads for web-ingest
        threading.Thread(target=audio_playback, daemon=True).start()
        threading.Thread(target=main_logic, args=(self,), daemon=True).start()

    # called by main_logic to record matches
    def _update_last_match(self, cue_id, score):
        self.last_match.update({"id": cue_id, "score": score})

    def status(self):
        uptime = int(time.time() - self.start_ts)
        return {
            "current_cue_index": current_cue_index,
            "last_match": {
                "id": self.last_match["id"],
                "score": self.last_match["score"],
                "spoken_text": self.last_spoken_text or ""
            },
            "is_listening": not self.listening_paused,
            "is_playing": is_playing,
            "uptime_s": uptime,
            "total_cues": len(script_cues),
        }

    def process_command(self, data: dict):
        global current_cue_index, last_played_cue_id, last_match_time
        cmd = (data or {}).get("cmd", "").lower()
        if cmd == "pause_listen":
            self.listening_paused = True
            return {"ok": True, "listening": False}
        if cmd == "resume_listen":
            self.listening_paused = False
            return {"ok": True, "listening": True}
        if cmd in ("next", "prev", "replay"):
            # implement manual stepping using existing queues
            if cmd == "next" and current_cue_index < len(script_cues) - 1:
                current_cue_index += 1
            elif cmd == "prev" and current_cue_index > 0:
                current_cue_index -= 1
            elif cmd == "replay" and last_played_cue_id is not None:
                current_cue_index = next((i for i, c in enumerate(script_cues)
                                          if c["id"] == last_played_cue_id), current_cue_index)
            cue = script_cues[current_cue_index]
            playback_queue.put(os.path.join(AUDIO_DIR, cue["en_audio"].split("/")[-1]))
            last_played_cue_id = cue["id"]
            last_match_time = time.time()
            return {"ok": True, "cue_id": cue["id"]}
        return {"ok": False, "error": f"unknown cmd '{cmd}'"}

    def manual_override(self, data: dict):
        global current_cue_index, last_played_cue_id, last_match_time
        cue_id = int((data or {}).get("cue_id", -1))
        idx = next((i for i, c in enumerate(script_cues) if c["id"] == cue_id), -1)
        if idx < 0:
            return {"ok": False, "error": "cue not found"}
        current_cue_index = idx
        cue = script_cues[idx]
        playback_queue.put(os.path.join(AUDIO_DIR, cue["en_audio"].split("/")[-1]))
        last_played_cue_id = cue_id
        last_match_time = time.time()
        return {"ok": True, "cue_id": cue_id}

    def process_audio(self, file_path: str):
        # Accept webm/wav, transcribe asynchronously, push text to queue
        if self.listening_paused:
            return {"ok": True, "ignored": "listening paused"}

        def _worker(p):
            try:
                model = _get_model()
                segments, _ = model.transcribe(p, language=LANGUAGE)
                text = " ".join(seg.text for seg in segments).strip()
                if text:
                    self.last_spoken_text = text
                    transcription_queue.put(text)
            except Exception as e:
                log.error(f"[Adapter] process_audio error: {e}")
            finally:
                # Ensure temporary WAV is removed after we're done
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except Exception as _:
                    pass

        threading.Thread(target=_worker, args=(file_path,), daemon=True).start()
        return {"ok": True}

# expose singleton for remote_api.py
app = AppAPI()