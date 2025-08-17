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
    # Selector constants
    VOICE_SELECTORS = [
        "[aria-label*='voice']",
        "[aria-label*='Voice']", 
        "[data-testid*='voice']",
        "button[title*='voice']",
        "button[title*='Voice']",
        ".voice-button",
        "[class*='voice']"
    ]
    
    TEXT_INPUT_SELECTORS = [
        "textarea[placeholder*='Ask Grok']",
        "textarea[placeholder*='Message']", 
        "input[placeholder*='Ask Grok']",
        "input[placeholder*='Message']",
        "[contenteditable='true']",
        "textarea",
        "input[type='text']",
        "[role='textbox']"
    ]
    
    RESPONSE_SELECTORS = [
        ".response-content-markdown",
        ".message-bubble",
        "[class*='message-bubble']",
        "[class*='response-content']",
        ".message.assistant",
        "[class*='message'][class*='assistant']",
        "[data-role='assistant']",
        ".response",
        "[class*='response']"
    ]
    
    NEW_CHAT_SELECTORS = [
        # Common patterns for new chat buttons
        "[aria-label*='New chat']",
        "[aria-label*='New conversation']",
        "[aria-label*='Start new']",
        "[aria-label*='new chat']",
        "[aria-label*='new conversation']",
        "button[title*='New chat']",
        "button[title*='New conversation']",
        "button[title*='new chat']",
        "[data-testid*='new-chat']",
        "[data-testid*='new-conversation']",
        "[data-testid*='newchat']",
        # Class-based selectors
        ".new-chat-button",
        ".new-conversation-button",
        ".newchat-button",
        "[class*='new-chat']",
        "[class*='new-conversation']",
        "[class*='newchat']",
        # Text-based selectors
        "button:has-text('New chat')",
        "button:has-text('New Chat')",
        "button:has-text('New')",
        "button:has-text('Start')",
        "[role='button']:has-text('New')",
        "[role='button']:has-text('Start')",
        # Plus icon buttons (common for new chat)
        "button[aria-label*='+']",
        "button:has([data-icon='plus'])",
        "button svg[data-icon='plus']",
        # Generic buttons that might be new chat
        "button[class*='primary']",
        "button[class*='compose']",
        "a[href='/']",
        "a[href='https://grok.com']"
    ]

    def __init__(self):
        self.browser = None
        self.grok_page = None
        self.results = []
        self.playwright = None
        self.config = self.load_config()
    
    def load_config(self):
        """Load configuration from config.json with fallback to defaults"""
        default_config = {
            "chrome_port": 9222,
            "response_timeout": 90,
            "tts_voice": "en-US-JennyNeural",
            "audio_wait_seconds": 2,
            "new_conversation_wait": 3,
            # Magic number constants
            "min_response_length": 10,
            "required_stable_checks": 3,
            "progress_bar_length": 20,
            "stabilization_check_interval": 1.0,
            "element_search_interval": 0.5
        }
        
        try:
            if os.path.exists("config.json"):
                with open("config.json", "r") as f:
                    user_config = json.load(f)
                    # Merge user config with defaults
                    default_config.update(user_config)
                    print(f"Loaded config from config.json")
            else:
                print("No config.json found, using defaults")
        except Exception as e:
            print(f"Error loading config.json: {e}, using defaults")
        
        return default_config
    
    async def find_clickable_element(self, selectors, description="element"):
        """Helper method to find and return the first clickable element from selector list"""
        print(f"Looking for {description}...")
        
        for selector in selectors:
            try:
                count = await self.grok_page.locator(selector).count()
                if count > 0:
                    element = self.grok_page.locator(selector).first
                    is_visible = await element.is_visible()
                    is_enabled = await element.is_enabled()
                    
                    if is_visible and is_enabled:
                        print(f"Found {description}: {selector}")
                        return element
                        
            except Exception as e:
                print(f"Error testing {description} selector {selector}: {e}")
        
        print(f"{description.capitalize()} not found")
        return None
    
    def load_existing_results(self, results_file):
        """Load existing results to enable resume functionality"""
        completed_ids = set()
        if os.path.exists(results_file):
            try:
                existing_df = pd.read_csv(results_file)
                completed_ids = set(existing_df['id'].tolist())
                print(f"Found {len(completed_ids)} already completed prompts in {results_file}")
            except Exception as e:
                print(f"Error reading existing results: {e}")
        return completed_ids
    
    def generate_results_filename(self, base_name="results"):
        """Generate timestamped results filename"""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        return f"{base_name}_{timestamp}.csv"
        
    async def connect_to_chrome(self):
        """Connect to Chrome browser via CDP"""
        try:
            print("Connecting to Chrome via CDP...")
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.connect_over_cdp(f"http://localhost:{self.config['chrome_port']}")
            
            # Get existing contexts and find Grok tab
            contexts = self.browser.contexts
            if not contexts:
                raise Exception("No browser contexts found")
                
            context = contexts[0]
            pages = context.pages
            
            # Find existing Grok tab or create new one
            self.grok_page = None
            for page in pages:
                if "grok.com" in page.url:
                    self.grok_page = page
                    break
            
            if not self.grok_page:
                print("No Grok tab found, creating new one...")
                self.grok_page = await context.new_page()
                await self.grok_page.goto("https://grok.com")
                await self.grok_page.wait_for_load_state("networkidle")
            else:
                print("Using existing Grok tab")
                await self.grok_page.bring_to_front()
            
            print("Chrome connection established successfully")
            return True
            
        except Exception as e:
            print(f"Failed to connect to Chrome: {e}")
            print("Make sure Chrome is running with: start_chrome_debug.bat")
            return False
    
    async def find_voice_button(self):
        """Find and click the voice button to enable voice mode"""
        element = await self.find_clickable_element(self.VOICE_SELECTORS, "voice button")
        if element:
            await element.click()
            await asyncio.sleep(self.config["audio_wait_seconds"])
            return True
        
        print("Voice button not found - trying text input instead")
        return False
    
    async def generate_and_stream_tts(self, text):
        """Generate TTS audio and stream to virtual microphone"""
        print(f"Converting to speech: '{text}'")
        
        # Create temporary file for audio
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            tmp_path = tmp_file.name
        
        try:
            # Generate TTS audio using edge-tts
            communicate = edge_tts.Communicate(text, self.config["tts_voice"])
            await communicate.save(tmp_path)
            
            # Load audio data
            data, samplerate = sf.read(tmp_path)
            
            print("Streaming audio to virtual microphone...")
            # Stream to default recording device (should be VB-Cable)
            sd.play(data, samplerate)
            sd.wait()  # Wait for playback to complete
            
            print("Audio streaming complete")
            return True
            
        except Exception as e:
            print(f"Error with TTS: {e}")
            return False
            
        finally:
            # Cleanup
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    async def send_text_input(self, text):
        """Fallback: send text input directly"""
        element = await self.find_clickable_element(self.TEXT_INPUT_SELECTORS, "text input element")
        if element:
            await element.click()
            await asyncio.sleep(0.5)
            await element.fill("")
            await asyncio.sleep(0.5)
            await element.type(text, delay=50)
            await asyncio.sleep(1)
            
            # Submit the message
            await self.grok_page.keyboard.press("Enter")
            return True
        
        print("No suitable input element found")
        return False
    
    async def get_latest_response_text(self):
        """Helper method to extract latest response text"""
        for selector in self.RESPONSE_SELECTORS:
            try:
                elements = await self.grok_page.locator(selector).all()
                if elements:
                    last_response = elements[-1]
                    text = await last_response.inner_text()
                    if text.strip():
                        return text
            except Exception:
                continue
        return ""
    
    async def wait_for_response(self, timeout=None):
        """Wait for Grok text response to appear and stabilize"""
        if timeout is None:
            timeout = self.config["response_timeout"]
        print("Waiting for Grok response...")
        
        try:
            # Wait for initial response to appear
            response_found = False
            start_time = asyncio.get_event_loop().time()
            
            while not response_found and (asyncio.get_event_loop().time() - start_time) < timeout:
                response_text = await self.get_latest_response_text()
                if response_text and len(response_text.strip()) > self.config["min_response_length"]:
                    print(f"Response detected")
                    response_found = True
                    break
                
                await asyncio.sleep(self.config["element_search_interval"])
            
            if not response_found:
                print("No response detected within timeout")
                return "Error: No response detected"
            
            # Monitor text stabilization (when text stops changing)
            print("Monitoring text stabilization...")
            last_text = ""
            stable_count = 0
            required_stable_checks = self.config["required_stable_checks"]
            
            while stable_count < required_stable_checks:
                current_text = await self.get_latest_response_text()
                
                # Check if text has stabilized
                if current_text == last_text and len(current_text.strip()) > self.config["min_response_length"]:
                    stable_count += 1
                    print(f"Text stable ({stable_count}/{required_stable_checks})")
                else:
                    stable_count = 0
                    if len(current_text) > len(last_text):
                        print(f"Text growing: {len(current_text)} chars")
                
                last_text = current_text
                await asyncio.sleep(self.config["stabilization_check_interval"])
            
            print(f"Response stabilized! Captured {len(last_text)} characters")
            print(f"Preview: {last_text[:100]}...")
            return last_text.strip()
            
        except Exception as e:
            print(f"Error waiting for response: {e}")
            return "Error: Response capture failed"
    
    async def start_new_conversation(self):
        """Start a new conversation by finding and clicking the new chat button"""
        print("Starting new conversation...")
        
        # First check current URL to understand context
        current_url = self.grok_page.url
        print(f"Current URL: {current_url}")
        
        # Try to find and click new chat button
        for selector in self.NEW_CHAT_SELECTORS:
            try:
                elements = await self.grok_page.locator(selector).all()
                if elements:
                    for element in elements:
                        try:
                            is_visible = await element.is_visible()
                            is_enabled = await element.is_enabled()
                            
                            if is_visible and is_enabled:
                                # Get element text/aria-label for better identification
                                text_content = ""
                                try:
                                    text_content = await element.inner_text()
                                    if not text_content:
                                        text_content = await element.get_attribute("aria-label") or ""
                                except:
                                    pass
                                
                                print(f"Trying element: {selector} (text: '{text_content}')")
                                await element.click()
                                await asyncio.sleep(3)  # Wait for navigation/loading
                                
                                # Check if URL changed or new conversation started
                                new_url = self.grok_page.url
                                if new_url != current_url or new_url == "https://grok.com" or new_url == "https://grok.com/":
                                    print(f"Successfully started new conversation - URL: {new_url}")
                                    return True
                                    
                        except Exception as e:
                            print(f"Error clicking element {selector}: {e}")
                            continue
                            
            except Exception as e:
                print(f"Error processing selector {selector}: {e}")
                continue
        
        # Alternative: navigate directly to main grok page
        print("New chat button not found, navigating to main page...")
        try:
            await self.grok_page.goto("https://grok.com")
            await self.grok_page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)
            print(f"Navigated to main page - URL: {self.grok_page.url}")
            return True
        except Exception as e:
            print(f"Error navigating to main page: {e}")
        
        # Last resort: try page refresh
        print("Trying page refresh...")
        try:
            await self.grok_page.reload()
            await self.grok_page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            print("Page refreshed")
            return True
        except Exception as e:
            print(f"Page refresh failed: {e}")
        
        print("Warning: Could not start new conversation")
        return False
    
    async def process_prompt(self, prompt_id, prompt_text):
        """Process a single prompt through the voice pipeline"""
        print(f"Processing prompt ID: {prompt_id}")
        
        try:
            # Try voice mode first
            voice_mode_activated = await self.find_voice_button()
            
            if voice_mode_activated:
                # Use voice input
                success = await self.generate_and_stream_tts(prompt_text)
                if not success:
                    print("TTS failed, falling back to text input")
                    success = await self.send_text_input(prompt_text)
            else:
                # Use text input as fallback
                success = await self.send_text_input(prompt_text)
            
            if not success:
                return {"id": prompt_id, "prompt": prompt_text, "grok_reply": "Error: Failed to send input"}
            
            # Wait for and capture response
            response = await self.wait_for_response()
            
            result = {
                "id": prompt_id,
                "prompt": prompt_text, 
                "grok_reply": response
            }
            
            print(f"Completed prompt {prompt_id}")
            return result
            
        except Exception as e:
            print(f"Error processing prompt {prompt_id}: {e}")
            return {"id": prompt_id, "prompt": prompt_text, "grok_reply": f"Error: {e}"}
    
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
        
        # Connect to Chrome
        if not await self.connect_to_chrome():
            return False
        
        try:
            # Load prompts
            print(f"Loading prompts from {prompts_file}")
            df = pd.read_csv(prompts_file)
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
            
            for index, row in df.iterrows():
                current_prompt = index + 1
                remaining = total_prompts - current_prompt
                
                # Progress display
                progress = current_prompt / total_prompts
                bar_length = self.config["progress_bar_length"]
                filled_length = int(bar_length * progress)
                bar = '█' * filled_length + '-' * (bar_length - filled_length)
                
                print(f"\n{'-'*60}")
                print(f"PROMPT {current_prompt}/{total_prompts} | ID: {row['id']} | {remaining} remaining")
                print(f"Progress: [{bar}] {progress:.1%}")
                print(f"Text: {row['text'][:80]}{'...' if len(row['text']) > 80 else ''}")
                print(f"{'-'*60}")
                
                result = await self.process_prompt(row['id'], row['text'])
                self.results.append(result)
                
                # Start new conversation for next prompt
                if index < len(df) - 1:  # Not the last prompt
                    print(f"\nStarting new conversation for next prompt...")
                    await self.start_new_conversation()
                    await asyncio.sleep(self.config["new_conversation_wait"])  # Allow UI to settle
            
            # Save results
            results_df = pd.DataFrame(self.results)
            
            # If resuming and file exists, append new results
            if resume and os.path.exists(results_file) and completed_ids:
                existing_df = pd.read_csv(results_file)
                combined_df = pd.concat([existing_df, results_df], ignore_index=True)
                combined_df.to_csv(results_file, index=False)
                print(f"Appended {len(results_df)} new results to {results_file}")
            else:
                results_df.to_csv(results_file, index=False)
                print(f"Saved results to {results_file}")
            
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