# 🚀 TTS Remote Controller - Startup Guide

## Quick Start (2 Steps)

### Step 1: Start the Backend API Server
```bash
cd /home/ashok/Desktop/tts_test
source venv/bin/activate
python remote_api.py
```
**This runs on:** `http://localhost:8001`

### Step 2: Open the Frontend
Choose **ONE** of these methods:

#### Method A: Direct File Access (Simplest)
```bash
# Open the HTML file directly in your browser
xdg-open /home/ashok/Desktop/tts_test/index.html
# OR double-click index.html in your file manager
```

#### Method B: HTTP Server (Recommended for development)
```bash
# In a NEW terminal window:
cd /home/ashok/Desktop/tts_test
python serve_frontend.py
```
**This serves frontend on:** `http://localhost:3000`

#### Method C: Python Built-in Server
```bash
# In a NEW terminal window:
cd /home/ashok/Desktop/tts_test
python3 -m http.server 3000
```
Then open: `http://localhost:3000`

## 🔧 Configuration

Once the frontend opens:

1. **Backend URL:** Set to `http://localhost:8001` (should be default)
2. **API Token:** Leave blank (unless you set API_TOKEN environment variable)
3. **Chunk Length:** 500ms (default is fine)
4. Click **"Connect"**
5. Click **"Start Mic"** to begin audio streaming

## 🎯 Architecture

```
Frontend (Port 3000)          Backend API (Port 8001)
┌─────────────────┐          ┌─────────────────┐
│   index.html    │ ◄──HTTP──► │  remote_api.py  │
│  (Web Browser)  │          │  (FastAPI)      │
└─────────────────┘          └─────────────────┘
                                      │
                                      │ imports
                                      ▼
                              ┌─────────────────┐
                              │     app.py      │
                              │ (Core Engine)   │
                              └─────────────────┘
```

## ❌ Common Issues

### "Frontend not opening"
- **Problem:** Trying to access frontend at `http://localhost:8001`
- **Solution:** Port 8001 is for the API backend. Use Method A, B, or C above.

### "Connection failed"
- **Problem:** Backend not running
- **Solution:** Make sure `python remote_api.py` is running in terminal

### "CORS errors"
- **Problem:** Browser security restrictions
- **Solution:** Use Method B or C (HTTP server) instead of direct file access

### "Microphone not working"
- **Problem:** Browser permissions or HTTPS requirement
- **Solution:** Grant microphone permissions, or use HTTPS in production

## 🧪 Testing

Test the system:
```bash
cd /home/ashok/Desktop/tts_test
python test_system.py
```

## 📝 Files Overview

- `index.html` - Frontend web interface (open this in browser)
- `remote_api.py` - Backend API server (run this in terminal)
- `app.py` - Core TTS engine (imported by remote_api.py)
- `serve_frontend.py` - Optional frontend server
- `script_cues.json` - Audio cue database

## 🎮 Usage

1. **Connect** - Establish connection to backend
2. **Start Mic** - Begin streaming browser audio to backend
3. **Speak** - Your speech will be processed and matched against cues
4. **Manual Controls** - Use Next/Prev/Replay buttons as needed
5. **Status Panel** - Monitor real-time system status

The system processes your speech and automatically plays corresponding English audio files when matches are found!