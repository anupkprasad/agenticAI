#!/usr/bin/env python3
"""
Interactive Chat with Ollama LLM
Supports both local and remote Ollama servers
Usage: python llm_chat.py [--remote NODE_NAME]
"""

import requests
import json
import sys
from typing import Optional
import llm_config  # Centralized LLM configuration

class OllamaChat:
    def __init__(self, base_url: str = None, model: str = None):
        # Use centralized config as defaults
        self.base_url = base_url or llm_config.LLM_BASE_URL
        self.model = model or llm_config.DEFAULT_MODEL
        self.chat_url = f"{self.base_url}/api/chat"
        self.generate_url = f"{self.base_url}/api/generate"
        self.conversation_history = []
        
    def check_server_status(self) -> bool:
        """Check if Ollama server is running and accessible (local or remote)"""
        try:
            print(f"🔍 Checking Ollama server at: {self.base_url}")
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            if response.status_code == 200:
                models = response.json().get('models', [])
                available_models = [model['name'] for model in models]
                print(f"✅ Ollama server is running!")
                print(f"🌐 Connected to: {self.base_url}")
                print(f"📋 Available models: {', '.join(available_models)}")
                
                # Check if our target model is available
                if self.model in available_models:
                    print(f"🎯 Using model: {self.model}")
                    return True
                else:
                    print(f"⚠️  Model '{self.model}' not found. Available: {available_models}")
                    if available_models:
                        self.model = available_models[0]
                        print(f"🔄 Switching to: {self.model}")
                        return True
                    return False
            else:
                print(f"❌ Server responded with status: {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            print("❌ Cannot connect to Ollama server at", self.base_url)
            print("🔧 Troubleshooting tips:")
            print("   1. Check if Ollama is running: ssh NODE 'curl -s http://localhost:11434/api/tags'")
            print("   2. Verify firewall allows port 11434")
            print("   3. Update llm_config.py with correct server address")
            print(f"   4. Try: ssh -L 11434:localhost:11434 NODE  # Port forwarding")
            return False
        except requests.exceptions.Timeout:
            print(f"⏰ Connection to {self.base_url} timed out")
            print("💡 Server might be slow or network issue")
            return False
        except Exception as e:
            print(f"❌ Error checking server: {e}")
            return False
    
    def send_message(self, message: str, use_history: bool = True) -> Optional[str]:
        """Send a message to the LLM and get response"""
        try:
            if use_history:
                # Use chat API with conversation history
                self.conversation_history.append({"role": "user", "content": message})
                
                payload = {
                    "model": self.model,
                    "messages": self.conversation_history,
                    "stream": False  # Get complete response at once
                }
                response = requests.post(self.chat_url, json=payload, timeout=60)
            else:
                # Use simple generate API
                payload = {
                    "model": self.model,
                    "prompt": message,
                    "stream": False
                }
                response = requests.post(self.generate_url, json=payload, timeout=60)
            
            if response.status_code == 200:
                data = response.json()
                
                if use_history and 'message' in data:
                    # Chat API response
                    assistant_message = data['message']['content']
                    self.conversation_history.append({"role": "assistant", "content": assistant_message})
                    return assistant_message
                elif not use_history and 'response' in data:
                    # Generate API response
                    return data['response']
                else:
                    print(f"❌ Unexpected response format: {data}")
                    return None
            else:
                print(f"❌ Request failed with status {response.status_code}: {response.text}")
                return None
                
        except requests.exceptions.Timeout:
            print("⏰ Request timed out. The model might be slow or overloaded.")
            return None
        except requests.exceptions.ConnectionError:
            print("❌ Connection lost to Ollama server")
            return None
        except Exception as e:
            print(f"❌ Error sending message: {e}")
            return None
    
    def interactive_chat(self):
        """Start an interactive chat session"""
        print("=" * 60)
        print("🤖 Ollama Interactive Chat")
        print("=" * 60)
        print("Commands:")
        print("  /quit or /exit - Exit the chat")
        print("  /clear - Clear conversation history")
        print("  /history - Show conversation history")
        print("  /model - Show current model")
        print("  /simple <message> - Send message without history")
        print("=" * 60)
        
        if not self.check_server_status():
            print("\n❌ Cannot start chat - server not accessible")
            return
        
        print(f"\n🎉 Chat started! You're talking with {self.model}")
        print("💬 Type your message and press Enter...\n")
        
        while True:
            try:
                user_input = input("You: ").strip()
                
                if not user_input:
                    continue
                    
                # Handle commands
                if user_input.lower() in ['/quit', '/exit']:
                    print("👋 Goodbye!")
                    break
                elif user_input.lower() == '/clear':
                    self.conversation_history = []
                    print("🧹 Conversation history cleared!")
                    continue
                elif user_input.lower() == '/history':
                    if self.conversation_history:
                        print("\n📜 Conversation History:")
                        for i, msg in enumerate(self.conversation_history):
                            role = msg['role'].title()
                            content = msg['content'][:100] + "..." if len(msg['content']) > 100 else msg['content']
                            print(f"  {i+1}. {role}: {content}")
                        print()
                    else:
                        print("📭 No conversation history yet")
                    continue
                elif user_input.lower() == '/model':
                    print(f"🎯 Current model: {self.model}")
                    continue
                elif user_input.lower().startswith('/simple '):
                    message = user_input[8:]  # Remove '/simple ' prefix
                    print("🤖 Assistant: ", end="")
                    response = self.send_message(message, use_history=False)
                    if response:
                        print(response)
                    print()
                    continue
                
                # Send regular message
                print("🤖 Assistant: ", end="")
                response = self.send_message(user_input)
                if response:
                    print(response)
                else:
                    print("❌ Failed to get response")
                print()
                
            except KeyboardInterrupt:
                print("\n\n👋 Chat interrupted. Goodbye!")
                break
            except EOFError:
                print("\n\n👋 Input ended. Goodbye!")
                break

def main():
    """Main function with remote node support"""
    import os
    
    # Start with centralized config
    base_url = llm_config.LLM_BASE_URL
    model = llm_config.DEFAULT_MODEL
    
    # Allow command line arguments to override
    if len(sys.argv) > 1:
        if sys.argv[1] in ['-h', '--help']:
            print("=" * 60)
            print("🤖 Ollama Chat - Local & Remote Support")
            print("=" * 60)
            print("Usage:")
            print("  python llm_chat.py                    # Use config from llm_config.py")
            print("  python llm_chat.py [base_url]         # Override base URL")
            print("  python llm_chat.py [base_url] [model] # Override both")
            print("  python llm_chat.py --remote NODE      # Quick remote connection")
            print()
            print("Examples:")
            print("  python llm_chat.py --remote ra5-5")
            print("  python llm_chat.py http://ra5-5:11434")
            print("  python llm_chat.py http://localhost:11434 llama2")
            print()
            print("Current config (from llm_config.py):")
            print(f"  Base URL: {llm_config.LLM_BASE_URL}")
            print(f"  Model:    {llm_config.DEFAULT_MODEL}")
            print()
            print("To permanently change, edit llm_config.py")
            print("=" * 60)
            return
        
        # Handle --remote flag for quick remote connections
        if sys.argv[1] == '--remote' and len(sys.argv) > 2:
            node = sys.argv[2]
            base_url = f"http://{node}:11434"
            print(f"🌐 Connecting to remote Ollama on {node}...")
        elif len(sys.argv) > 1 and not sys.argv[1].startswith('-'):
            base_url = sys.argv[1]
        if len(sys.argv) > 2 and sys.argv[1] != '--remote':
            model = sys.argv[2]
    
    # Show configuration
    print(f"📍 Using base URL: {base_url}")
    print(f"🤖 Using model: {model}")
    print()
    
    # Create and start chat
    chat = OllamaChat(base_url=base_url, model=model)
    chat.interactive_chat()

if __name__ == "__main__":
    main()

