# import json
# import os
# import time
# import threading
# import queue
# import logging
# import sounddevice as sd
# import numpy as np
# from faster_whisper import WhisperModel
# from playsound import playsound
# from pynput import keyboard

# # --- Configuration ---
# AUDIO_DIR = "audio"
# SCRIPT_CUES_FILE = "script_cues.json"
# SAMPLE_RATE = 16000  # Whisper model expects 16kHz
# CHUNK_SIZE = 1024    # Audio buffer size
# WHISPER_MODEL_SIZE = "base" # You can change this to "small", "medium", "large"
# LANGUAGE = "en" # English for transcription
# SILENCE_THRESHOLD = 0.01 # Adjust as needed
# SILENCE_DURATION = 1.0 # Seconds of silence to consider end of utterance
# MATCH_COOLDOWN = 5 # Seconds to ignore new matches after a playback

# # --- Logging Setup ---
# logging.basicConfig(level=logging.INFO,
#                     format='[%(asctime)s.%(msecs)03d] %(message)s',
#                     datefmt='%H:%M:%S')
# log = logging.getLogger(__name__)

# # --- Global Variables ---
# audio_queue = queue.Queue()
# transcription_queue = queue.Queue()
# playback_queue = queue.Queue()
# script_cues = []
# last_played_cue_id = None
# last_match_time = 0
# current_cue_index = -1 # For manual override
# keyboard_listener = None

# # --- Load Script Cues ---
# def load_script_cues():
#     global script_cues
#     try:
#         with open(SCRIPT_CUES_FILE, 'r', encoding='utf-8') as f:
#             script_cues = json.load(f)
#         log.info(f"Loaded {len(script_cues)} script cues from {SCRIPT_CUES_FILE}")
#     except FileNotFoundError:
#         log.error(f"Error: {SCRIPT_CUES_FILE} not found.")
#         exit(1)
#     except json.JSONDecodeError:
#         log.error(f"Error: Could not decode JSON from {SCRIPT_CUES_FILE}.")
#         exit(1)

# # --- Audio Recording Thread ---
# def audio_recorder():
#     log.info("Starting audio recording...")
#     try:
#         with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='float32', blocksize=CHUNK_SIZE) as stream:
#             while True:
#                 audio_chunk, overflowed = stream.read(CHUNK_SIZE)
#                 if overflowed:
#                     log.warning("Audio input buffer overflowed!")
#                 audio_queue.put(audio_chunk.flatten())
#     except Exception as e:
#         log.error(f"Audio recording error: {e}")

# # --- Transcription Thread ---
# def transcriber():
#     log.info(f"Loading Whisper model: {WHISPER_MODEL_SIZE}...")
#     model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8") # Use "cuda" if you have a GPU
#     log.info("Whisper model loaded.")

#     full_audio_buffer = np.array([])
#     last_speech_time = time.time()

#     while True:
#         try:
#             chunk = audio_queue.get(timeout=1) # Get audio chunk
#             full_audio_buffer = np.concatenate((full_audio_buffer, chunk))

#             # Simple VAD: Check if audio chunk contains speech
#             rms = np.sqrt(np.mean(chunk**2))
#             if rms > SILENCE_THRESHOLD:
#                 last_speech_time = time.time()

#             # If silence detected for a duration, process the accumulated audio
#             if time.time() - last_speech_time > SILENCE_DURATION and len(full_audio_buffer) > 0:
#                 log.info("Silence detected, processing utterance...")
#                 segments, info = model.transcribe(full_audio_buffer, language=LANGUAGE)
#                 transcribed_text = " ".join([segment.text for segment in segments])
#                 if transcribed_text.strip():
#                     transcription_queue.put(transcribed_text.strip())
#                 full_audio_buffer = np.array([]) # Reset buffer
#                 last_speech_time = time.time() # Reset speech time

#         except queue.Empty:
#             # If no audio for a while, and there's accumulated audio, process it
#             if len(full_audio_buffer) > 0 and time.time() - last_speech_time > SILENCE_DURATION:
#                 log.info("Timeout/Silence, processing remaining utterance...")
#                 segments, info = model.transcribe(full_audio_buffer, language=LANGUAGE)
#                 transcribed_text = " ".join([segment.text for segment in segments])
#                 if transcribed_text.strip():
#                     transcription_queue.put(transcribed_text.strip())
#                 full_audio_buffer = np.array([])
#                 last_speech_time = time.time()
#         except Exception as e:
#             log.error(f"Transcription error: {e}")

