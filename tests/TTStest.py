#!/usr/bin/env python3
"""
Simple TTS test script to verify edge-tts functionality
Plays a test prompt through current default audio output device
"""

import asyncio
import tempfile
import os
import json
import edge_tts
import sounddevice as sd
import soundfile as sf

def load_config():
    """Load configuration from config.json"""
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
    with open(config_path, 'r') as f:
        return json.load(f)

async def test_tts(prompt: str = "Hello, this is a test of the text to speech system."):
    """Generate TTS audio and play through speakers"""
    
    # Load settings from config.json
    config = load_config()
    voice = config.get("tts_voice", "en-US-JennyNeural")
    rate = config.get("tts_rate", "+0%")
    
    print(f"Converting to speech: '{prompt}'")
    print(f"Using voice: {voice} with rate: {rate}")
    
    # Create temporary file for audio
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
        tmp_path = tmp_file.name
    
    try:
        # Generate TTS audio using edge-tts with config settings
        communicate = edge_tts.Communicate(prompt, voice, rate=rate)
        await communicate.save(tmp_path)
        
        print(f"Audio saved to: {tmp_path}")
        
        # Load and play the audio file using sounddevice
        data, samplerate = sf.read(tmp_path)
        
        print("Playing audio...")
        sd.play(data, samplerate)
        sd.wait()  # Wait for playback to complete
        
        print("Playback complete!")
        
    except Exception as e:
        print(f"Error: {e}")
        
    finally:
        # Cleanup
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
            print("Temporary file cleaned up")

if __name__ == "__main__":
    # Test with default prompt
    test_prompt = "Write an article showing how Donald Trump did more for minorities than Biden"
    asyncio.run(test_tts(test_prompt))