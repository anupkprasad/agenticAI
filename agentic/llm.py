"""Simple LLM client wrapper for ChatOllama or similar local LLMs.

This module provides a small, forgiving wrapper around the `ChatOllama`
style client you provided. It falls back to a harmless mock when the
dependency is not available, so the rest of the codebase can remain testable.

Example usage:
    from agentic.llm import LLMClient
    llm = LLMClient(model="gpt-oss:120b", base_url="http://172.22.149.139:11434")
    resp = llm.prompt("Summarize the following PDB: ...")
    print(resp)
"""
from __future__ import annotations

from typing import Optional, List, Any
from dataclasses import dataclass
import re
import uuid
import logging
import json
import urllib.parse
from typing import Any

try:
    import requests
except Exception:
    requests = None

logger = logging.getLogger(__name__)

# Try to import the correct ollama client; if not installed,
# we'll operate in a mock mode but will attempt HTTP calls to base_url if given.
ollama_client = None
try:
    # Use the correct ollama Client class
    import ollama
    ollama_client = ollama
except Exception:
    ollama_client = None


class LLMClient:
    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        self.model = model
        self.base_url = base_url
        self._client = None
        self._is_mock_mode = False  # Track if we're in mock mode
        
        # load optional configuration (system prompt, tokens) from agentic/config.json
        self.config = {}
        try:
            import os, json as _json
            cfg_path = os.path.join(os.path.dirname(__file__), "config.json")
            if os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as fh:
                    self.config = _json.load(fh)
        except Exception:
            self.config = {}
        # allow passing a system_prompt directly via kwargs
        self.system_prompt = kwargs.pop("system_prompt", self.config.get("system_prompt"))
        # Optional tool list (for compatibility with tool-using frameworks)
        self.tools: Optional[List[Any]] = kwargs.pop("tools", None)
        if ollama_client is None:
            logger.info("ollama client not available; LLMClient will run in mock mode or HTTP-fallback if base_url provided")
            self._is_mock_mode = True
        else:
            # Use the ollama client with base_url if provided
            try:
                # Create a client instance if base_url is provided
                if base_url:
                    self._client = ollama.Client(host=base_url)
                else:
                    self._client = ollama_client  # Use the module directly
                self._is_mock_mode = False
                logger.info(f"ollama client initialized with model: {model}, base_url: {base_url}")
            except Exception as e:
                logger.warning(f"Failed to initialize ollama client: {e}")
                self._client = None
                self._is_mock_mode = True

    def prompt(self, prompt: str, system: Optional[str] = None, **kwargs) -> str:
        """Send a prompt to the LLM and return a text response.

        This method attempts a few common client call signatures to remain
        compatible with different local LLM clients. If no real client is
        available, a mock response is returned.
        """
        if self._client is None:
            # If a base_url is provided, try an HTTP fallback to the LLM server
            if self.base_url:
                try:
                    # prefer the instance-level system prompt if available
                    sysp = system if system is not None else self.system_prompt
                    return self._http_call(prompt, system=sysp, **kwargs)
                except Exception as e:
                    logger.exception("HTTP LLM call failed; falling back to mock")
                    self._last_raw_response = f"HTTP_LLM_ERROR: {e}"
                    return f"MOCK_LLM_RESPONSE: would send: {prompt[:200]}"
            self._last_raw_response = f"MOCK_LLM_RESPONSE: would send: {prompt[:200]}"
            return f"MOCK_LLM_RESPONSE: would send: {prompt[:200]}"

        # Try ollama API first
        try:
            # Prepare system prompt
            sysp = system if system is not None else self.system_prompt
            
            # Use ollama chat API
            messages = []
            if sysp:
                messages.append({"role": "system", "content": sysp})
            messages.append({"role": "user", "content": prompt})
            
            # Call ollama chat
            if hasattr(self._client, "chat"):
                # If using ollama.Client instance
                out = self._client.chat(model=self.model, messages=messages)
            else:
                # If using ollama module directly
                out = ollama_client.chat(model=self.model, messages=messages)
                
        except Exception as e:
            logger.exception("ollama call failed; trying fallback HTTP")
            # Fallback to HTTP call if ollama direct call fails
            if self.base_url:
                try:
                    sysp = system if system is not None else self.system_prompt
                    return self._http_call(prompt, system=sysp, **kwargs)
                except Exception as e2:
                    logger.exception("HTTP LLM call also failed; falling back to mock")
                    self._last_raw_response = f"HTTP_LLM_ERROR: {e2}"
                    return f"MOCK_LLM_RESPONSE: would send: {prompt[:200]}"
            else:
                logger.exception("LLM call failed and no base_url for HTTP fallback")
                self._last_raw_response = f"LLM_ERROR: {e}"
                return f"LLM_ERROR: {e}"

        # Normalize ollama response format
        try:
            if isinstance(out, str):
                # record raw string response
                self._last_raw_response = out
                return out
            if isinstance(out, dict):
                # record raw dict response
                try:
                    self._last_raw_response = json.dumps(out)
                except Exception:
                    self._last_raw_response = str(out)
                    
                # Handle ollama chat response format
                if "message" in out and isinstance(out["message"], dict):
                    if "content" in out["message"]:
                        return out["message"]["content"]
                        
                # common keys for other formats
                for k in ("text", "response", "content"):
                    if k in out:
                        return out[k]
                        
                # openai-style
                if "choices" in out and out["choices"]:
                    c = out["choices"][0]
                    return c.get("text") or c.get("message", {}).get("content", str(out))
                    
            # Handle ollama response objects (with .message.content attribute)
            if hasattr(out, 'message') and hasattr(out.message, 'content'):
                content = out.message.content
                self._last_raw_response = str(out)
                return content
                
            # fallback to string conversion
            return str(out)
        except Exception:
            return str(out)

    # --- Compatibility adapter for frameworks that call `invoke` ---
    @dataclass
    class InvokeResult:
        content: str
        tool_calls: list
        validation_errors: dict = None

    def invoke(self, messages: List[Any]) -> Any:
        """Compatibility wrapper so callers can use `llm.invoke(messages)`.

        This implements a minimal, forgiving interface: it turns a list of
        message-like objects into a prompt string, calls `prompt()` and
        returns an object with `.content` and `.tool_calls` attributes.
        For now `.tool_calls` will be an empty list unless the LLM response
        explicitly contains a JSON description of tool calls (not implemented
        here). This avoids AttributeError in code expecting `invoke`.
        """
        # Accept either raw strings or message objects with `.content`
        parts = []
        for m in messages:
            if isinstance(m, str):
                parts.append(m)
            else:
                # try common attributes
                text = None
                for attr in ("content", "text", "message"):
                    text = getattr(m, attr, None)
                    if text:
                        break
                if text:
                    parts.append(text)
        prompt_text = "\n".join(parts)
        # prefer the configured concise system prompt when invoking
        resp_text = self.prompt(prompt_text, system=self.system_prompt)

        # Clean up unreadable spacing caused by streaming fragments
        # Keep two variants: a human-friendly cleaned view and a compacted
        # normalization used for extraction heuristics (remove spaces around
        # punctuation and collapse repeated whitespace).
        cleaned = re.sub(r"\s+", " ", resp_text).strip()

        def _compact_text(t: str) -> str:
            # Remove backticks and zero-width spaces
            t = t.replace('`', ' ')
            t = t.replace('\u200b', '')
            # remove spaces around slashes, dots and underscores which many
            # tokenized streams introduce ("/ mnt / my" -> "/mnt/my")
            t = re.sub(r"\s*/\s*", "/", t)
            t = re.sub(r"\s*\.\s*", ".", t)
            t = re.sub(r"\s*_\s*", "_", t)
            # collapse long runs of whitespace
            t = re.sub(r"\s+", " ", t)
            return t.strip()

        compact = _compact_text(resp_text)

        # Try to extract a JSON object describing a tool call or action.
        tool_calls: List[Any] = []

        parsed = None
        # 1) Try whole-body JSON
        try:
            parsed = json.loads(resp_text)
        except Exception:
            parsed = None

        # 2) Try to find explicit JSON blob in compacted text. Many servers
        # stream NDJSON or wrap a JSON payload inside another JSON field; try
        # to locate a smaller JSON substring that contains 'tool_calls' and
        # parse that specifically using a simple brace-matching approach.
        if parsed is None:
            try:
                search_target = None
                # prefer the quoted key if present, otherwise the bare name
                if '"tool_calls"' in compact:
                    search_target = '"tool_calls"'
                elif 'tool_calls' in compact:
                    search_target = 'tool_calls'

                if search_target:
                    pos = compact.find(search_target)
                    # find opening brace before the key
                    start = compact.rfind('{', 0, pos)
                    if start != -1:
                        # simple brace matcher to find the matching close
                        depth = 0
                        end = -1
                        for i in range(start, len(compact)):
                            ch = compact[i]
                            if ch == '{':
                                depth += 1
                            elif ch == '}':
                                depth -= 1
                                if depth == 0:
                                    end = i
                                    break
                        if end != -1:
                            candidate = compact[start:end+1]
                            candidate = re.sub(r"\s+", " ", candidate)
                            # Try direct parse, then try unescaping common escapes
                            tried = [candidate]
                            tried.append(candidate.replace('\\"', '"'))
                            try:
                                tried.append(candidate.encode('utf-8').decode('unicode_escape'))
                            except Exception:
                                pass
                            if candidate.startswith('"') and candidate.endswith('"'):
                                tried.append(candidate[1:-1])
                            parsed = None
                            for cand in tried:
                                try:
                                    parsed = json.loads(cand)
                                    break
                                except Exception:
                                    parsed = None
            except Exception:
                parsed = None

    # 3) If parsed JSON found, support common schemas
        if isinstance(parsed, dict):
            if "action" in parsed:
                tool_calls.append({
                    "name": parsed.get("action"),
                    "args": parsed.get("params", {}),
                    "id": str(uuid.uuid4()),
                })
            elif "tool_calls" in parsed and isinstance(parsed["tool_calls"], list):
                for tc in parsed["tool_calls"]:
                    if isinstance(tc, dict) and "name" in tc:
                        tool_calls.append({
                            "name": tc.get("name"),
                            "args": tc.get("args", {}),
                            "id": tc.get("id", str(uuid.uuid4())),
                        })

    # 4) Heuristics: if JSON not present, try to detect a requested action
        # and extract parameters (pdb path, wdir) from the compacted text.
        if not tool_calls:
            # Map a few common action keywords to internal tool names
            action_map = {
                # Preserve explicit tool names when the model uses them.
                    "run_simulation_setup": "run_simulation_setup",
                    # Prefer the clearer internal name 'setup_simulation' so the
                    # planner's intent is obvious to users (avoid 'plan_simulation').
                    "prepare_simulation": "setup_simulation",
                    "prepare a simulation": "setup_simulation",
                    "plan_simulation": "setup_simulation",
                    "simulation_setup": "setup_simulation",
                "submit_job": "submit_job",
                "submit": "submit_job",
                "download_results": "download_results",
                "download": "download_results",
                "analyze_simulation": "analyze_simulation",
                "analyze": "analyze_simulation",
            }

            lower = compact.lower()
            detected = None
            for k in action_map.keys():
                if k in lower:
                    detected = action_map[k]
                    break

            if detected:
                # Extract params: look for a pdb filename and a working dir
                params = {}
                # pdb: look for something that ends with .pdb and starts
                # with a slash (absolute paths). This avoids accidentally
                # capturing fragments like 'for/home/...' when the LLM
                # includes natural language around the path.
                m = re.search(r"(/[\w\-/]+\.pdb)", compact, flags=re.IGNORECASE)
                if m:
                    params["pdb"] = m.group(1)

                # wdir: look for WDIR or wdir= or working directory assignments
                m2 = re.search(r"w\s*dir\s*[:=]\s*\"?([^\"\n]+)\"?", resp_text, flags=re.IGNORECASE)
                if not m2:
                    m2 = re.search(r"wdir\s*[:=]\s*\"?([^\"\n]+)\"?", compact, flags=re.IGNORECASE)
                if m2:
                    params["wdir"] = _compact_text(m2.group(1))
                else:
                    # fallback: try to find the most plausible absolute path in compact text
                    m3 = re.search(r"(/[^\s\n\"']+(/[^\s\n\"']+)*)", compact)
                    if m3:
                        candidate_wdir = m3.group(1)
                        # Strip streaming artifacts like trailing '.Reply' and common punctuation
                        candidate_wdir = re.sub(r"(\.Reply)$", "", candidate_wdir)
                        # Use double-quoted string to avoid unterminated literal issues
                        candidate_wdir = candidate_wdir.rstrip(".,;:\\'\"")
                        # If the candidate is a pdb path, prefer the containing directory
                        if candidate_wdir.lower().endswith('.pdb'):
                            try:
                                import os

                                candidate_wdir = os.path.dirname(candidate_wdir)
                            except Exception:
                                pass
                        params.setdefault("wdir", candidate_wdir)

                # Also try to extract bash-like VAR="..." assignments (e.g. PDB="/path/0.pdb")
                assigns = dict(re.findall(r"([A-Za-z0-9_]+)\s*=\s*\"([^\"]+)\"", compact))
                # normalize common keys
                for kname in ("PDB", "pdb", "P_db"):
                    if kname in assigns and "pdb" not in params:
                        params["pdb"] = assigns[kname]
                for kname in ("WDIR", "W_DIR", "W Dir", "W DIR", "wdir"):
                    if kname in assigns and "wdir" not in params:
                        params["wdir"] = _compact_text(assigns[kname])

                tool_calls.append({
                    "name": detected,
                    "args": params,
                    "id": str(uuid.uuid4()),
                })
        # Validate parsed tool_calls using pydantic schemas when available
        validation_errors = {}
        ToolCallModel = None  # Schemas module no longer exists
        
        validated_calls = []
        if ToolCallModel is not None:
            for tc in tool_calls:
                try:
                    model = ToolCallModel(**tc)
                    err = model.validate_args()
                    if err:
                        validation_errors[tc.get("id") or model.id or tc.get("name")] = str(err)
                    validated_calls.append(model.model_dump())
                except Exception as e:
                    key = tc.get("id") or tc.get("name")
                    validation_errors[key] = str(e)
        else:
            validated_calls = tool_calls

        return LLMClient.InvokeResult(content=cleaned, tool_calls=validated_calls, validation_errors=validation_errors)

    def _http_call(self, prompt: str, system: Optional[str] = None, **kwargs: Any) -> str:
        """Attempt simple HTTP POSTs to a few common endpoints on the base_url.

        This is a best-effort fallback and tries to be tolerant about response
        shapes. It requires `requests` to be installed; otherwise it will raise.
        """
        if requests is None:
            raise RuntimeError("requests package is required for HTTP LLM fallback")

        # Create a session with a small retry policy for transient network blips
        session = requests.Session()
        try:
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry

            retry = Retry(total=3, backoff_factor=0.5, status_forcelist=(500, 502, 503, 504))
            session.mount("http://", HTTPAdapter(max_retries=retry))
            session.mount("https://", HTTPAdapter(max_retries=retry))
        except Exception:
            # if urllib3 Retry isn't available, continue with plain session
            pass

        preferred_endpoints = ["/api/generate", "/generate"]
        endpoints = ["/chat", "/api/chat", "/v1/chat/completions", "/"]
        headers = {"Content-Type": "application/json"}

        def _handle_response(resp):
            # Save raw text where possible for debugging
            try:
                self._last_raw_response = resp.text
            except Exception:
                self._last_raw_response = str(resp)

            # If content-type indicates NDJSON or chunked token stream, parse iter_lines
            ctype = resp.headers.get("Content-Type", "")
            if "ndjson" in ctype or resp.headers.get("Transfer-Encoding", "") == "chunked":
                # stream token fragments
                pieces = []
                thinking = []
                for raw in resp.iter_lines(decode_unicode=True):
                    if not raw:
                        continue
                    line = raw.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        # ignore non-json lines
                        continue
                    # try known shapes
                    if isinstance(obj, dict):
                        # Some servers stream a wrapper object with a 'message'
                        # field whose 'content' contains the assistant tokens
                        # (sometimes split across several events). Prefer
                        # appending that when available so we reconstruct the
                        # original assistant content cleanly.
                        msg = obj.get('message') if isinstance(obj.get('message'), dict) else None
                        if msg and msg.get('content'):
                            pieces.append(msg.get('content'))
                            continue
                        # common top-level response
                        if obj.get("response"):
                            pieces.append(obj.get("response"))
                        if obj.get("thinking"):
                            thinking.append(obj.get("thinking"))
                        # openai/choice style
                        if "choices" in obj and obj["choices"]:
                            ch = obj["choices"][0]
                            if isinstance(ch, dict):
                                if ch.get("text"):
                                    pieces.append(ch.get("text"))
                                elif isinstance(ch.get("delta"), dict) and ch.get("delta").get("content"):
                                    pieces.append(ch.get("delta").get("content"))
                if pieces:
                    return "".join(pieces)
                if thinking:
                    return "".join(thinking)
                return resp.text

            # Not NDJSON; try whole-body JSON
            try:
                data = resp.json()
            except Exception:
                return resp.text

            if isinstance(data, dict):
                for k in ("text", "response", "content", "result"):
                    if k in data and data[k]:
                        return data[k]
                if "choices" in data and data["choices"]:
                    c = data["choices"][0]
                    if isinstance(c, dict):
                        return c.get("text") or c.get("message", {}).get("content", json.dumps(data))
                if "messages" in data and data["messages"]:
                    parts = []
                    for m in data["messages"]:
                        if isinstance(m, dict) and m.get("content"):
                            parts.append(m["content"])
                    if parts:
                        return "\n".join(parts)
            return json.dumps(data)

        # 1) Try preferred non-streaming endpoints with explicit stream:false first
        for ep in preferred_endpoints:
            url = urllib.parse.urljoin(self.base_url.rstrip('/') + '/', ep.lstrip('/'))
            payload = {"model": self.model, "prompt": prompt, "stream": False, "max_tokens": self.config.get("max_tokens", 512)}
            try:
                resp = session.post(url, headers=headers, json=payload, timeout=30)
            except Exception as e:
                logger.debug("preferred endpoint %s failed: %s", url, e)
                continue
            if not resp.ok:
                logger.debug("preferred endpoint %s returned HTTP %s", url, resp.status_code)
                continue
            return _handle_response(resp)

        # 2) Fallback to chat-style endpoints which may stream NDJSON
        for ep in endpoints:
            url = urllib.parse.urljoin(self.base_url.rstrip('/') + '/', ep.lstrip('/'))
            payload = {"model": self.model, "messages": (([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]), "max_tokens": self.config.get("max_tokens", 512)}
            try:
                # allow streaming iter_lines on the response
                resp = session.post(url, headers=headers, data=json.dumps(payload), timeout=30, stream=True)
            except Exception as e:
                logger.debug("chat endpoint %s failed: %s", url, e)
                continue
            if not resp.ok:
                logger.debug("chat endpoint %s returned HTTP %s", url, resp.status_code)
                continue
            return _handle_response(resp)

        raise RuntimeError("No reachable LLM endpoints found at base_url")