# # --- Playback Thread ---
# def audio_playback():
#     while True:
#         try:
#             audio_file = playback_queue.get()
#             if audio_file:
#                 log.info(f"Playing '{audio_file}'...")
#                 playsound(audio_file, block=False) # Non-blocking playback
#                 log.info(f"Finished playing '{audio_file}'.")
#         except Exception as e:
#             log.error(f"Audio playback error: {e}")

# # --- Main Logic Thread ---
# def main_logic():
#     global last_match_time, last_played_cue_id, current_cue_index

#     while True:
#         try:
#             transcribed_text = transcription_queue.get(timeout=1)
#             log.info(f"[⏱️ {time.strftime('%H:%M:%S', time.gmtime(time.time()))}] Detected: '{transcribed_text}'")

#             if time.time() - last_match_time < MATCH_COOLDOWN:
#                 log.info("Ignoring match due to cooldown period.")
#                 continue

#             # Extract first 1-2 tokens (normalized)
#             tokens = transcribed_text.lower().split()[:2]

#             matched_cue = None
#             for i, cue in enumerate(script_cues):
#                 normalized_first_tokens = [t.lower() for t in cue["first_tokens"]]
#                 if len(tokens) >= len(normalized_first_tokens) and \
#                    all(tokens[j] == normalized_first_tokens[j] for j in range(len(normalized_first_tokens))):
#                     matched_cue = cue
#                     current_cue_index = i
#                     break

#             if matched_cue:
#                 log.info(f"[✅ Match] Found cue {matched_cue['id']} → Playing '{matched_cue['en_audio']}'")
#                 playback_queue.put(os.path.join(AUDIO_DIR, matched_cue['en_audio'].split('/')[-1]))
#                 last_match_time = time.time()
#                 last_played_cue_id = matched_cue['id']
#             else:
#                 log.info("No match found for detected text.")

#         except queue.Empty:
#             pass # No new transcription, continue loop
#         except Exception as e:
#             log.error(f"Main logic error: {e}")

# # --- Manual Override Hotkeys ---
# def on_press(key):
#     global current_cue_index, last_match_time, last_played_cue_id
#     try:
#         if key == keyboard.Key.esc:
#             log.info("Exiting application.")
#             return False # Stop listener

#         if key.char == 'n':
#             if current_cue_index < len(script_cues) - 1:
#                 current_cue_index += 1
#                 cue = script_cues[current_cue_index]
#                 log.info(f"[⏩ Next] Playing next cue {cue['id']} → '{cue['en_audio']}'")
#                 playback_queue.put(os.path.join(AUDIO_DIR, cue['en_audio'].split('/')[-1]))
#                 last_played_cue_id = cue['id']
#                 last_match_time = time.time() # Reset cooldown
#             else:
#                 log.info("Already at the last cue.")
#         elif key.char == 'p':
#             if current_cue_index > 0:
#                 current_cue_index -= 1
#                 cue = script_cues[current_cue_index]
#                 log.info(f"[⏪ Previous] Playing previous cue {cue['id']} → '{cue['en_audio']}'")
#                 playback_queue.put(os.path.join(AUDIO_DIR, cue['en_audio'].split('/')[-1]))
#                 last_played_cue_id = cue['id']
#                 last_match_time = time.time() # Reset cooldown
#             else:
#                 log.info("Already at the first cue.")
#         elif key.char == 'r':
#             if last_played_cue_id is not None:
#                 cue = next((c for c in script_cues if c['id'] == last_played_cue_id), None)
#                 if cue:
#                     log.info(f"[🔁 Repeat] Repeating last played cue {cue['id']} → '{cue['en_audio']}'")
#                     playback_queue.put(os.path.join(AUDIO_DIR, cue['en_audio'].split('/')[-1]))
#                     last_match_time = time.time() # Reset cooldown
#                 else:
#                     log.warning("Last played cue not found in script_cues.")
#             else:
#                 log.info("No cue has been played yet to repeat.")
#     except AttributeError:
#         pass # Ignore non-character keys

# def start_keyboard_listener():
#     global keyboard_listener
#     keyboard_listener = keyboard.Listener(on_press=on_press)
#     keyboard_listener.start()
#     log.info("Keyboard listener started. Press 'N' for next, 'P' for previous, 'R' for repeat, 'Esc' to exit.")

# # --- Main Execution ---
# if __name__ == "__main__":
#     load_script_cues()

