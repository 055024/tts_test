import streamlit as st
import json
import os
import numpy as np
from faster_whisper import WhisperModel
from rapidfuzz import process, fuzz
import tempfile
import time

# --- Configuration ---
AUDIO_DIR = "audio"
SCRIPT_CUES_FILE = "script_cues.json"
WHISPER_MODEL_SIZE = "base"
LANGUAGE = "en"
MATCH_THRESHOLD_SCORE = 60

# --- Load Script Cues ---
def load_script_cues():
    with open(SCRIPT_CUES_FILE, 'r', encoding='utf-8') as f:
        script_cues = json.load(f)
    cue_texts = [cue['hi_text'] for cue in script_cues]
    return script_cues, cue_texts

# --- Transcribe Audio ---
def transcribe_audio(audio_bytes, model):
    import soundfile as sf
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp.flush()
        data, samplerate = sf.read(tmp.name)
        if len(data.shape) > 1:
            data = data[:, 0]  # mono
        if samplerate != 16000:
            import librosa
            data = librosa.resample(data, orig_sr=samplerate, target_sr=16000)
        segments, _ = model.transcribe(np.array(data), language=LANGUAGE)
        text = " ".join(seg.text for seg in segments).strip()
    os.unlink(tmp.name)
    return text

# --- Main App ---
st.set_page_config(page_title="TTS Test Streamlit", layout="wide")
st.title("🎤 TTS Test: Audio Cue Matcher")

# Load cues and model
@st.cache_resource(show_spinner=True)
def get_model_and_cues():
    script_cues, cue_texts = load_script_cues()
    model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
    return model, script_cues, cue_texts

model, script_cues, cue_texts = get_model_and_cues()

# Session state for navigation
if 'current_cue_index' not in st.session_state:
    st.session_state.current_cue_index = 0
if 'last_played_cue_id' not in st.session_state:
    st.session_state.last_played_cue_id = None
if 'last_transcription' not in st.session_state:
    st.session_state.last_transcription = ''
if 'last_match_score' not in st.session_state:
    st.session_state.last_match_score = 0

# Audio input
st.header("1. Upload Audio")
audio_file = st.file_uploader(
    "Upload or record audio (wav, mp3, ogg, mpga)", 
    type=["wav", "mp3", "ogg", "mpga"]
)
audio_bytes = None
if audio_file is not None:
    audio_bytes = audio_file.read()
    st.audio(audio_bytes, format='audio/wav')

# Transcription and Matching
# if audio_bytes:
#     with st.spinner("Transcribing and matching..."):
#         transcription = transcribe_audio(audio_bytes, model)
#         st.session_state.last_transcription = transcription
#         match, score, idx = process.extractOne(transcription, cue_texts, scorer=fuzz.partial_ratio)
#         st.session_state.last_match_score = score
#         st.session_state.current_cue_index = idx if score >= MATCH_THRESHOLD_SCORE else 0
#         st.write(f"**Transcription:** {transcription}")
#         st.write(f"**Best Match:** {match}")
#         st.write(f"**Score:** {score}")
#         if score >= MATCH_THRESHOLD_SCORE:
#             st.success(f"Matched cue {script_cues[idx]['id']}! Play below.")
#             # Automatically play the matched cue audio
#             audio_path = os.path.join("audio", script_cues[idx]["en_audio"])
#             if os.path.exists(audio_path):
#                 audio_bytes = open(audio_path, "rb").read()
#                 st.audio(audio_bytes, format="audio/wav", start_time=0)
#             else:
#                 st.error("Matched audio file not found.")
#         else:
#             st.warning("No cue passed the match threshold.")
if audio_bytes:
    with st.spinner("Transcribing and matching..."):
        transcription = transcribe_audio(audio_bytes, model)
        st.session_state.last_transcription = transcription
        match, score, idx = process.extractOne(transcription, cue_texts, scorer=fuzz.partial_ratio)
        st.session_state.last_match_score = score
        st.session_state.current_cue_index = idx if score >= MATCH_THRESHOLD_SCORE else 0
        st.write(f"**Transcription:** {transcription}")
        st.write(f"**Best Match:** {match}")
        st.write(f"**Score:** {score}")
        if score >= MATCH_THRESHOLD_SCORE:
            st.success(f"Matched cue {script_cues[idx]['id']}! Play below.")
            # Automatically play the matched cue audio
            audio_path = os.path.join("audio", script_cues[idx]["en_audio"])
            if os.path.exists(audio_path):
                cue_audio_bytes = open(audio_path, "rb").read()
                st.audio(cue_audio_bytes, format="audio/wav", start_time=0)
            else:
                st.error("Matched audio file not found.")
        else:
            st.warning("No cue passed the match threshold.")

# Manual Controls
st.header("2. Manual Controls")
col1, col2, col3 = st.columns(3)
with col1:
    if st.button("⏪ Previous"):
        if st.session_state.current_cue_index > 0:
            st.session_state.current_cue_index -= 1
with col2:
    if st.button("🔁 Repeat"):
        pass  # just replays current
with col3:
    if st.button("⏩ Next"):
        if st.session_state.current_cue_index < len(script_cues) - 1:
            st.session_state.current_cue_index += 1

cue = script_cues[st.session_state.current_cue_index]
st.subheader(f"Current Cue: {cue['id']}")
st.write(cue['hi_text'])
audio_path = os.path.join(AUDIO_DIR, cue['en_audio'])
if os.path.exists(audio_path):
    with open(audio_path, 'rb') as f:
        st.audio(f.read(), format='audio/mp3')
else:
    st.error(f"Audio file not found: {audio_path}")

# Show all cues
def show_cues_table():
    st.header("3. All Script Cues")
    for c in script_cues:
        st.markdown(f"**{c['id']}**: {c['hi_text']}")
        ap = os.path.join(AUDIO_DIR, c['en_audio'])
        if os.path.exists(ap):
            with open(ap, 'rb') as f:
                st.audio(f.read(), format='audio/mp3')
        st.markdown("---")

with st.expander("Show all cues"):
    show_cues_table()

st.info("Use the controls above to navigate cues, or upload/record audio to match and play.")
