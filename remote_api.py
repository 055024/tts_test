import os, time, tempfile, subprocess
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_500_INTERNAL_SERVER_ERROR
from starlette.middleware.cors import CORSMiddleware

from app import app as app_api  # exposes status(), process_command(), manual_override(), process_audio()
from helpers import pick_ext, save_atomic_bytes, validate_with_ffprobe, quick_header_check

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

@app.get("/api/status")
def status():
    # Provide a stable contract for the frontend while preserving existing fields
    payload = app_api.status()
    payload.setdefault("ok", True)
    payload.setdefault("engine", "ready")
    payload.setdefault("frontend_mode", True)
    return payload

@app.post("/api/cmd")
async def cmd(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    return app_api.process_command(data)

@app.post("/api/manual")
async def manual(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    return app_api.manual_override(data)

@app.post("/api/ingest")
async def ingest(request: Request):
    try:
        ctype = (request.headers.get("content-type", "") or "").lower()
        raw = None
        suffix = ".bin"
        if "multipart/form-data" in ctype:
            # Properly parse multipart and extract the 'audio' field
            form = await request.form()
            up = form.get("audio")
            if not up or not hasattr(up, "read"):
                return JSONResponse(status_code=HTTP_400_BAD_REQUEST, content={"error": "missing_audio_field"})
            file_ct = getattr(up, "content_type", "") or ""
            suffix = pick_ext(file_ct)
            raw = await up.read()
        else:
            # Fallback: raw body mode
            raw = await request.body()  # only returns after the upload fully completes
            suffix = pick_ext(ctype)
        tmp_path = save_atomic_bytes(raw, suffix=suffix)

        min_bytes = 2000  # ~2 KB; adjust if needed
        size = os.path.getsize(tmp_path)
        if size < min_bytes:
            os.remove(tmp_path)  # Clean up the small file
            return JSONResponse(status_code=204, content={"skip": f"chunk too small: {size} bytes"})

        # quick fast-fail for OGG files
        if suffix == ".ogg" and not quick_header_check(tmp_path):
            os.remove(tmp_path)
            return JSONResponse(status_code=HTTP_400_BAD_REQUEST,
                                content={"error": "bad_ogg_header"})

        ok, meta = validate_with_ffprobe(tmp_path)
        if not ok:
            # Gracefully ignore known short/incomplete container slices from browsers
            detail = str(meta)
            if any(k in detail.lower() for k in ["end of file", "ebml header parsing failed", "invalid data found"]):
                try: os.remove(tmp_path)
                except: pass
                return JSONResponse(status_code=204, content={"skip": detail[:200]})
            os.remove(tmp_path)
            return JSONResponse(status_code=HTTP_400_BAD_REQUEST,
                                content={"error": "invalid_media", "detail": meta})

        # Lightweight decode test: try to read the input with ffmpeg without producing output
        sanity = subprocess.run([
            "ffmpeg", "-v", "error", "-nostdin", "-i", tmp_path, "-f", "null", "-"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if sanity.returncode != 0:
            err = sanity.stderr.decode("utf-8", errors="ignore")
            # Graceful skip for partial, short, or fragmented chunks
            low = err.lower()
            if any(k in low for k in ["end of file", "ebml header parsing failed", "invalid data found", "moov atom not found"]):
                try: os.remove(tmp_path)
                except: pass
                return JSONResponse(status_code=204, content={"skip": err[:200]})
            os.remove(tmp_path)
            return JSONResponse(status_code=HTTP_400_BAD_REQUEST,
                                content={"error": "decode_failed", "detail": err[:400]})

        # Transcode to WAV for consistent processing
        wav_tmp = tempfile.mktemp(suffix=".wav")
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
            "-y", "-i", tmp_path, "-ac", "1", "-ar", "16000", "-f", "wav", wav_tmp
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0 or not os.path.exists(wav_tmp) or os.path.getsize(wav_tmp) == 0:
            err = proc.stderr.decode("utf-8", errors="ignore")
            print("[ffmpeg] transcode error:", err[:800])
            os.remove(tmp_path)  # Clean up original file
            try:
                os.remove(wav_tmp)  # Try to remove partially created wav file
            except:
                pass
            return JSONResponse(status_code=422, content={"error": "ffmpeg_failed", "detail": err[:400]})

        # now it's complete AND valid → safe to process
        try:
            result = app_api.process_audio(wav_tmp)   # Pass the transcoded WAV file
        finally:
            # remove only the original upload; let the app delete the WAV after use
            try:
                os.remove(tmp_path)
            except:
                pass
            # Do NOT remove wav_tmp here; it is used asynchronously by the app

        return result
    except Exception as e:
        return JSONResponse(status_code=HTTP_500_INTERNAL_SERVER_ERROR, content={"error": str(e)})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
