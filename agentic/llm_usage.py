"""Session-level LLM token accounting and budget enforcement for SimAgent."""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_FILE_LOCK = threading.RLock()


class TokenBudgetExceeded(RuntimeError):
    """Raised when a call would exceed the configured LLM token budget."""

    def __init__(self, used: int, limit: int, pending_estimate: int = 0):
        self.used = used
        self.limit = limit
        self.pending_estimate = pending_estimate
        super().__init__(
            f"LLM token budget exceeded: {used + pending_estimate} tokens "
            f"(used {used}, limit {limit}"
            + (f", pending estimate {pending_estimate}" if pending_estimate else "")
            + ")"
        )


@dataclass
class LLMCallRecord:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    agent: str = ""
    method: str = ""
    estimated: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @classmethod
    def from_counts(
        cls,
        *,
        prompt_tokens: int,
        completion_tokens: int,
        model: str = "",
        agent: str = "",
        method: str = "",
        estimated: bool = False,
    ) -> "LLMCallRecord":
        total = int(prompt_tokens) + int(completion_tokens)
        return cls(
            prompt_tokens=int(prompt_tokens),
            completion_tokens=int(completion_tokens),
            total_tokens=total,
            model=model,
            agent=agent,
            method=method,
            estimated=estimated,
        )


@dataclass
class LLMUsageTotals:
    limit: Optional[int] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0
    estimated_calls: int = 0
    billing_enabled: bool = False
    by_agent: Dict[str, Dict[str, int]] = field(default_factory=dict)
    call_log: List[Dict[str, Any]] = field(default_factory=list)

    def remaining(self) -> Optional[int]:
        if self.limit is None:
            return None
        return max(0, self.limit - self.total_tokens)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "limit": self.limit,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "calls": self.calls,
            "estimated_calls": self.estimated_calls,
            "remaining": self.remaining(),
            "billing_enabled": self.billing_enabled,
            "by_agent": self.by_agent,
            "call_log": self.call_log[-200:],
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }


def estimate_tokens(text: str, *, model: str = "") -> int:
    """Rough pre-call token estimate when provider usage metadata is unavailable."""
    if not text:
        return 0
    try:
        import tiktoken  # optional; OpenAI-compatible counting

        if model:
            try:
                enc = tiktoken.encoding_for_model(model)
            except KeyError:
                enc = tiktoken.get_encoding("cl100k_base")
        else:
            enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)


def parse_usage_from_response(data: Any) -> Tuple[int, int, bool]:
    """Extract (prompt_tokens, completion_tokens, estimated) from provider JSON."""
    if not isinstance(data, dict):
        return 0, 0, True

    usage = data.get("usage")
    if isinstance(usage, dict):
        prompt = int(
            usage.get("prompt_tokens")
            or usage.get("input_tokens")
            or 0
        )
        completion = int(
            usage.get("completion_tokens")
            or usage.get("output_tokens")
            or 0
        )
        if prompt or completion:
            return prompt, completion, False

    prompt = int(data.get("prompt_eval_count") or 0)
    completion = int(data.get("eval_count") or 0)
    if prompt or completion:
        return prompt, completion, False

    return 0, 0, True


def _merge_agent_totals(
    by_agent: Dict[str, Dict[str, int]], agent: str, record: LLMCallRecord
) -> None:
    key = agent or "unknown"
    bucket = by_agent.setdefault(
        key,
        {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0},
    )
    bucket["prompt_tokens"] += record.prompt_tokens
    bucket["completion_tokens"] += record.completion_tokens
    bucket["total_tokens"] += record.total_tokens
    bucket["calls"] += 1


