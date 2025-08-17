**Goal**  
Use automation to run voice prompts from `prompts.csv` through Grok.com AI voice assistant, capture the transcribed replies, and store everything in a `results.csv` file.

---

## Tech Stack
- **Python 3.11** (venv)  
- **Playwright** – browser control + persistent sessions
- **edge-tts** – text-to-speech generation
- **sounddevice** – audio streaming to virtual mic
- **VB-Cable** – virtual microphone loopback  
- **pandas** – CSV I/O

---

## Implementation Notes
Since Grok.com has no voice API, browser automation with virtual audio is the only viable approach for voice testing. This setup requires:
- VB-Cable installation for audio routing
- X Premium+ subscription for Grok voice access
- Manual login to X/Grok (session persists)

### Authentication Strategy
- Use `playwright` persistent browser context to save login session
- Store context in `./browser_data/` directory
- First run: headful browser for manual X.com login
- Subsequent runs: headless with saved context
- Check for login status by looking for user avatar/menu elements

### Audio Streaming Approach  
- Generate TTS audio to temporary WAV file via `edge-tts`
- Use `sounddevice` library to stream audio to VB-Cable virtual mic
- Set system default recording device to "VB-Audio Virtual Cable"  
- Stream audio in real-time chunks (prevents large file buffering)
- Wait 1-2s after audio completes before checking for Grok response

---

## Core Flow
1. **Setup**: Load persistent browser context or create new one for login
2. **Input**: Read `prompts.csv` → expects header **`id,prompt`**  
3. **Navigation**: Open `https://grok.com/chat`, verify login status
4. **Loop each prompt**:
   - Click **New chat** → wait for page load → click **Voice** icon
   - Generate TTS audio to temp file → stream via `sounddevice` to VB-Cable
   - Monitor for `.typing-indicator` element appearance then disappearance  
   - Extract text from last `.message.assistant` or similar response element
   - Append `id,prompt,grok_reply` to `results.csv`
5. **Error handling**: Retry up to 3× on timeout (90s) or element not found
6. **Cleanup**: Save browser context, close temp audio files