#     # Start threads
#     audio_thread = threading.Thread(target=audio_recorder, daemon=True)
#     transcription_thread = threading.Thread(target=transcriber, daemon=True)
#     playback_thread = threading.Thread(target=audio_playback, daemon=True)
#     main_logic_thread = threading.Thread(target=main_logic, daemon=True)

#     audio_thread.start()
#     transcription_thread.start()
#     playback_thread.start()
#     main_logic_thread.start()

#     start_keyboard_listener()

#     # Keep main thread alive
#     try:
#         while True:
#             time.sleep(1)
#     except KeyboardInterrupt:
#         log.info("Application interrupted by user.")
#     finally:
#         if keyboard_listener:
#             keyboard_listener.stop()
#         log.info("Application shutting down.")

# import json
# import os
# import time
# import threading
# import queue
# import logging
# import sounddevice as sd
# import numpy as np
# from faster_whisper import WhisperModel
# from playsound import playsound
# from pynput import keyboard
# from rapidfuzz import process, fuzz

# # --- Configuration ---
# AUDIO_DIR              = "audio"
# SCRIPT_CUES_FILE       = "script_cues.json"
# SAMPLE_RATE            = 16000  # Whisper model expects 16kHz
# CHUNK_SIZE             = 1024   # Audio buffer size
# WHISPER_MODEL_SIZE     = "base" # You can change to "small", "medium", "large"
# LANGUAGE               = "en"   # Use English model for transcription
# SILENCE_THRESHOLD      = 0.005  # More sensitive detection
# SILENCE_DURATION       = 0.5    # Shorter silence for utterance end
# MATCH_COOLDOWN         = 5      # Seconds to ignore new matches after a playback
# MATCH_THRESHOLD_SCORE  = 70     # Fuzzy match score (%) threshold

# # --- Logging Setup ---
# logging.basicConfig(level=logging.INFO,
#                     format='[%(asctime)s.%(msecs)03d] %(message)s',
#                     datefmt='%H:%M:%S')
# log = logging.getLogger(__name__)

# # --- Global Variables ---
# audio_queue         = queue.Queue()
# transcription_queue = queue.Queue()
# playback_queue      = queue.Queue()
# script_cues         = []
# cue_texts           = []
# last_played_cue_id  = None
# last_match_time     = 0
# current_cue_index   = -1  # For manual override
# keyboard_listener   = None

# # --- Load Script Cues ---
# def load_script_cues():
#     global script_cues, cue_texts
#     try:
#         with open(SCRIPT_CUES_FILE, 'r', encoding='utf-8') as f:
#             script_cues = json.load(f)
#         cue_texts = [cue["hi_text"] for cue in script_cues]
#         log.info(f"Loaded {len(script_cues)} script cues from {SCRIPT_CUES_FILE}")
#     except FileNotFoundError:
#         log.error(f"Error: {SCRIPT_CUES_FILE} not found.")
#         exit(1)
#     except json.JSONDecodeError:
#         log.error(f"Error: Could not decode JSON from {SCRIPT_CUES_FILE}.")
#         exit(1)

# # --- Audio Recording Thread ---
# def audio_recorder():
#     log.info("Starting audio recording...")
#     try:
#         with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='float32', blocksize=CHUNK_SIZE) as stream:
#             while True:
#                 audio_chunk, overflowed = stream.read(CHUNK_SIZE)
#                 if overflowed:
#                     log.warning("Audio input buffer overflowed!")
#                 audio_queue.put(audio_chunk.flatten())
#     except Exception as e:
#         log.error(f"Audio recording error: {e}")

# # --- Transcription Thread ---
# def transcriber():
#     log.info(f"Loading Whisper model: {WHISPER_MODEL_SIZE}...")
#     model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
#     log.info("Whisper model loaded.")

#     full_audio_buffer = np.array([])
#     last_speech_time = time.time()

#     while True:
#         try:
#             chunk = audio_queue.get(timeout=1)
#             full_audio_buffer = np.concatenate((full_audio_buffer, chunk))

#             rms = np.sqrt(np.mean(chunk**2))
#             if rms > SILENCE_THRESHOLD:
#                 last_speech_time = time.time()

#             if time.time() - last_speech_time > SILENCE_DURATION and len(full_audio_buffer) > 0:
#                 log.info("Silence detected, processing utterance...")
#                 segments, info = model.transcribe(full_audio_buffer, language=LANGUAGE)
#                 transcribed_text = " ".join([seg.text for seg in segments]).strip()
#                 if transcribed_text:
#                     transcription_queue.put(transcribed_text)
#                 full_audio_buffer = np.array([])
#                 last_speech_time = time.time()

