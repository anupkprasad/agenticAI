"""
Centralized LLM Configuration
Single source of truth for all LLM server addresses and models
"""
import os

# ===== OLLAMA SERVER CONFIGURATION =====
# Default: Use environment variable or fallback to localhost
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434")

# For remote connections, uncomment and modify:
# LLM_BASE_URL = "http://a1-23:11434"  # Ollama on ra5-5
# LLM_BASE_URL = "http://d5-15:11434"  # Ollama on d5-15
# LLM_BASE_URL = "http://hostname.domain:11434"  # Custom host

# ===== MODEL CONFIGURATION =====
DEFAULT_MODEL = os.getenv("LLM_MODEL", "gpt-oss:20b")

# ===== PAID API / TOKEN BUDGET =====
# Set LLM_API_KEY or OPENAI_API_KEY when using a hosted model.
# Token usage is always tracked to {working-dir}/llm_usage.json when LLM is used.
# Optional LLM_TOKEN_BUDGET / --llm-token-budget enforces a hard cap (recommended for paid APIs).
# LLM_PROVIDER: auto | ollama | openai
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
LLM_TOKEN_BUDGET = os.getenv("LLM_TOKEN_BUDGET") or os.getenv("OPENAI_TOKEN_BUDGET")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto")

# Alternative models (uncomment to use):
# DEFAULT_MODEL = "llama2:latest"
# DEFAULT_MODEL = "mistral:latest"
# DEFAULT_MODEL = "codellama:latest"

# ===== CONNECTION SETTINGS =====
TIMEOUT = 60  # seconds
MAX_RETRIES = 3

# ===== ENDPOINTS =====
def get_chat_url():
    """Get chat API endpoint"""
    return f"{LLM_BASE_URL}/api/chat"

def get_generate_url():
    """Get generate API endpoint"""
    return f"{LLM_BASE_URL}/api/generate"

def get_tags_url():
    """Get tags/models list endpoint"""
    return f"{LLM_BASE_URL}/api/tags"

# ===== HELPER FUNCTIONS =====
def get_llm_config():
    """Get complete LLM configuration as dictionary"""
    return {
        "base_url": LLM_BASE_URL,
        "model": DEFAULT_MODEL,
        "timeout": TIMEOUT,
        "max_retries": MAX_RETRIES,
        "token_budget": LLM_TOKEN_BUDGET,
        "provider": LLM_PROVIDER,
        "has_api_key": bool(LLM_API_KEY),
    }

def print_config():
    """Print current configuration"""
    print("=" * 60)
    print("🔧 LLM Configuration")
    print("=" * 60)
    print(f"Base URL:  {LLM_BASE_URL}")
    print(f"Model:     {DEFAULT_MODEL}")
    print(f"Timeout:   {TIMEOUT}s")
    print(f"Retries:   {MAX_RETRIES}")
    print("=" * 60)

if __name__ == "__main__":
    print_config()
