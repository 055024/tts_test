import os, tempfile, subprocess, json

def pick_ext(content_type: str) -> str:
    ct = (content_type or "").lower()
    if "ogg" in ct: return ".ogg"     # Firefox
    if "webm" in ct: return ".webm"   # Chromium
    if "wav" in ct: return ".wav"
    return ".bin"

def save_atomic_bytes(data: bytes, suffix: str) -> str:
    # write to .part then atomic rename
    fd, part_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        final_path = part_path  # already unique; rename only if you want a deterministic name
        return final_path
    except:
        try: os.remove(part_path)
        except: pass
        raise

def validate_with_ffprobe(path: str) -> tuple[bool, str | dict]:
    try:
        p = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_streams",
                "-select_streams", "a",
                "-show_entries", "stream=codec_name,codec_type,sample_rate,channels",
                "-of", "json", path,
            ],
            capture_output=True, text=True, timeout=5
        )
        if p.returncode != 0:
            return False, p.stderr.strip()
        info = json.loads(p.stdout or "{}")
        streams = info.get("streams")
        if not streams or not isinstance(streams, list):
            return False, "no streams"
        # find first audio stream
        st = None
        for s in streams:
            if isinstance(s, dict) and s.get("codec_type") == "audio":
                st = s
                break
        if not st:
            return False, "no audio stream"
        # accept opus/vorbis/pcm etc. tighten if you want only opus:
        if st.get("codec_name") not in ("opus", "vorbis", "pcm_s16le", "pcm_f32le"):
            return False, f"unexpected codec: {st.get('codec_name')}"
        return True, st
    except Exception as e:
        return False, str(e)

def quick_header_check(path: str) -> bool:
    # Fast sanity for OGG: must start with b'OggS'
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"OggS"
    except:
        return False