#         except queue.Empty:
#             if len(full_audio_buffer) > 0 and time.time() - last_speech_time > SILENCE_DURATION:
#                 log.info("Timeout/Silence, processing remaining utterance...")
#                 segments, info = model.transcribe(full_audio_buffer, language=LANGUAGE)
#                 transcribed_text = " ".join([seg.text for seg in segments]).strip()
#                 if transcribed_text:
#                     transcription_queue.put(transcribed_text)
#                 full_audio_buffer = np.array([])
#                 last_speech_time = time.time()
#         except Exception as e:
#             log.error(f"Transcription error: {e}")

# # --- Playback Thread ---
# def audio_playback():
#     while True:
#         try:
#             audio_file = playback_queue.get()
#             if audio_file:
#                 log.info(f"Playing '{audio_file}'...")
#                 playsound(audio_file, block=False)
#                 log.info(f"Finished playing '{audio_file}'.")
#         except Exception as e:
#             log.error(f"Audio playback error: {e}")

# # --- Main Logic Thread ---
# def main_logic():
#     global last_match_time, last_played_cue_id, current_cue_index

#     while True:
#         try:
#             transcribed_text = transcription_queue.get(timeout=1)
#             log.info(f"[⏱️ {time.strftime('%H:%M:%S', time.gmtime(time.time()))}] Detected: '{transcribed_text}'")

#             if time.time() - last_match_time < MATCH_COOLDOWN:
#                 continue

#             match, score, idx = process.extractOne(
#                 transcribed_text, cue_texts, scorer=fuzz.partial_ratio)
#             log.info(f"[🔍 Fuzzy] Best match: '{match}' (score: {score})")
#             if score >= MATCH_THRESHOLD_SCORE:
#                 cue = script_cues[idx]
#                 current_cue_index = idx
#                 log.info(f"[✅ Match] Cue {cue['id']} matched → Playing '{cue['en_audio']}'")
#                 playback_queue.put(os.path.join(AUDIO_DIR, cue['en_audio']))
#                 last_match_time = time.time()
#                 last_played_cue_id = cue['id']
#             else:
#                 log.info("No cue passed threshold.")

#         except queue.Empty:
#             pass
#         except Exception as e:
#             log.error(f"Main logic error: {e}")

# # --- Manual Override Hotkeys ---
# def on_press(key):
#     global current_cue_index, last_match_time, last_played_cue_id
#     try:
#         if key == keyboard.Key.esc:
#             return False
#         if hasattr(key, 'char'):
#             c = key.char.lower()
#             if c == 'n' and current_cue_index < len(script_cues) - 1:
#                 current_cue_index += 1
#                 cue = script_cues[current_cue_index]
#                 log.info(f"[⏩ Next] Playing cue {cue['id']} → '{cue['en_audio']}'")
#                 playback_queue.put(os.path.join(AUDIO_DIR, cue['en_audio']))
#                 last_played_cue_id = cue['id']
#                 last_match_time = time.time()
#             elif c == 'p' and current_cue_index > 0:
#                 current_cue_index -= 1
#                 cue = script_cues[current_cue_index]
#                 log.info(f"[⏪ Previous] Playing cue {cue['id']} → '{cue['en_audio']}'")
#                 playback_queue.put(os.path.join(AUDIO_DIR, cue['en_audio']))
#                 last_played_cue_id = cue['id']
#                 last_match_time = time.time()
#             elif c == 'r' and last_played_cue_id is not None:
#                 cue = next((c for c in script_cues if c['id'] == last_played_cue_id), None)
#                 if cue:
#                     log.info(f"[🔁 Repeat] Repeating cue {cue['id']} → '{cue['en_audio']}'")
#                     playback_queue.put(os.path.join(AUDIO_DIR, cue['en_audio']))
#                     last_match_time = time.time()
#     except Exception:
#         pass


# def start_keyboard_listener():
#     global keyboard_listener
#     keyboard_listener = keyboard.Listener(on_press=on_press)
#     keyboard_listener.start()
#     log.info("Keyboard listener started. Press 'N', 'P', 'R', or 'Esc'.")

# # --- Main Execution ---
# if __name__ == "__main__":
#     load_script_cues()

