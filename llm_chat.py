#!/usr/bin/env python3
"""
Interactive Chat with Ollama LLM
Make sure you are on the **same node** where Ollama server is running
Usage: python ollama_llm_chat.py
"""

import requests
import json
import sys
from typing import Optional

class OllamaChat:
    def __init__(self, base_url: str = None, model: str = None):
        self.base_url = base_url or "http://127.0.0.1:11434"
        self.model = model or "gpt-oss:20b"
        self.chat_url = f"{base_url}/api/chat"
        self.generate_url = f"{base_url}/api/generate"
        self.conversation_history = []
        
    def check_server_status(self) -> bool:
        """Check if Ollama server is running and accessible"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                available_models = [model['name'] for model in models]
                print(f"✅ Ollama server is running!")
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
            print("🔧 Make sure you're on the same node where Ollama is running")
            print("💡 Try running: srun --jobid=42162557 --pty bash")
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
    """Main function"""
    import os
    
    # Get defaults from environment or use fallbacks
    base_url = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434")
    model = os.getenv("LLM_MODEL", "gpt-oss:20b")
    
    # Allow command line arguments to override
    if len(sys.argv) > 1:
        if sys.argv[1] in ['-h', '--help']:
            print("Usage: python ollama_llm_chat.py [base_url] [model]")
            print("Example: python ollama_llm_chat.py http://localhost:11434 llama2")
            print(f"Default base_url: {os.getenv('LLM_BASE_URL', 'http://127.0.0.1:11434')}")
            print(f"Default model: {os.getenv('LLM_MODEL', 'gpt-oss:20b')}")
            return
        if len(sys.argv) > 1:
            base_url = sys.argv[1]
        if len(sys.argv) > 2:
            model = sys.argv[2]
    
    # Create and start chat
    chat = OllamaChat(base_url=base_url, model=model)
    chat.interactive_chat()

if __name__ == "__main__":
    main()
