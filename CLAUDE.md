# GrokEval

Automated **batch evaluator** for the Grok mobile app’s **voice-mode** using a Windows PC only.  
`grokeval.py` drives an Android emulator, speaks each prompt, captures Grok’s reply, and logs results.

---

## 1. What it does (plain English)

| Step | Action | Done by |
|------|--------|---------|
| 1 | Read `prompts.csv` (`id,prompt` per line) | Python |
| 2 | Convert each prompt → WAV (Edge-TTS) | Python |
| 3 | Play WAV into a *virtual microphone* (VB-Audio Cable) that the emulator hears | FFmpeg |
| 4 | Hold Grok’s mic button exactly as long as the audio | `uiautomator2` |
| 5 | Wait until Grok finishes speaking back | `uiautomator2` |
| 6 | Extract last chat bubble text | `uiautomator2` |
| 7 | Append `id,prompt,reply` → `results.csv` | Python |
| 8 | Tap “New chat”, repeat | `uiautomator2` |

No screen-coordinate hacks; every UI target is addressed by stable Android resource IDs.

---

## 2. Folder layout

GrokEval/
│ README.md ← this file
│ grokeval.py ← main driver
│ prompts.csv ← your test prompts
│ results.csv ← auto-generated log
│
└─.venv/ ← Python virtual env (ignored by Git)


---

## 3. Hard requirements

* **Windows 10/11**
* **Python 3.10+**
* **Android Studio Emulator** (API 34 image)
* **VB-Audio Virtual Cable**  
* **FFmpeg** (for audio playback)
* **Edge-TTS**, **uiautomator2**, **adbutils**, **pydub** (Python packages)

---
