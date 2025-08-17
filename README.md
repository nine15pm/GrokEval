# GrokAutomation

Automate Grok.com voice testing: CSV prompts → TTS → voice chat → capture responses.

## Setup
1. `pip install -r requirements.txt`
2. Install VB-Cable, set as default recording device
3. `start_chrome_debug.bat` → login to grok.com
4. `python grokautomation.py`

## Usage
```bash
python grokautomation.py                    # Basic
python grokautomation.py -i prompts.csv    # Custom input
python grokautomation.py --resume          # Resume run
```

**Input**: `prompts.csv` (id,text)  
**Output**: `results_YYYY-MM-DD_HH-MM.csv` (id,prompt,grok_reply)