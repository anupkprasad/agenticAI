"""Simple LLM client wrapper for ChatOllama or similar local LLMs.

This module provides a small, forgiving wrapper around the `ChatOllama`
style client you provided. It falls back to a harmless mock when the
dependency is not available, so the rest of the codebase can remain testable.

Example usage:
    from agentic.llm import LLMClient
    import llm_config
    llm = LLMClient(model=llm_config.DEFAULT_MODEL, base_url=llm_config.LLM_BASE_URL)
    resp = llm.prompt("Summarize the following PDB: ...")
    print(resp)
"""
from __future__ import annotations

from typing import Optional, List, Any, Dict
from dataclasses import dataclass
import re
import uuid
import logging
import json
import urllib.parse
import sys
import os

# Add parent directory to path to import llm_config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import llm_config
except ImportError:
    llm_config = None

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
    def __init__(self, model: str = None, base_url: Optional[str] = None, **kwargs):
        # Use centralized config as defaults if available
        if llm_config:
            self.model = model or llm_config.DEFAULT_MODEL
            self.base_url = base_url or llm_config.LLM_BASE_URL
        else:
            self.model = model or "gpt-oss:20b"
            self.base_url = base_url or "http://127.0.0.1:11434"
            
        self._client = None
        self._is_mock_mode = False  # Track if we're in mock mode
        self._last_raw_response = None
        self._last_thinking = None  # Reasoning tokens from the last call (debug)
        
        logger.info(f"LLMClient initialized: {self.base_url} with model {self.model}")
        
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

    @property
    def available(self) -> bool:
        """Check if LLM client is available and not in mock mode."""
        return not self._is_mock_mode and self._client is not None

    def prompt_raw(self, prompt: str, system: Optional[str] = None, **kwargs) -> str:
        """Send a prompt via /api/generate (no tool-call parsing).
        
        Use this for free-form Q&A where the model output may contain text
        patterns that would be misinterpreted by the chat endpoint's native
        tool-call parser (e.g. 'TOOL: ...' or 'ACTION: ...').
        """
        if not self.base_url:
            return f"MOCK_LLM_RESPONSE: would send: {prompt[:200]}"
        try:
            return self._http_call(prompt, system=system, **kwargs)
        except Exception as e:
            logger.error(f"prompt_raw HTTP call failed: {e}")
            return f"MOCK_LLM_RESPONSE: HTTP_ERROR: {e}"

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
            err_text = str(e)
            if "parsing tool call" in err_text.lower():
                logger.warning(
                    "ollama chat mis-parsed model output as a tool call; "
                    "retrying via /api/generate"
                )
                try:
                    sysp = system if system is not None else self.system_prompt
                    return self.prompt_raw(prompt, system=sysp, **kwargs)
                except Exception as gen_exc:
                    logger.warning("generate retry failed: %s", gen_exc)
            else:
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

    def _ollama_options(self, **kwargs: Any) -> Dict[str, Any]:
        """Build Ollama ``options`` dict honoring per-call and config limits."""
        num_predict = (
            kwargs.get("max_tokens")
            or kwargs.get("num_predict")
            or self.config.get("max_tokens")
            or 4096
        )
        num_predict = int(num_predict)
        # Reasoning models spend a large token budget on hidden reasoning before
        # emitting the answer. Complex JSON plans (many tools + 17+ steps) need
        # a high floor so reasoning finishes AND the full steps array is emitted.
        if self._is_reasoning_model():
            num_predict = max(num_predict, 16384)
        options: Dict[str, Any] = {"num_predict": num_predict}
        num_ctx = kwargs.get("num_ctx") or self.config.get("num_ctx")
        if num_ctx:
            options["num_ctx"] = int(num_ctx)
        elif self._is_reasoning_model():
            # Large planning prompts (~900 lines of tool docs) need a wide context.
            options["num_ctx"] = max(int(self.config.get("num_ctx") or 0), 32768)
        temperature = kwargs.get("temperature")
        if temperature is not None:
            options["temperature"] = float(temperature)
        return options

    def _is_reasoning_model(self) -> bool:
        """Heuristic: does the configured model emit separate reasoning tokens?"""
        name = (self.model or "").lower()
        return any(tag in name for tag in ("gpt-oss", "deepseek-r1", "qwq", "-r1", "reason"))

    def _apply_reasoning_directive(self, system: Optional[str]) -> Optional[str]:
        """Prepend a low-reasoning directive for reasoning models.

        gpt-oss and similar harmony-format models honour a ``Reasoning: low``
        system directive that sharply shortens hidden reasoning. Without it a
        complex prompt can spend the entire token budget on reasoning and emit
        no answer (empty content). Keeps the budget for the actual response.
        """
        if not self._is_reasoning_model():
            return system
        if system and "reasoning:" in system.lower():
            return system
        directive = "Reasoning: low"
        return f"{directive}\n\n{system}" if system else directive

    @staticmethod
    def _resolve_format(**kwargs: Any) -> Optional[str]:
        """Return Ollama ``format`` value ('json') when JSON output is requested."""
        fmt = kwargs.get("format")
        if fmt:
            return fmt
        rf = kwargs.get("response_format")
        if isinstance(rf, dict) and rf.get("type") == "json_object":
            return "json"
        if rf in ("json", "json_object"):
            return "json"
        if kwargs.get("json") is True:
            return "json"
        return None

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
        response_format = self._resolve_format(**kwargs)
        # Reasoning models: cap reasoning so the token budget reaches the answer.
        system = self._apply_reasoning_directive(system)

        # /api/chat + format:"json" is reliable for reasoning models; /api/generate
        # can return empty envelopes. Try chat first when JSON output is required.
        if response_format == "json" and self._is_reasoning_model():
            endpoint_order = endpoints + preferred_endpoints
        else:
            endpoint_order = preferred_endpoints + endpoints

        def _extract_from_obj(obj, pieces, thinking):
            """Pull assistant content + reasoning from one parsed JSON event/object."""
            if not isinstance(obj, dict):
                return
            msg = obj.get("message") if isinstance(obj.get("message"), dict) else None
            if msg:
                if msg.get("content"):
                    pieces.append(msg["content"])
                # Reasoning models (e.g. gpt-oss) stream reasoning separately.
                if msg.get("thinking"):
                    thinking.append(msg["thinking"])
                if msg.get("reasoning"):
                    thinking.append(msg["reasoning"])
            if obj.get("response"):
                pieces.append(obj["response"])
            if obj.get("thinking"):
                thinking.append(obj["thinking"])
            for k in ("text", "content", "result"):
                if not msg and obj.get(k):
                    pieces.append(obj[k])
            if "choices" in obj and obj["choices"]:
                ch = obj["choices"][0]
                if isinstance(ch, dict):
                    if ch.get("text"):
                        pieces.append(ch["text"])
                    elif isinstance(ch.get("delta"), dict) and ch["delta"].get("content"):
                        pieces.append(ch["delta"]["content"])
                    elif isinstance(ch.get("message"), dict) and ch["message"].get("content"):
                        pieces.append(ch["message"]["content"])

        def _finalize(pieces, thinking):
            """Prefer real assistant content; fall back to reasoning only for free-form text."""
            content = "".join(pieces).strip()
            reason = "".join(thinking).strip()
            self._last_thinking = reason
            if content:
                return content
            if reason:
                # Reasoning-only output means the model never emitted an answer
                # (usually token-budget truncation during reasoning).
                if response_format == "json":
                    # Reasoning text would poison JSON parsing — return empty so
                    # the caller retries / falls back to a deterministic plan.
                    logger.warning(
                        "LLM returned reasoning but no content for a JSON request "
                        "(%d reasoning chars); returning empty for caller fallback.",
                        len(reason),
                    )
                    return ""
                # Free-form/natural-language request: reasoning is better than an
                # empty plan, so return it as a last resort.
                logger.warning(
                    "LLM returned reasoning but no content (%d reasoning chars); "
                    "using reasoning text as the free-form answer.",
                    len(reason),
                )
                return reason
            return ""

        def _handle_response(resp):
            # Save raw text where possible for debugging
            try:
                self._last_raw_response = resp.text
            except Exception:
                self._last_raw_response = str(resp)

            pieces: List[str] = []
            thinking: List[str] = []

            # 1) Try whole-body JSON first (stream:false responses).
            try:
                data = resp.json()
            except Exception:
                data = None

            if isinstance(data, dict):
                _extract_from_obj(data, pieces, thinking)
                if pieces or thinking:
                    return _finalize(pieces, thinking)
                # Known non-streaming shapes without message wrapper
                if "messages" in data and data["messages"]:
                    parts = [
                        m["content"] for m in data["messages"]
                        if isinstance(m, dict) and m.get("content")
                    ]
                    if parts:
                        return "\n".join(parts)
                # Recognized generation envelope but empty content (e.g. gpt-oss
                # returns response="" ). Return an empty answer via _finalize so
                # the caller can retry / fall back — never leak the raw envelope.
                envelope_keys = {
                    "response", "message", "done", "done_reason",
                    "choices", "model", "eval_count",
                }
                if envelope_keys & set(data.keys()):
                    return _finalize(pieces, thinking)
                return json.dumps(data)

            # 2) NDJSON / chunked token stream — reassemble line by line
            #    regardless of Content-Type headers (some servers mislabel them).
            raw_text = self._last_raw_response or ""
            parsed_any = False
            for raw in raw_text.splitlines():
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                parsed_any = True
                _extract_from_obj(obj, pieces, thinking)

            if parsed_any:
                return _finalize(pieces, thinking)

            # 3) Not JSON at all — return raw text
            return raw_text

        def _post_and_parse(ep: str, payload: dict, *, timeout: int = 180) -> tuple[str, bool]:
            """Return (content, reachable). reachable=True when HTTP succeeded."""
            url = urllib.parse.urljoin(self.base_url.rstrip('/') + '/', ep.lstrip('/'))
            try:
                resp = session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=timeout,
                )
            except Exception as e:
                logger.debug("endpoint %s failed: %s", url, e)
                return "", False
            if not resp.ok:
                logger.debug("endpoint %s returned HTTP %s", url, resp.status_code)
                return "", False
            return _handle_response(resp), True

        last_empty = ""
        any_reachable = False
        for ep in endpoint_order:
            is_chat = ep in endpoints
            if is_chat:
                payload = {
                    "model": self.model,
                    "messages": (
                        ([{"role": "system", "content": system}] if system else [])
                        + [{"role": "user", "content": prompt}]
                    ),
                    "stream": False,
                    "options": self._ollama_options(**kwargs),
                }
                if response_format:
                    payload["format"] = response_format
            else:
                payload = {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": self._ollama_options(**kwargs),
                }
                # /api/generate + format:"json" returns empty for some reasoning models.
                if response_format and not self._is_reasoning_model():
                    payload["format"] = response_format
                if system:
                    payload["system"] = system

            result, reachable = _post_and_parse(ep, payload)
            if reachable:
                any_reachable = True
            if result:
                return result
            last_empty = ep
            logger.debug(
                "endpoint %s returned empty content%s; trying next endpoint",
                ep,
                " (JSON request)" if response_format == "json" else "",
            )

        if any_reachable:
            logger.warning(
                "All reachable LLM endpoints returned empty content (last tried: %s)",
                last_empty or endpoint_order[-1],
            )
            return ""
        raise RuntimeError("No reachable LLM endpoints found at base_url")