class LLMUsageTracker:
    """In-process tracker with optional on-disk merge for parallel workers.

    Tracking is cheap (counters + occasional JSON write) and is enabled whenever
    a persist path is configured. Budget enforcement only runs when ``limit`` is
    set (typical for paid API runs).
    """

    def __init__(
        self,
        *,
        limit: Optional[int] = None,
        billing_enabled: bool = False,
        persist_path: Optional[str] = None,
        warn_fraction: float = 0.8,
        tracking_enabled: Optional[bool] = None,
    ):
        self.limit = int(limit) if limit is not None and int(limit) > 0 else None
        self.billing_enabled = bool(billing_enabled)
        self.persist_path = Path(persist_path) if persist_path else None
        # Track by default whenever we can persist (local Ollama or paid API).
        if tracking_enabled is None:
            tracking_enabled = bool(self.persist_path) or self.billing_enabled or self.limit is not None
        self.tracking_enabled = bool(tracking_enabled)
        self.warn_fraction = warn_fraction
        self._warned = False
        self.totals = LLMUsageTotals(
            limit=self.limit,
            billing_enabled=self.billing_enabled,
        )
        if self.persist_path and self.persist_path.is_file():
            self._load_from_disk()

    def _load_from_disk(self) -> None:
        if not self.persist_path:
            return
        with _FILE_LOCK:
            try:
                data = json.loads(self.persist_path.read_text(encoding="utf-8"))
            except Exception:
                return
            self.totals.prompt_tokens = int(data.get("prompt_tokens") or 0)
            self.totals.completion_tokens = int(data.get("completion_tokens") or 0)
            self.totals.total_tokens = int(data.get("total_tokens") or 0)
            self.totals.calls = int(data.get("calls") or 0)
            self.totals.estimated_calls = int(data.get("estimated_calls") or 0)
            self.totals.by_agent = dict(data.get("by_agent") or {})
            self.totals.call_log = list(data.get("call_log") or [])[-200:]

    def check_budget(self, pending_estimate: int = 0) -> None:
        if self.limit is None:
            return
        projected = self.totals.total_tokens + max(0, int(pending_estimate))
        if projected > self.limit:
            raise TokenBudgetExceeded(self.totals.total_tokens, self.limit, pending_estimate)
        if (
            not self._warned
            and self.limit
            and projected >= int(self.limit * self.warn_fraction)
        ):
            self._warned = True
            logger.warning(
                "LLM token budget at %.0f%% (%s / %s tokens used)",
                100.0 * projected / self.limit,
                projected,
                self.limit,
            )

    def record(
        self,
        record: LLMCallRecord,
        *,
        prompt_text: str = "",
        completion_text: str = "",
        model: str = "",
    ) -> None:
        if not self.tracking_enabled:
            return
        if record.prompt_tokens == 0 and record.completion_tokens == 0:
            # Prefer cheap char estimate for local tracking; tiktoken only when
            # a paid budget is active (slightly more accurate for enforcement).
            if self.limit is not None or self.billing_enabled:
                est_prompt = estimate_tokens(prompt_text, model=model or record.model)
                est_completion = estimate_tokens(completion_text, model=model or record.model)
            else:
                est_prompt = max(1, len(prompt_text or "") // 4) if prompt_text else 0
                est_completion = (
                    max(1, len(completion_text or "") // 4) if completion_text else 0
                )
            record = LLMCallRecord.from_counts(
                prompt_tokens=est_prompt,
                completion_tokens=est_completion,
                model=model or record.model,
                agent=record.agent,
                method=record.method,
                estimated=True,
            )

        self.totals.prompt_tokens += record.prompt_tokens
        self.totals.completion_tokens += record.completion_tokens
        self.totals.total_tokens += record.total_tokens
        self.totals.calls += 1
        if record.estimated:
            self.totals.estimated_calls += 1
        _merge_agent_totals(self.totals.by_agent, record.agent, record)
        self.totals.call_log.append(asdict(record))
        self.totals.call_log = self.totals.call_log[-200:]
        self._persist()

    def _persist(self) -> None:
        if not self.persist_path:
            return
        path = self.persist_path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = self.totals.to_dict()
        payload["tracking_enabled"] = self.tracking_enabled
        payload["budget_enforced"] = self.limit is not None
        with _FILE_LOCK:
            if path.is_file():
                try:
                    existing = json.loads(path.read_text(encoding="utf-8"))
                    if int(existing.get("total_tokens") or 0) > payload["total_tokens"]:
                        payload["prompt_tokens"] = int(existing.get("prompt_tokens") or 0)
                        payload["completion_tokens"] = int(
                            existing.get("completion_tokens") or 0
                        )
                        payload["total_tokens"] = int(existing.get("total_tokens") or 0)
                        payload["calls"] = int(existing.get("calls") or 0)
                        payload["estimated_calls"] = int(
                            existing.get("estimated_calls") or 0
                        )
                        merged_agents = dict(existing.get("by_agent") or {})
                        for agent, vals in (self.totals.by_agent or {}).items():
                            if agent not in merged_agents:
                                merged_agents[agent] = vals
                        payload["by_agent"] = merged_agents
                        merged_log = list(existing.get("call_log") or [])
                        merged_log.extend(self.totals.call_log)
                        payload["call_log"] = merged_log[-200:]
                except Exception:
                    pass
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp.replace(path)

    def summary_dict(self) -> Dict[str, Any]:
        out = self.totals.to_dict()
        out["tracking_enabled"] = self.tracking_enabled
        out["budget_enforced"] = self.limit is not None
        if self.persist_path:
            out["_path"] = str(self.persist_path)
        return out


def load_usage_summary(working_dir: str) -> Optional[Dict[str, Any]]:
    path = Path(working_dir) / "llm_usage.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def format_usage_terminal(summary: Dict[str, Any]) -> str:
    if not summary:
        return ""
    limit = summary.get("limit")
    total = int(summary.get("total_tokens") or 0)
    prompt = int(summary.get("prompt_tokens") or 0)
    completion = int(summary.get("completion_tokens") or 0)
    calls = int(summary.get("calls") or 0)
    est = int(summary.get("estimated_calls") or 0)
    lines = [
        "",
        "LLM TOKEN USAGE",
        f"  Calls: {calls} ({est} estimated)",
        f"  Prompt tokens:     {prompt:,}",
        f"  Completion tokens: {completion:,}",
        f"  Total tokens:      {total:,}",
    ]
    if limit:
        remaining = summary.get("remaining")
        if remaining is None:
            remaining = max(0, int(limit) - total)
        pct = 100.0 * total / int(limit) if int(limit) else 0.0
        lines.append(f"  Budget: {total:,} / {int(limit):,} ({pct:.1f}%, {remaining:,} remaining)")
    else:
        lines.append("  Budget: (not set — tracking only)")
    by_agent = summary.get("by_agent") or {}
    if by_agent:
        lines.append("  By agent:")
        for agent, vals in sorted(by_agent.items()):
            lines.append(
                f"    - {agent}: {int(vals.get('total_tokens', 0)):,} tokens "
                f"({int(vals.get('calls', 0))} calls)"
            )
    lines.append(f"  Usage file: {Path(summary.get('_path') or 'llm_usage.json')}")
    return "\n".join(lines)


def resolve_llm_budget_from_env() -> Optional[int]:
    raw = os.getenv("LLM_TOKEN_BUDGET") or os.getenv("OPENAI_TOKEN_BUDGET")
    if not raw:
        return None
    try:
        val = int(str(raw).strip())
        return val if val > 0 else None
    except ValueError:
        return None


def resolve_llm_api_key(cli_value: Optional[str] = None) -> Optional[str]:
    key = (cli_value or "").strip()
    if key:
        return key
    for env_name in ("LLM_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        val = (os.getenv(env_name) or "").strip()
        if val:
            return val
    return None
