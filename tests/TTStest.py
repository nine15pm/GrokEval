#!/usr/bin/env python3
"""
Simple TTS test script to verify edge-tts functionality
Plays a test prompt through current default audio output device
"""

import asyncio
import tempfile
import os
import edge_tts
import sounddevice as sd
import soundfile as sf

async def test_tts(prompt: str = "Hello, this is a test of the text to speech system."):
    """Generate TTS audio and play through speakers"""
    
    print(f"Converting to speech: '{prompt}'")
    
    # Create temporary file for audio
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
        tmp_path = tmp_file.name
    
    try:
        # Generate TTS audio using edge-tts
        communicate = edge_tts.Communicate(prompt, "en-US-JennyNeural")
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
    test_prompt = "Testing edge TTS with speakers. Can you hear this message clearly?"
    asyncio.run(test_tts(test_prompt))