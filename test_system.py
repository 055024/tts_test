#!/usr/bin/env python3
"""
Test script to demonstrate the TTS remote controller system.
"""

import subprocess
import time
import requests
import threading
import sys

def test_api_endpoints():
    """Test the API endpoints."""
    base_url = "http://localhost:8000"
    
    print("Testing API endpoints...")
    
    try:
        # Test status endpoint
        response = requests.get(f"{base_url}/api/status")
        if response.status_code == 200:
            status = response.json()
            print(f"✅ Status endpoint working: {status}")
        else:
            print(f"❌ Status endpoint failed: {response.status_code}")
            
        # Test command endpoint
        response = requests.post(f"{base_url}/api/cmd", json={"cmd": "next"})
        if response.status_code == 200:
            print("✅ Command endpoint working")
        else:
            print(f"❌ Command endpoint failed: {response.status_code}")
            
        # Test manual play endpoint
        response = requests.post(f"{base_url}/api/manual", json={"cue_id": 1})
        if response.status_code == 200:
            print("✅ Manual play endpoint working")
        else:
            print(f"❌ Manual play endpoint failed: {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to API server. Make sure it's running.")
    except Exception as e:
        print(f"❌ Error testing API: {e}")

def start_api_server():
    """Start the API server in background."""
    print("Starting API server...")
    try:
        process = subprocess.Popen([
            sys.executable, "remote_api.py"
        ], cwd="/home/ashok/Desktop/tts_test")
        
        # Wait a bit for server to start
        time.sleep(3)
        
        return process
    except Exception as e:
        print(f"❌ Failed to start API server: {e}")
        return None

def main():
    print("🎤 TTS Remote Controller System Test")
    print("=" * 50)
    
    # Check if required files exist
    required_files = [
        "/home/ashok/Desktop/tts_test/app.py",
        "/home/ashok/Desktop/tts_test/remote_api.py",
        "/home/ashok/Desktop/tts_test/index.html",
        "/home/ashok/Desktop/tts_test/script_cues.json"
    ]
    
    for file_path in required_files:
        if not os.path.exists(file_path):
            print(f"❌ Missing required file: {file_path}")
            return
        else:
            print(f"✅ Found: {file_path}")
    
    print("\n📋 System Components:")
    print("1. app.py - Core TTS matching engine (unchanged)")
    print("2. remote_api.py - FastAPI adapter layer")
    print("3. index.html - Standalone web frontend")
    print("4. script_cues.json - Cue database")
    
    print("\n🚀 To run the system:")
    print("1. Start the API server:")
    print("   cd /home/ashok/Desktop/tts_test")
    print("   source venv/bin/activate")
    print("   python remote_api.py")
    print()
    print("2. Open index.html in a web browser")
    print("3. Configure the backend URL (http://localhost:8000)")
    print("4. Click 'Connect' and start using the controls")
    
    print("\n🌐 API Endpoints:")
    print("- GET  /api/status - Get system status")
    print("- POST /api/cmd - Execute commands (next, prev, replay, pause_listen, resume_listen)")
    print("- POST /api/manual - Play cue by ID")
    print("- POST /api/ingest - Ingest browser audio")
    
    print("\n🎯 Features:")
    print("- Remote control via web interface")
    print("- Browser microphone streaming")
    print("- Real-time status monitoring")
    print("- Manual cue playback")
    print("- CORS enabled for any origin")
    print("- Optional bearer token authentication")
    
    # Test if we can import the modules
    try:
        import app
        print("✅ Core app module imports successfully")
    except Exception as e:
        print(f"❌ Failed to import app module: {e}")
        
    try:
        import remote_api
        print("✅ Remote API module imports successfully")
    except Exception as e:
        print(f"❌ Failed to import remote_api module: {e}")

if __name__ == "__main__":
    import os
    main()