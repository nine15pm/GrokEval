#!/usr/bin/env python3
"""
Grok UI Discovery Tool
Connects to existing Chrome/Grok session and discovers working UI patterns
"""

import asyncio
import json
from datetime import datetime
from playwright.async_api import async_playwright

class GrokUIDiscovery:
    def __init__(self, chrome_port=9222):
        self.chrome_port = chrome_port
        self.playwright = None
        self.browser = None
        self.page = None
        self.findings = {
            "timestamp": datetime.now().isoformat(),
            "url": "",
            "voice_buttons": [],
            "text_inputs": [],
            "new_chat_buttons": [],
            "response_containers": [],
            "error_elements": []
        }
    
    async def connect(self):
        """Connect to existing Chrome session"""
        try:
            print("Connecting to Chrome...")
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.connect_over_cdp(f"http://localhost:{self.chrome_port}")
            
            # Find Grok page
            for context in self.browser.contexts:
                for page in context.pages:
                    if "grok.com" in page.url:
                        self.page = page
                        break
                if self.page:
                    break
            
            if not self.page:
                print("No Grok page found. Please open grok.com in Chrome first.")
                return False
            
            await self.page.bring_to_front()
            self.findings["url"] = self.page.url
            print(f"Connected to: {self.page.url}")
            return True
            
        except Exception as e:
            print(f"Connection failed: {e}")
            return False
    
    async def discover_elements(self, category, potential_selectors, description):
        """Test selectors and find working ones"""
        print(f"\n=== Discovering {description} ===")
        working_selectors = []
        
        for selector in potential_selectors:
            try:
                elements = await self.page.locator(selector).all()
                if elements:
                    for i, element in enumerate(elements):
                        try:
                            is_visible = await element.is_visible()
                            is_enabled = await element.is_enabled()
                            
                            if is_visible:
                                # Get element details
                                tag_name = await element.evaluate("el => el.tagName.toLowerCase()")
                                text_content = await element.inner_text() if tag_name != "input" else ""
                                aria_label = await element.get_attribute("aria-label") or ""
                                placeholder = await element.get_attribute("placeholder") or ""
                                class_name = await element.get_attribute("class") or ""
                                
                                element_info = {
                                    "selector": selector,
                                    "index": i,
                                    "tag": tag_name,
                                    "visible": is_visible,
                                    "enabled": is_enabled,
                                    "text": text_content[:100],
                                    "aria_label": aria_label,
                                    "placeholder": placeholder,
                                    "class": class_name,
                                    "bounding_box": await element.bounding_box()
                                }
                                
                                working_selectors.append(element_info)
                                print(f"Found: {selector} - {tag_name} - '{text_content[:50]}' - '{aria_label}'")
                                
                        except Exception as e:
                            print(f"  Error testing element {i}: {e}")
                            
            except Exception as e:
                print(f"  Error with selector '{selector}': {e}")
        
        self.findings[category] = working_selectors
        print(f"Found {len(working_selectors)} working {description}")
        return working_selectors
    
    async def run_discovery(self):
        """Run full UI discovery"""
        if not await self.connect():
            return False
        
        # Voice button patterns to test
        voice_selectors = [
            "[aria-label*='voice']",
            "[aria-label*='Voice']", 
            "button[title*='voice']",
            "button[title*='Voice']",
            "[data-testid*='voice']",
            "button:has-text('voice')",
            "button:has-text('Voice')",
            "[class*='voice']"
        ]
        
        # Text input patterns
        text_input_selectors = [
            "textarea",
            "input[type='text']",
            "[contenteditable='true']",
            "[role='textbox']",
            "textarea[placeholder*='Ask']",
            "textarea[placeholder*='Message']"
        ]
        
        # New chat button patterns
        new_chat_selectors = [
            "button:has-text('New')",
            "button:has-text('new')",
            "[aria-label*='New']",
            "[aria-label*='new']",
            "a[href='/']",
            "a[href='https://grok.com']",
            "[class*='new']"
        ]
        
        # Response container patterns
        response_selectors = [
            "[class*='message']",
            "[class*='response']",
            "[role='log']",
            "[data-testid*='message']",
            "[data-testid*='response']"
        ]
        
        # Error element patterns
        error_selectors = [
            "[role='alert']",
            "[class*='error']",
            "[class*='Error']",
            "[aria-label*='error']"
        ]
        
        # Run discoveries
        await self.discover_elements("voice_buttons", voice_selectors, "voice buttons")
        await self.discover_elements("text_inputs", text_input_selectors, "text inputs")
        await self.discover_elements("new_chat_buttons", new_chat_selectors, "new chat buttons")
        await self.discover_elements("response_containers", response_selectors, "response containers")
        await self.discover_elements("error_elements", error_selectors, "error elements")
        
        return True
    
    async def detect_page_state(self):
        """Auto-detect what state the page is in based on visible elements"""
        # Check for indicators of different states
        indicators = {
            "has_messages": False,
            "has_empty_input": False,
            "has_voice_button": False,
            "has_response_area": False
        }
        
        try:
            # Check for existing messages/conversation
            message_selectors = ["[class*='message']", "[role='log']", "[class*='conversation']"]
            for selector in message_selectors:
                if await self.page.locator(selector).count() > 0:
                    indicators["has_messages"] = True
                    break
            
            # Check for empty input (new conversation indicator)
            input_elements = await self.page.locator("[contenteditable='true']").all()
            for element in input_elements:
                if await element.is_visible():
                    text = await element.inner_text()
                    if not text.strip():
                        indicators["has_empty_input"] = True
                    break
            
            # Check for voice button
            voice_elements = await self.page.locator("[aria-label*='voice']").all()
            indicators["has_voice_button"] = len(voice_elements) > 0
            
            # Determine state
            if indicators["has_messages"]:
                state = "thread_view"
            elif indicators["has_empty_input"]:
                state = "new_conversation"
            else:
                state = "unknown"
                
        except Exception as e:
            print(f"Error detecting state: {e}")
            state = "unknown"
        
        return state
    
    async def save_findings(self, filename=None):
        """Save findings to JSON file with auto-detected state naming"""
        if filename is None:
            state = await self.detect_page_state()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"grok_ui_{state}_{timestamp}.json"
        
        # Add detected state to findings
        self.findings["detected_state"] = await self.detect_page_state()
        
        with open(filename, "w") as f:
            json.dump(self.findings, f, indent=2)
        print(f"\nFindings saved to: {filename}")
        return filename
    
    
    async def cleanup(self):
        """Cleanup resources"""
        try:
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            print(f"Cleanup error: {e}")

async def main():
    """Run UI discovery"""
    discovery = GrokUIDiscovery()
    
    try:
        print("Grok UI Discovery Tool")
        print("=" * 30)
        print("Make sure:")
        print("1. Chrome is running with debug port (start_chrome_debug.bat)")
        print("2. You're logged into grok.com")
        print("3. Navigate to the page you want to discover (new chat, thread, etc.)")
        
        print("\nStarting discovery in 2 seconds...")
        await asyncio.sleep(2)
        
        if await discovery.run_discovery():
            await discovery.save_findings()
            print("\nDiscovery complete!")
        else:
            print("\n✗ Discovery failed")
            
    finally:
        await discovery.cleanup()

if __name__ == "__main__":
    asyncio.run(main())