#     threading.Thread(target=audio_recorder, daemon=True).start()
#     threading.Thread(target=transcriber, daemon=True).start()
#     threading.Thread(target=audio_playback, daemon=True).start()
#     threading.Thread(target=main_logic, daemon=True).start()

#     start_keyboard_listener()

#     try:
#         while True:
#             time.sleep(1)
#     except KeyboardInterrupt:
#         log.info("Application interrupted by user.")
#     finally:
#         if keyboard_listener:
#             keyboard_listener.stop()
#         log.info("Application shutting down.")
# import json
# import os
# import time
# import threading
# import queue
# import logging
# import sounddevice as sd
# import numpy as np
# from faster_whisper import WhisperModel
# import simpleaudio as sa
# import wave
# from pynput import keyboard
# from rapidfuzz import process, fuzz

# # --- Configuration ---
# AUDIO_DIR              = "audio"
# SCRIPT_CUES_FILE       = "script_cues.json"
# SAMPLE_RATE            = 16000  # Whisper model expects 16kHz
# CHUNK_SIZE             = 1024   # Audio buffer size
# WHISPER_MODEL_SIZE     = "base" # You can change to "small", "medium", "large"
# LANGUAGE               = "en"   # Use English model for transcription
# SILENCE_THRESHOLD      = 0.005  # More sensitive detection
# SILENCE_DURATION       = 0.5    # Shorter silence for utterance end
# MATCH_COOLDOWN         = 5      # Seconds to ignore new matches after a playback
# MATCH_THRESHOLD_SCORE  = 70     # Fuzzy match score (%) threshold

# # --- Logging Setup ---
# logging.basicConfig(level=logging.INFO,
#                     format='[%(asctime)s.%(msecs)03d] %(message)s',
#                     datefmt='%H:%M:%S')
# log = logging.getLogger(__name__)

# # --- Global Variables ---
# audio_queue         = queue.Queue()
# transcription_queue = queue.Queue()
# playback_queue      = queue.Queue()
# script_cues         = []
# cue_texts           = []
# last_played_cue_id  = None
# last_match_time     = 0
# current_cue_index   = -1  # For manual override
# keyboard_listener   = None
# play_obj            = None   # simpleaudio playback object

# # --- Load Script Cues ---
# def load_script_cues():
#     global script_cues, cue_texts
#     try:
#         with open(SCRIPT_CUES_FILE, 'r', encoding='utf-8') as f:
#             script_cues = json.load(f)
#         cue_texts = [cue["hi_text"] for cue in script_cues]
#         log.info(f"Loaded {len(script_cues)} script cues from {SCRIPT_CUES_FILE}")
#     except FileNotFoundError:
#         log.error(f"Error: {SCRIPT_CUES_FILE} not found.")
#         exit(1)
#     except json.JSONDecodeError:
#         log.error(f"Error: Could not decode JSON from {SCRIPT_CUES_FILE}.")
#         exit(1)

# # --- Audio Recording Thread ---
# def audio_recorder():
#     log.info("Starting audio recording...")
#     try:
#         with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='float32', blocksize=CHUNK_SIZE) as stream:
#             while True:
#                 audio_chunk, overflowed = stream.read(CHUNK_SIZE)
#                 if overflowed:
#                     log.warning("Audio input buffer overflowed!")
#                 audio_queue.put(audio_chunk.flatten())
#     except Exception as e:
#         log.error(f"Audio recording error: {e}")

# # --- Transcription Thread ---
# def transcriber():
#     global play_obj
#     log.info(f"Loading Whisper model: {WHISPER_MODEL_SIZE}...")
#     model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
#     log.info("Whisper model loaded.")

#     full_audio_buffer = np.array([])
#     last_speech_time = time.time()

#     while True:
#         try:
#             chunk = audio_queue.get(timeout=1)
#             full_audio_buffer = np.concatenate((full_audio_buffer, chunk))

#             rms = np.sqrt(np.mean(chunk**2))
#             if rms > SILENCE_THRESHOLD:
#                 # interrupt current playback on voice detected
#                 if play_obj and play_obj.is_playing():
#                     log.info("Voice detected: interrupting playback.")
#                     play_obj.stop()
#                 last_speech_time = time.time()

#             if time.time() - last_speech_time > SILENCE_DURATION and len(full_audio_buffer) > 0:
#                 log.info("Silence detected, processing utterance...")
#                 segments, info = model.transcribe(full_audio_buffer, language=LANGUAGE)
#                 transcribed_text = " ".join([seg.text for seg in segments]).strip()
#                 if transcribed_text:
#                     transcription_queue.put(transcribed_text)
#                 full_audio_buffer = np.array([])
#                 last_speech_time = time.time()

