#!/usr/bin/env python3
"""
GrokAutomation v0 - End-to-end automation for Grok voice testing
Combines CDP connection, voice button detection, TTS streaming, and response capture
"""

import asyncio
import tempfile
import os
import pandas as pd
from playwright.async_api import async_playwright
import edge_tts
import sounddevice as sd
import soundfile as sf
import json
from datetime import datetime
import argparse

class GrokAutomator:
    # Proven selectors from UI discovery JSON files
    VOICE_SELECTOR = "[aria-label*='voice']"
    EXIT_VOICE_SELECTOR = "[aria-label='Exit voice mode']"
    TEXT_INPUT_SELECTOR = "[contenteditable='true']"
    RESPONSE_SELECTOR = "[class*='message']"
    NEW_CHAT_SELECTOR = "a[href='/']"
    ERROR_SELECTOR = "[role='alert']"

    def __init__(self):
        self.browser = None
        self.grok_page = None
        self.results = []
        self.playwright = None
        self.config = self.load_config()
    
    def load_config(self):
        """Load configuration from config.json"""
        try:
            if os.path.exists("config.json"):
                with open("config.json", "r") as f:
                    config = json.load(f)
                    print(f"Loaded config from config.json")
                    return config
            else:
                raise FileNotFoundError("config.json not found")
        except Exception as e:
            print(f"Error loading config.json: {e}")
            print("Please create a config.json file with required parameters")
            raise
    
    async def find_element(self, selector, description="element"):
        """Find and return element by selector"""
        try:
            element = self.grok_page.locator(selector).first
            if await element.is_visible() and await element.is_enabled():
                print(f"Found {description}")
                return element
        except Exception as e:
            print(f"Error finding {description}: {e}")
        print(f"{description.capitalize()} not found")
        return None
    
    async def detect_ui_errors(self):
        """Detect if there are any error messages in the UI"""
        try:
            elements = await self.grok_page.locator(self.ERROR_SELECTOR).all()
            for element in elements:
                if await element.is_visible():
                    error_text = await element.inner_text()
                    if error_text.strip() and "grok" not in error_text.lower():
                        return error_text.strip()
        except Exception:
            pass
        return None
    
    async def has_messages(self):
        """Check if page has messages (thread view)"""
        try:
            count = await self.grok_page.locator(self.RESPONSE_SELECTOR).count()
            return count > 0
        except Exception:
            return False
    
    async def is_new_conversation(self):
        """Check if we're in new conversation state (no messages)"""
        return not await self.has_messages()
    
    def load_existing_results(self, results_file):
        """Load existing results to enable resume functionality"""
        completed_ids = set()
        if os.path.exists(results_file):
            try:
                existing_df = pd.read_csv(results_file, encoding='utf-8')
                completed_ids = set(existing_df['id'].tolist())
                print(f"Found {len(completed_ids)} already completed prompts in {results_file}")
            except Exception as e:
                print(f"Error reading existing results: {e}")
        return completed_ids
    
    def generate_results_filename(self, base_name="results"):
        """Generate timestamped results filename"""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        return f"{base_name}_{timestamp}.csv"
        
    async def connect_to_chrome_with_retry(self):
        """Connect to Chrome browser via CDP with retry logic"""
        max_retries = self.config["max_retries"]
        retry_delay = self.config["retry_delay"]
        
        for attempt in range(max_retries):
            try:
                print(f"Connecting to Chrome via CDP (attempt {attempt + 1}/{max_retries})...")
                self.playwright = await async_playwright().start()
                
                # Add timeout for CDP connection
                try:
                    self.browser = await asyncio.wait_for(
                        self.playwright.chromium.connect_over_cdp(f"http://localhost:{self.config['chrome_port']}"),
                        timeout=10
                    )
                except asyncio.TimeoutError:
                    raise Exception("CDP connection timeout - is Chrome running with debug port?")
                
                # Get existing contexts and find Grok tab
                contexts = self.browser.contexts
                if not contexts:
                    raise Exception("No browser contexts found")
                    
                context = contexts[0]
                pages = context.pages
                
                # Find existing Grok tab or create new one
                self.grok_page = None
                for page in pages:
                    try:
                        if "grok.com" in page.url:
                            self.grok_page = page
                            break
                    except Exception as e:
                        print(f"Error checking page URL: {e}")
                        continue
                
                if not self.grok_page:
                    print("No Grok tab found, creating new one...")
                    self.grok_page = await context.new_page()
                    
                    # Navigate with timeout and retry
                    navigation_success = False
                    for nav_attempt in range(3):
                        try:
                            await asyncio.wait_for(
                                self.grok_page.goto("https://grok.com", wait_until="domcontentloaded"),
                                timeout=30
                            )
                            await asyncio.wait_for(
                                self.grok_page.wait_for_load_state("networkidle", timeout=30000),
                                timeout=35
                            )
                            navigation_success = True
                            break
                        except asyncio.TimeoutError:
                            print(f"Navigation timeout on attempt {nav_attempt + 1}")
                            if nav_attempt < 2:
                                await asyncio.sleep(5)
                                continue
                            else:
                                raise Exception("Navigation to grok.com timed out")
                        except Exception as e:
                            print(f"Navigation error on attempt {nav_attempt + 1}: {e}")
                            if nav_attempt < 2:
                                await asyncio.sleep(5)
                                continue
                            else:
                                raise
                    
                    if not navigation_success:
                        raise Exception("Failed to navigate to grok.com")
                        
                else:
                    print("Using existing Grok tab")
                    try:
                        await self.grok_page.bring_to_front()
                        # Check if page is responsive
                        await asyncio.wait_for(
                            self.grok_page.evaluate("() => document.readyState"),
                            timeout=5
                        )
                    except Exception as e:
                        print(f"Existing tab seems unresponsive: {e}")
                        print("Creating new tab...")
                        self.grok_page = await context.new_page()
                        await asyncio.wait_for(
                            self.grok_page.goto("https://grok.com", wait_until="domcontentloaded"),
                            timeout=30
                        )
                        await asyncio.wait_for(
                            self.grok_page.wait_for_load_state("networkidle", timeout=30000),
                            timeout=35
                        )
                
                # Set page timeouts
                self.grok_page.set_default_timeout(30000)
                self.grok_page.set_default_navigation_timeout(30000)
                
                print("Chrome connection established successfully")
                return True
                
            except Exception as e:
                print(f"Failed to connect to Chrome (attempt {attempt + 1}): {e}")
                
                # Cleanup on failed attempt
                try:
                    if self.browser:
                        await self.browser.close()
                    if self.playwright:
                        await self.playwright.stop()
                except:
                    pass
                
                self.browser = None
                self.playwright = None
                self.grok_page = None
                
                if attempt < max_retries - 1:
                    print(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                else:
                    print("\nTroubleshooting tips:")
                    print("1. Make sure Chrome is running with: start_chrome_debug.bat")
                    print("2. Check if port 9222 is available")
                    print("3. Try closing and restarting Chrome")
                    print("4. Make sure you're logged into grok.com")
                    return False
        
        return False
    
    async def exit_voice_mode(self):
        """Exit voice mode if currently active"""
        for attempt in range(self.config["max_retries"]):
            element = await self.find_element(self.EXIT_VOICE_SELECTOR, "exit voice button")
            if element:
                try:
                    await element.click()
                    await asyncio.sleep(2)  # Wait for voice mode to exit
                    print("Exited voice mode")
                    return True
                except Exception as e:
                    print(f"Exit voice button click failed: {e}")
                    if attempt < self.config["max_retries"] - 1:
                        await asyncio.sleep(self.config["retry_delay"])
                        continue
            else:
                # No exit voice button found, likely not in voice mode
                print("Not in voice mode or exit button not found")
                return True
        return False

    async def try_voice_mode(self):
        """Try to activate voice mode with error checking"""
        for attempt in range(self.config["max_retries"]):
            element = await self.find_element(self.VOICE_SELECTOR, "voice button")
            if element:
                try:
                    await element.click()
                    await asyncio.sleep(self.config["audio_wait_seconds"])
                    
                    # Check for errors after clicking
                    error_msg = await self.detect_ui_errors()
                    if error_msg:
                        print(f"Voice mode error: {error_msg}")
                        if attempt < self.config["max_retries"] - 1:
                            await asyncio.sleep(self.config["retry_delay"])
                            continue
                        return False
                    
                    print("Voice mode activated")
                    return True
                except Exception as e:
                    print(f"Voice button click failed: {e}")
                    if attempt < self.config["max_retries"] - 1:
                        await asyncio.sleep(self.config["retry_delay"])
                        continue
            else:
                if attempt < self.config["max_retries"] - 1:
                    await asyncio.sleep(self.config["retry_delay"])
                    continue
        return False
    
    async def generate_and_stream_tts(self, text):
        """Generate TTS audio and stream to virtual microphone"""
        print(f"Converting to speech: '{text}'")
        
        # Create temporary file for audio
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            tmp_path = tmp_file.name
        
        try:
            # Generate TTS audio using edge-tts
            communicate = edge_tts.Communicate(text, self.config["tts_voice"], rate=self.config["tts_rate"])
            await communicate.save(tmp_path)
            
            # Load audio data
            data, samplerate = sf.read(tmp_path)
            
            print("Streaming audio to virtual microphone...")
            # Stream to default recording device (should be VB-Cable)
            sd.play(data, samplerate)
            sd.wait()  # Wait for playback to complete
            
            # Wait for Grok to finish transcribing the audio
            print("Waiting for transcription to complete...")
            await asyncio.sleep(self.config["transcription_wait_seconds"])
            
            print("TTS and transcription complete")
            return True
            
        except Exception as e:
            print(f"Error with TTS: {e}")
            return False
            
        finally:
            # Cleanup
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    async def send_text_input(self, text):
        """Send text input with retry logic"""
        for attempt in range(self.config["max_retries"]):
            element = await self.find_element(self.TEXT_INPUT_SELECTOR, "text input")
            if element:
                try:
                    await element.click()
                    await element.fill(text)
                    await self.grok_page.keyboard.press("Enter")
                    
                    # Brief wait and error check
                    await asyncio.sleep(1)
                    error_msg = await self.detect_ui_errors()
                    if error_msg:
                        print(f"Text input error: {error_msg}")
                        if attempt < self.config["max_retries"] - 1:
                            await asyncio.sleep(self.config["retry_delay"])
                            continue
                        return False
                    
                    print("Text input sent")
                    return True
                except Exception as e:
                    print(f"Text input failed: {e}")
                    if attempt < self.config["max_retries"] - 1:
                        await asyncio.sleep(self.config["retry_delay"])
                        continue
            else:
                if attempt < self.config["max_retries"] - 1:
                    await asyncio.sleep(self.config["retry_delay"])
                    continue
        return False
    
    async def get_latest_response(self):
        """Get latest response text"""
        try:
            elements = await self.grok_page.locator(self.RESPONSE_SELECTOR).all()
            if elements:
                last_response = elements[-1]
                text = await last_response.inner_text()
                return text.strip() if text else ""
        except Exception:
            pass
        return ""
    
    async def wait_for_response(self):
        """Wait for Grok response with character limit instead of timeout"""
        print("Waiting for response...")
        last_text = ""
        stable_count = 0
        response_started = False
        max_chars = self.config["max_response_chars"]
        max_wait_time = self.config["max_wait_time"]
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < max_wait_time:
            # Check for UI errors
            error_msg = await self.detect_ui_errors()
            if error_msg and "grok" not in error_msg.lower():
                # Rate limit detection
                if "rate limit" in error_msg.lower() or "too many" in error_msg.lower():
                    print("Rate limit detected, waiting...")
                    await asyncio.sleep(30)
                    continue
                return f"Error: {error_msg}"
            
            # Check if we're still in the right state
            if not await self.has_messages() and response_started:
                return "Error: Lost thread view during response"
            
            current_text = await self.get_latest_response()
            
            if current_text and len(current_text) > self.config["min_response_length"]:
                response_started = True
                
                # Check if we've hit the character limit
                if len(current_text) >= max_chars:
                    print(f"Character limit reached: {len(current_text)} chars, truncating")
                    return current_text[:max_chars]
                
                if current_text == last_text:
                    stable_count += 1
                    if stable_count >= self.config["required_stable_checks"]:
                        print(f"Response captured: {len(current_text)} chars")
                        return current_text
                else:
                    stable_count = 0
                    last_text = current_text
                    print(f"Response growing: {len(current_text)} chars")
            
            await asyncio.sleep(self.config["stabilization_check_interval"])
        
        # Fallback timeout handling
        if last_text and len(last_text) > self.config["min_response_length"]:
            print("Max wait time reached, returning response")
            return last_text[:max_chars] if len(last_text) > max_chars else last_text
        
        return "Error: No response received"
    
    async def start_new_conversation(self):
        """Start a new conversation with retry and validation"""
        if await self.is_new_conversation():
            print("Already in new conversation")
            return True
        
        # Try new chat button first
        for attempt in range(self.config["max_retries"]):
            element = await self.find_element(self.NEW_CHAT_SELECTOR, "new chat button")
            if element:
                try:
                    await element.click()
                    await asyncio.sleep(self.config["new_conversation_wait"])
                    
                    if await self.is_new_conversation():
                        print("Started new conversation")
                        return True
                    
                    # Check if URL changed (alternative success indicator)
                    if self.grok_page.url in ["https://grok.com", "https://grok.com/"]:
                        print("Navigated to main page")
                        return True
                        
                except Exception as e:
                    print(f"New chat button failed: {e}")
            
            if attempt < self.config["max_retries"] - 1:
                await asyncio.sleep(self.config["retry_delay"])
        
        # Fallback: direct navigation
        print("Trying direct navigation...")
        for attempt in range(2):  # Fewer retries for navigation
            try:
                await self.grok_page.goto("https://grok.com")
                await self.grok_page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)
                
                if await self.is_new_conversation():
                    print("Navigation successful")
                    return True
                    
            except Exception as e:
                print(f"Navigation attempt {attempt + 1} failed: {e}")
                if attempt == 0:
                    await asyncio.sleep(3)
        
        print("Warning: Could not start new conversation")
        return False
    
    async def process_prompt(self, prompt_id, prompt_text):
        """Process a single prompt with comprehensive error recovery"""
        print(f"Processing prompt {prompt_id}: {prompt_text[:50]}...")
        
        for attempt in range(self.config["max_retries"]):
            try:
                # Check for persistent UI errors
                error_msg = await self.detect_ui_errors()
                if error_msg and "grok" not in error_msg.lower():
                    print(f"Pre-prompt UI error: {error_msg}")
                    if attempt < self.config["max_retries"] - 1:
                        await self.grok_page.reload()
                        await self.grok_page.wait_for_load_state("networkidle")
                        await asyncio.sleep(2)
                        continue
                    return {"id": prompt_id, "prompt": prompt_text, "grok_reply": f"Error: Persistent UI error - {error_msg}"}
                
                # Ensure new conversation
                if not await self.start_new_conversation():
                    if attempt < self.config["max_retries"] - 1:
                        print("Retrying new conversation...")
                        await asyncio.sleep(self.config["retry_delay"])
                        continue
                    return {"id": prompt_id, "prompt": prompt_text, "grok_reply": "Error: Could not start new conversation"}
                
                # Try voice mode first, fallback to text
                input_success = False
                if await self.try_voice_mode():
                    input_success = await self.generate_and_stream_tts(prompt_text)
                    if not input_success:
                        print("TTS failed, falling back to text")
                        input_success = await self.send_text_input(prompt_text)
                else:
                    input_success = await self.send_text_input(prompt_text)
                
                if not input_success:
                    if attempt < self.config["max_retries"] - 1:
                        print("Input failed, retrying...")
                        await asyncio.sleep(self.config["retry_delay"])
                        continue
                    return {"id": prompt_id, "prompt": prompt_text, "grok_reply": "Error: Failed to send input after retries"}
                
                # Wait for response
                response = await self.wait_for_response()
                
                # Validate response
                if response.startswith("Error:"):
                    if attempt < self.config["max_retries"] - 1:
                        print(f"Response error, retrying: {response}")
                        await asyncio.sleep(self.config["retry_delay"])
                        continue
                
                # Exit voice mode after getting response, before moving to next prompt
                print("Exiting voice mode after response...")
                await self.exit_voice_mode()
                
                print(f"Completed prompt {prompt_id}")
                return {
                    "id": prompt_id,
                    "prompt": prompt_text,
                    "grok_reply": response
                }
                
            except Exception as e:
                print(f"Error processing prompt {prompt_id} (attempt {attempt + 1}): {e}")
                if attempt < self.config["max_retries"] - 1:
                    await asyncio.sleep(self.config["retry_delay"])
                    continue
        
        return {"id": prompt_id, "prompt": prompt_text, "grok_reply": f"Error: Failed after {self.config['max_retries']} attempts"}
    
    
    async def run_automation(self, prompts_file="prompts.csv", results_file=None, resume=False):
        """Run the complete automation pipeline"""
        print("Starting GrokAutomation v0...")
        
        # Generate results filename if not provided
        if results_file is None:
            results_file = self.generate_results_filename()
            print(f"Using timestamped results file: {results_file}")
        
        # Load existing results for resume functionality
        completed_ids = set()
        if resume:
            completed_ids = self.load_existing_results(results_file)
        
        # Connect to Chrome with retry logic
        if not await self.connect_to_chrome_with_retry():
            return False
        
        try:
            # Load prompts
            print(f"Loading prompts from {prompts_file}")
            df = pd.read_csv(prompts_file, encoding='utf-8')
            print(f"Loaded {len(df)} prompts")
            
            # Validate CSV columns
            required_columns = ['id', 'text']
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                raise ValueError(f"Missing required columns in {prompts_file}: {missing_columns}")
            print(f"CSV validation passed")
            
            # Filter out already completed prompts if resuming
            if completed_ids:
                original_count = len(df)
                df = df[~df['id'].isin(completed_ids)]
                skipped_count = original_count - len(df)
                print(f"Skipping {skipped_count} already completed prompts")
                if len(df) == 0:
                    print("All prompts already completed!")
                    return True
            
            # Process all prompts (or limit for testing)
            self.results = []
            total_prompts = len(df)
            
            for i, (index, row) in enumerate(df.iterrows()):
                current_prompt = i + 1
                remaining = total_prompts - current_prompt
                
                # Progress display
                progress = current_prompt / total_prompts
                bar_length = self.config["progress_bar_length"]
                filled_length = int(bar_length * progress)
                bar = '#' * filled_length + '-' * (bar_length - filled_length)
                
                print(f"\n{'-'*60}")
                print(f"PROMPT {current_prompt}/{total_prompts} | ID: {row['id']} | {remaining} remaining")
                print(f"Progress: [{bar}] {progress:.1%}")
                print(f"Text: {row['text'][:80]}{'...' if len(row['text']) > 80 else ''}")
                print(f"{'-'*60}")
                
                result = await self.process_prompt(row['id'], row['text'])
                self.results.append(result)
                
                # Save each result immediately
                result_df = pd.DataFrame([result])
                if not os.path.exists(results_file):
                    # Create file with header if it doesn't exist
                    result_df.to_csv(results_file, index=False, encoding='utf-8')
                else:
                    # Append without header if file exists
                    result_df.to_csv(results_file, mode='a', header=False, index=False, encoding='utf-8')
                
                # Prepare for next prompt (handled in process_prompt)
                if i < len(df) - 1:
                    await asyncio.sleep(1)  # Brief pause between prompts
            
            # Results are saved immediately after each prompt
            
            print(f"\n{'-'*60}")
            print(f"AUTOMATION COMPLETE")
            print(f"Results saved to: {results_file}")
            print(f"Successfully processed: {len(self.results)}/{total_prompts} prompts")
            print(f"{'-'*60}")
            
            return True
            
        except Exception as e:
            print(f"Error during automation: {e}")
            return False
            
        finally:
            # Don't close browser - leave tab open
            pass
    
    async def cleanup(self):
        """Properly cleanup resources"""
        try:
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            print(f"Warning during cleanup: {e}")

async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="GrokAutomation - Automated Grok voice testing")
    parser.add_argument("--input", "-i", default="prompts.csv", help="Input CSV file with prompts (default: prompts.csv)")
    parser.add_argument("--output", "-o", help="Output CSV file for results (default: timestamped filename)")
    parser.add_argument("--resume", "-r", action="store_true", help="Resume from existing results file")
    
    args = parser.parse_args()
    
    automator = GrokAutomator()
    try:
        success = await automator.run_automation(
            prompts_file=args.input,
            results_file=args.output,
            resume=args.resume
        )
        
        if success:
            print("\nGrokAutomation completed successfully")
        else:
            print("\nGrokAutomation failed - check Chrome connection and Grok login")
    finally:
        await automator.cleanup()

if __name__ == "__main__":
    asyncio.run(main())