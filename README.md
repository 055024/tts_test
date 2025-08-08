# Live Theatre Dubbing System

This project implements a real-time live dubbing system for theatre performances. It detects Hindi/Sanskrit speech from a live microphone input, transcribes it, matches the first few tokens with a predefined `script_cues.json` file, and plays the corresponding pre-recorded English audio file.

## Features

- **Real-time Speech-to-Text (STT):** Utilizes `faster-whisper` for efficient transcription of live Hindi/Sanskrit speech.
- **Cue Matching:** Matches detected speech tokens with a `script_cues.json` file to trigger audio playback.
- **Non-blocking Audio Playback:** Plays English audio files instantly without interrupting the main process.
- **Manual Overrides:** Hotkeys for playing next, previous, or repeating the last played audio cue.
- **Logging:** Provides clear terminal output for detected speech and matched cues.
- **Offline Capability:** Designed to work entirely offline, suitable for theatre environments.

## Prerequisites

- Python 3.8+
- `pip` (Python package installer)

## Setup

1.  **Clone the repository (if applicable):**
    ```bash
    # If this were a git repo, you'd clone it here.
    # For this task, assume you have the files in your working directory.
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *Note: `faster-whisper` will download the specified Whisper model (`base` by default) on its first run.*

3.  **Prepare audio files:**
    Create an `audio` directory in the project root and place your pre-recorded English `.wav` files inside it. Ensure the filenames match those referenced in `script_cues.json` (e.g., `1.wav`, `2.wav`).

    ```
    your_project_root/
    ├── app.py
    ├── script_cues.json
    ├── requirements.txt
    └── audio/
        ├── 1.wav
        ├── 2.wav
        └── ...
    ```

4.  **Configure `script_cues.json`:**
    Edit the `script_cues.json` file to define your Hindi/Sanskrit cues and their corresponding English audio files.

    Example `script_cues.json`:
    ```json
    [
      {
        "id": 1,
        "hi_text": "श्रीराम बोलो",
        "first_tokens": ["श्रीराम", "बोलो"],
        "en_audio": "audio/1.wav"
      },
      {
        "id": 2,
        "hi_text": "हनुमान जी आयेंगे",
        "first_tokens": ["हनुमान", "जी"],
        "en_audio": "audio/2.wav"
      }
    ]
    ```
    - `id`: A unique identifier for the cue.
    - `hi_text`: The full Hindi/Sanskrit text of the line (for reference/logging).
    - `first_tokens`: An array of 1-2 key tokens (words) that, when detected at the beginning of a live utterance, will trigger this cue. These tokens should be in lowercase for matching.
    - `en_audio`: The path to the corresponding English audio file relative to the project root.

## Usage

Run the application from your terminal:

```bash
python app.py
```

The system will start listening to your microphone.

### Hotkeys

-   **N**: Play the next audio cue in `script_cues.json`.
-   **P**: Play the previous audio cue in `script_cues.json`.
-   **R**: Repeat the last played audio cue.
-   **Esc**: Exit the application.

## Logging

The terminal will display real-time logs:

```
[⏱️ 00:12.3] Detected: 'श्रीराम बोलो'
[✅ Match] Found cue 1 → Playing 'audio/1.wav'
```

## Customization

-   **Whisper Model Size:** In `app.py`, change `WHISPER_MODEL_SIZE` to `small`, `medium`, or `large` for different accuracy/performance trade-offs.
-   **Language:** Ensure `LANGUAGE` in `app.py` is set correctly (`hi` for Hindi).
-   **Silence Detection:** Adjust `SILENCE_THRESHOLD` and `SILENCE_DURATION` in `app.py` to fine-tune when an utterance is considered complete.
-   **Match Cooldown:** Modify `MATCH_COOLDOWN` in `app.py` to control how long the system ignores new matches after a playback.

## Potential Enhancements (Bonus)

-   **Dockerfile:** For containerized deployment with ALSA/PulseAudio support.
-   **Keyword Spotting:** Integrate `openWakeWord` or a TF-Lite KWS model for more robust initial token detection.
-   **GUI:** A simple graphical user interface for easier control and monitoring.
-   **Error Handling:** More robust error handling for audio devices and file operations.