#         except queue.Empty:
#             if len(full_audio_buffer) > 0 and time.time() - last_speech_time > SILENCE_DURATION:
#                 log.info("Timeout/Silence, processing remaining utterance...")
#                 segments, info = model.transcribe(full_audio_buffer, language=LANGUAGE)
#                 transcribed_text = " ".join([seg.text for seg in segments]).strip()
#                 if transcribed_text:
#                     transcription_queue.put(transcribed_text)
#                 full_audio_buffer = np.array([])
#                 last_speech_time = time.time()
#         except Exception as e:
#             log.error(f"Transcription error: {e}")

# # --- Playback Thread ---
# def audio_playback():
#     global play_obj
#     while True:
#         try:
#             audio_file = playback_queue.get()
#             if audio_file:
#                 # stop any existing playback
#                 if play_obj and play_obj.is_playing():
#                     play_obj.stop()
#                 log.info(f"Playing '{audio_file}'...")
#                 # load WAV file
#                 wf = wave.open(audio_file, 'rb')
#                 data = wf.readframes(wf.getnframes())
#                 play_obj = sa.play_buffer(
#                     data,
#                     num_channels=wf.getnchannels(),
#                     bytes_per_sample=wf.getsampwidth(),
#                     sample_rate=wf.getframerate()
#                 )
#                 wf.close()
#         except Exception as e:
#             log.error(f"Audio playback error: {e}")

# # --- Main Logic Thread ---
# def main_logic():
#     global last_match_time, last_played_cue_id, current_cue_index

#     while True:
#         try:
#             transcribed_text = transcription_queue.get(timeout=1)
#             log.info(f"[⏱️ {time.strftime('%H:%M:%S', time.gmtime(time.time()))}] Detected: '{transcribed_text}'")

#             if time.time() - last_match_time < MATCH_COOLDOWN:
#                 continue

#             match, score, idx = process.extractOne(
#                 transcribed_text, cue_texts, scorer=fuzz.partial_ratio)
#             log.info(f"[🔍 Fuzzy] Best match: '{match}' (score: {score})")
#             if score >= MATCH_THRESHOLD_SCORE:
#                 cue = script_cues[idx]
#                 current_cue_index = idx
#                 log.info(f"[✅ Match] Cue {cue['id']} matched → Playing '{cue['en_audio']}'")
#                 playback_queue.put(os.path.join(AUDIO_DIR, cue['en_audio']))
#                 last_match_time = time.time()
#                 last_played_cue_id = cue['id']
#             else:
#                 log.info("No cue passed threshold.")

#         except queue.Empty:
#             pass
#         except Exception as e:
#             log.error(f"Main logic error: {e}")

# # --- Manual Override Hotkeys ---
# def on_press(key):
#     global current_cue_index, last_match_time, last_played_cue_id, play_obj
#     try:
#         if key == keyboard.Key.esc:
#             return False
#         if hasattr(key, 'char'):
#             c = key.char.lower()
#             # interrupt playback on any manual key
#             if play_obj and play_obj.is_playing():
#                 play_obj.stop()
#             if c == 'n' and current_cue_index < len(script_cues) - 1:
#                 current_cue_index += 1
#                 cue = script_cues[current_cue_index]
#                 log.info(f"[⏩ Next] Playing cue {cue['id']} → '{cue['en_audio']}'")
#                 playback_queue.put(os.path.join(AUDIO_DIR, cue['en_audio']))
#                 last_played_cue_id = cue['id']
#                 last_match_time = time.time()
#             elif c == 'p' and current_cue_index > 0:
#                 current_cue_index -= 1
#                 cue = script_cues[current_cue_index]
#                 log.info(f"[⏪ Previous] Playing cue {cue['id']} → '{cue['en_audio']}'")
#                 playback_queue.put(os.path.join(AUDIO_DIR, cue['en_audio']))
#                 last_played_cue_id = cue['id']
#                 last_match_time = time.time()
#             elif c == 'r' and last_played_cue_id is not None:
#                 cue = next((c for c in script_cues if c['id'] == last_played_cue_id), None)
#                 if cue:
#                     log.info(f"[🔁 Repeat] Repeating cue {cue['id']} → '{cue['en_audio']}'")
#                     playback_queue.put(os.path.join(AUDIO_DIR, cue['en_audio']))
#                     last_match_time = time.time()
#     except Exception:
#         pass


