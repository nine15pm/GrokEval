**Goal**  
Automate Grok.com voice testing: read prompts from CSV, send via TTS to Grok voice chat, capture responses, save to results.csv.

## Setup
1. Run `start_chrome_debug.bat` (starts Chrome with CDP on port 9222)
2. Manually login to grok.com in Chrome browser (session persists)
3. Set VB-Cable as default recording device for audio routing
4. Run `python grokeval.py`

## CSV Format
- **Input**: `prompts.csv` with columns `id,text`
- **Output**: `results.csv` with columns `id,prompt,grok_reply`

## Tech Stack
- Playwright (CDP connection to Chrome)
- edge-tts (text-to-speech)
- sounddevice (audio streaming to VB-Cable)
- pandas (CSV processing)