# def start_keyboard_listener():
#     global keyboard_listener
#     keyboard_listener = keyboard.Listener(on_press=on_press)
#     keyboard_listener.start()
#     log.info("Keyboard listener started. Press 'N', 'P', 'R', or 'Esc'.")

# # --- Main Execution ---
# if __name__ == "__main__":
#     load_script_cues()
#     threading.Thread(target=audio_recorder, daemon=True).start()
#     threading.Thread(target=transcriber, daemon=True).start()
#     threading.Thread(target=audio_playback, daemon=True).start()
#     threading.Thread(target=main_logic, daemon=True).start()

#     start_keyboard_listener()

#     try:
#         while True:
#             time.sleep(1)
#     except KeyboardInterrupt:
#         log.info("Application interrupted by user.")
#     finally:
#         if keyboard_listener:
#             keyboard_listener.stop()
#         log.info("Application shutting down.")
# import json
# import os
# import time
# import threading
# import queue
# import logging
# import sounddevice as sd
# import numpy as np
# from faster_whisper import WhisperModel
# from playsound import playsound
# from pynput import keyboard
# from rapidfuzz import process, fuzz

# # --- Configuration ---
# AUDIO_DIR = "audio"
# SCRIPT_CUES_FILE = "script_cues.json"
# SAMPLE_RATE = 16000  # Whisper model expects 16kHz
# CHUNK_SIZE = 1024    # Audio buffer size
# WHISPER_MODEL_SIZE = "base"  # or "small", "medium", "large"
# LANGUAGE = "en"  # English for transcription
# SILENCE_THRESHOLD = 0.01  # Adjust as needed
# SILENCE_DURATION = 1.0  # Seconds of silence to consider end of utterance
# MATCH_COOLDOWN = 5  # Seconds to ignore new matches after a playback
# MATCH_THRESHOLD_SCORE = 60  # Fuzzy match threshold (0-100)

# # --- Logging Setup ---
# logging.basicConfig(
#     level=logging.INFO,
#     format='[%(asctime)s.%(msecs)03d] %(message)s',
#     datefmt='%H:%M:%S'
# )
# log = logging.getLogger(__name__)

# # --- Global Variables ---
# audio_queue = queue.Queue()
# transcription_queue = queue.Queue()
# playback_queue = queue.Queue()
# script_cues = []
# cue_texts = []
# last_played_cue_id = None
# last_match_time = 0
# current_cue_index = -1  # For manual override
# keyboard_listener = None

# # --- Load Script Cues ---
# def load_script_cues():
#     global script_cues, cue_texts
#     try:
#         with open(SCRIPT_CUES_FILE, 'r', encoding='utf-8') as f:
#             script_cues = json.load(f)
#         # prepare plain-text list for fuzzy matching
#         cue_texts = [cue['hi_text'] for cue in script_cues]
#         log.info(f"Loaded {len(script_cues)} script cues from {SCRIPT_CUES_FILE}")
#     except FileNotFoundError:
#         log.error(f"Error: {SCRIPT_CUES_FILE} not found.")
#         exit(1)
#     except json.JSONDecodeError:
#         log.error(f"Error: Could not decode JSON from {SCRIPT_CUES_FILE}.")
#         exit(1)

# # --- Audio Recording Thread ---
# def audio_recorder():
#     log.info("Starting audio recording...")
#     try:
#         with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='float32', blocksize=CHUNK_SIZE) as stream:
#             while True:
#                 audio_chunk, overflowed = stream.read(CHUNK_SIZE)
#                 if overflowed:
#                     log.warning("Audio input buffer overflowed!")
#                 audio_queue.put(audio_chunk.flatten())
#     except Exception as e:
#         log.error(f"Audio recording error: {e}")

# # --- Transcription Thread ---
# def transcriber():
#     log.info(f"Loading Whisper model: {WHISPER_MODEL_SIZE}...")
#     model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
#     log.info("Whisper model loaded.")

#     full_audio_buffer = np.array([])
#     last_speech_time = time.time()

#     while True:
#         try:
#             chunk = audio_queue.get(timeout=1)
#             full_audio_buffer = np.concatenate((full_audio_buffer, chunk))

#             rms = np.sqrt(np.mean(chunk ** 2))
#             if rms > SILENCE_THRESHOLD:
#                 last_speech_time = time.time()

#             if time.time() - last_speech_time > SILENCE_DURATION and full_audio_buffer.size:
#                 log.info("Silence detected, processing utterance...")
#                 segments, _ = model.transcribe(full_audio_buffer, language=LANGUAGE)
#                 text = " ".join(seg.text for seg in segments).strip()
#                 if text:
#                     transcription_queue.put(text)
#                 full_audio_buffer = np.array([])
#                 last_speech_time = time.time()

#         except queue.Empty:
#             if full_audio_buffer.size and time.time() - last_speech_time > SILENCE_DURATION:
#                 log.info("Timeout/Silence, processing remaining utterance...")
#                 segments, _ = model.transcribe(full_audio_buffer, language=LANGUAGE)
#                 text = " ".join(seg.text for seg in segments).strip()
#                 if text:
#                     transcription_queue.put(text)
#                 full_audio_buffer = np.array([])
#                 last_speech_time = time.time()
#         except Exception as e:
#             log.error(f"Transcription error: {e}")

# # --- Playback Thread ---
# def audio_playback():
#     while True:
#         try:
#             audio_file = playback_queue.get()
#             if audio_file:
#                 log.info(f"Playing '{audio_file}'...")
#                 playsound(audio_file, block=False)
#         except Exception as e:
#             log.error(f"Audio playback error: {e}")

# # --- Main Logic Thread ---
# def main_logic():
#     global last_match_time, last_played_cue_id, current_cue_index

#     while True:
#         try:
#             transcribed_text = transcription_queue.get(timeout=1)
#             log.info(f"Detected: '{transcribed_text}'")

#             # enforce cooldown
#             if time.time() - last_match_time < MATCH_COOLDOWN:
#                 continue

#             # fuzzy-match against cues
#             match, score, idx = process.extractOne(
#                 transcribed_text, cue_texts, scorer=fuzz.partial_ratio
#             )
#             log.info(f"Fuzzy match '{match}' with score {score}")

#             if score >= MATCH_THRESHOLD_SCORE:
#                 cue = script_cues[idx]
#                 current_cue_index = idx
#                 log.info(f"Match! Cue {cue['id']} → {cue['en_audio']}")
#                 playback_queue.put(os.path.join(AUDIO_DIR, cue['en_audio'].split('/')[-1]))
#                 last_match_time = time.time()
#                 last_played_cue_id = cue['id']
#         except queue.Empty:
#             continue
#         except Exception as e:
#             log.error(f"Main logic error: {e}")

# # --- Manual Override Hotkeys ---
# def on_press(key):
#     global current_cue_index, last_match_time, last_played_cue_id
#     try:
#         if key == keyboard.Key.esc:
#             return False
#         if hasattr(key, 'char'):
#             c = key.char.lower()
#             if c in ('n', 'p', 'r'):
#                 # interrupt and process manual commands
#                 if c == 'n' and current_cue_index < len(script_cues) - 1:
#                     current_cue_index += 1
#                 elif c == 'p' and current_cue_index > 0:
#                     current_cue_index -= 1
#                 elif c == 'r' and last_played_cue_id is not None:
#                     # find last cue index
#                     current_cue_index = next((i for i, c in enumerate(script_cues) if c['id'] == last_played_cue_id), current_cue_index)
#                 cue = script_cues[current_cue_index]
#                 log.info(f"Manual '{c}' → Cue {cue['id']} playing {cue['en_audio']}")
#                 playback_queue.put(os.path.join(AUDIO_DIR, cue['en_audio'].split('/')[-1]))
#                 last_played_cue_id = cue['id']
#                 last_match_time = time.time()
#     except Exception:
#         pass


# def start_keyboard_listener():
#     global keyboard_listener
#     keyboard_listener = keyboard.Listener(on_press=on_press)
#     keyboard_listener.start()
#     log.info("Keyboard listener started. Press N/P/R or Esc.")

# # --- Main Execution ---
# if __name__ == "__main__":
#     load_script_cues()

#     threading.Thread(target=audio_recorder, daemon=True).start()
#     threading.Thread(target=transcriber, daemon=True).start()
#     threading.Thread(target=audio_playback, daemon=True).start()
#     threading.Thread(target=main_logic, daemon=True).start()

#     start_keyboard_listener()

#     try:
#         while True:
#             time.sleep(1)
#     except KeyboardInterrupt:
#         log.info("Application interrupted by user.")
#     finally:
#         if keyboard_listener:
#             keyboard_listener.stop()
#         log.info("Application shutting down.")
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