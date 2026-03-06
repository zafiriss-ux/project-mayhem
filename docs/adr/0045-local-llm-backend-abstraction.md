# ADR-0045 — Local LLM Backend Abstraction: Ollama and On-Device Model Support

**Date:** 2026-03-06
**Status:** Accepted
**Deciders:** Architect
**Source:** Strategic review session 2026-03-06 — future-proofing for local LLM commoditization
**Phase:** Phase 10 design constraint — effective from Phase 10 implementation start
**Supplements:** ADR-0043 (product direction + LLM seams — this ADR refines Seam 3),
ADR-0014 (ML kill-switch pattern — same pattern applied here), ADR-0042 (human override invariant)

---

## Context

ADR-0043 Decision 3 established that Phase 10 introduces an LLM coach query layer,
initially targeting the Claude API (Anthropic). ADR-0043 Seam 3 specified an env-gated
kill-switch (`TITAN_LLM_COACH`) with a deterministic fallback.

However, ADR-0043 did not address a structural shift that is already underway and will
be near-complete by the time Phase 10 arrives (~2029):

**The commoditization of local LLMs.**

### The local LLM landscape (2026 baseline, trajectory toward Phase 10)

As of early 2026:
- Ollama (v0.3+) runs 7B–70B parameter instruction-tuned models on a laptop with Apple
  Silicon or a mid-range NVIDIA GPU. No internet connection required.
- `llama.cpp` provides quantized inference (Q4_K_M, Q5_K_M) that fits Llama-3-70B into
  ~40GB VRAM — achievable on a single A100 or 2× consumer 3090s.
- Models like Qwen2.5-72B-Instruct, Mistral-Large-Instruct, and Llama-4 (projected 2026)
  already match GPT-4-class performance on structured reasoning tasks.
- Apple MLX enables M-series Macs to run 70B models at 15–30 tokens/second — sufficient
  for coaching query latency (non-real-time use case).

By Phase 10 (~2029), it is reasonable to expect:
- 100B+ parameter models running on consumer hardware.
- Coaching context windows of 50K–200K tokens — sufficient to include a full 90-day
  training log and governance decision history for all athletes.
- No meaningful quality gap between local inference and cloud API for structured
  coaching query tasks.

### Why this matters architecturally for TITAN OS

TITAN OS handles health data: HRV, RHR, sleep scores, subjective fatigue ratings,
training load history. Sending this data to an external API creates:

1. **GDPR data transfer obligations** — health data is "special category data" under
   GDPR Article 9. Sending it to a US-based cloud API requires a data processing
   agreement (DPA) and potentially a SCCs (Standard Contractual Clauses) filing.
   This is manageable but adds compliance overhead.

2. **API cost at scale** — 50 athletes × 1 daily coach query × 8K input tokens =
   ~400K tokens/day. At $3/MTok (Claude pricing, 2026), this is ~$1.20/day or ~$438/year.
   Not prohibitive, but a perpetual recurring cost that a local model eliminates entirely.

3. **Data sovereignty preference** — some coach contexts (national federations, medical
   coaches working with patient data) may have contractual or regulatory requirements
   that prohibit health data leaving a specific jurisdiction or infrastructure boundary.

4. **API availability dependency** — an external API outage does not prevent TITAN OS
   from making governance decisions (the LLM is advisory-only), but it silences the
   Phase 10 coaching narrative layer. A local model is always available.

If the Phase 10 `llm_coach.py` module is hardcoded to the Claude API, migrating to a
local model later requires rewriting the integration. The cost of building the abstraction
correctly now (when Phase 10 is being designed) is ~1 day. The cost of retrofitting it
later is 2–3 weeks.

---

## Decision

**The `llm_coach.py` module (Phase 10) must use a backend-abstracted interface from day
one. The architecture supports three backends, selected via environment variable:**

```
TITAN_LLM_BACKEND=none      # Default — deterministic fallback only (kill-switch)
TITAN_LLM_BACKEND=claude    # Anthropic Claude API (external)
TITAN_LLM_BACKEND=ollama    # Ollama local inference (self-hosted)
```

### Backend Interface Contract

All backends implement the same interface:

```python
# titan/integrations/llm_backends/base.py
from abc import ABC, abstractmethod

class LLMBackend(ABC):
    """
    ADR-0045: Backend-agnostic LLM interface for TITAN coach query layer.
    All backends must be stateless and deterministic for the same input + model version.
    """

    @abstractmethod
    def generate(self, prompt: str, context: dict, max_tokens: int = 1024) -> str:
        """
        Generate a coaching narrative from structured athlete context.
        Must return a non-empty string. Must raise LLMBackendError on failure
        (never return an empty string or None — callers rely on this invariant).
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Health check. Returns True only if backend can accept a request right now."""

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Human-readable name for structured log events."""
```

### Claude API Backend

```python
# titan/integrations/llm_backends/claude_backend.py
import anthropic

class ClaudeBackend(LLMBackend):
    MODEL = "claude-opus-4-6"  # Update to latest capable model at Phase 10 impl time

    def generate(self, prompt: str, context: dict, max_tokens: int = 1024) -> str:
        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
        message = client.messages.create(
            model=self.MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": _format_prompt(prompt, context)}],
        )
        return message.content[0].text

    def is_available(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
```

### Ollama Backend

```python
# titan/integrations/llm_backends/ollama_backend.py
import httpx

OLLAMA_BASE_URL = os.environ.get("TITAN_OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.environ.get("TITAN_OLLAMA_MODEL", "qwen2.5:72b-instruct-q4_K_M")

class OllamaBackend(LLMBackend):
    def generate(self, prompt: str, context: dict, max_tokens: int = 1024) -> str:
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": _format_prompt(prompt, context),
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        response = httpx.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload, timeout=60.0)
        response.raise_for_status()
        return response.json()["response"]

    def is_available(self) -> bool:
        try:
            r = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2.0)
            return r.status_code == 200
        except Exception:
            return False
```

### Deterministic Fallback (kill-switch default)

When `TITAN_LLM_BACKEND=none` OR when the active backend's `is_available()` returns
False, `llm_coach.py` falls back to template-based summaries (ADR-0043 Seam 3). This
fallback must produce the same output shape as the LLM paths — callers cannot
distinguish template from LLM output by type.

### Backend Resolution Logic

```python
# titan/integrations/llm_coach.py
def _get_backend() -> LLMBackend | None:
    backend_name = os.environ.get("TITAN_LLM_BACKEND", "none")
    if backend_name == "claude":
        return ClaudeBackend()
    if backend_name == "ollama":
        return OllamaBackend()
    return None  # none — use deterministic fallback

def coach_query(prompt: str, athlete_context: dict) -> str:
    backend = _get_backend()
    if backend is None or not backend.is_available():
        _emit_event("llm_backend_unavailable", backend=backend, severity="INFO")
        return _deterministic_fallback_summary(athlete_context)
    try:
        result = backend.generate(prompt, athlete_context)
        _emit_event("llm_query_completed", backend=backend.backend_name, severity="INFO")
        return result
    except LLMBackendError as exc:
        _emit_event("llm_query_failed", error=str(exc), severity="WARNING")
        return _deterministic_fallback_summary(athlete_context)
```

### Recommended model for Ollama (Phase 10 baseline)

At Phase 10 implementation time, evaluate the current best available model for the task.
The baseline recommendation (2026 knowledge cutoff) is:

| Hardware | Recommended model | Rationale |
|---|---|---|
| Apple M3 Max / M4 Pro (64GB) | `qwen2.5:72b-instruct-q4_K_M` | 15–25 tok/s; fits in 42GB |
| NVIDIA RTX 4090 (24GB) | `qwen2.5:32b-instruct-q5_K_M` | Fits in 22GB; strong instruction following |
| CPU-only (RAM ≥ 64GB) | `qwen2.5:14b-instruct-q5_K_M` | Acceptable latency (~3–5 tok/s) |
| Self-hosted server (A100 80GB) | `llama-4-scout:109b-instruct-q4_K_M` | Best quality at Phase 10 |

Model selection must be re-evaluated at Phase 10 implementation time. Do not hardcode
a model at ADR authoring time — `TITAN_OLLAMA_MODEL` is an env variable for this reason.

### Data Privacy Classification

| Backend | Data leaves device | GDPR DPA required | Cost |
|---|---|---|---|
| `none` | No | No | $0 |
| `ollama` | No | No | $0 (hardware only) |
| `claude` | Yes (Anthropic servers) | Yes (sign Anthropic DPA) | ~$438/year at 50 athletes |

**Default is `none`.** Coaches who activate `claude` or `ollama` must acknowledge the
data handling implications. This acknowledgement must be recorded in the `consent_log`
table (ADR-0044) with `consent_type = 'llm_data_processing'`.

### What This Does NOT Change

- ADR-0043 Decision 4 (LLM out of scope for Phases 8 and 9) is unchanged.
- The governance gate pipeline has no dependency on any LLM backend.
- ADR-0042 (human override invariant) applies to all LLM outputs regardless of backend.
- Tests must not make live API calls. Both Claude and Ollama backends must have injectable
  mock interfaces for CI testing.

---

## Debt Items Created

No new debt items. T5-10 (Phase 10 LLM layer) is updated to reference ADR-0045 as the
implementation contract for the backend abstraction.

---

## Alternatives Considered

**Alternative A — Hardcode Claude API only**
Rejected. See context above — data sovereignty, cost, and offline availability are
material concerns for a health data platform. Retrofitting an abstraction later costs
more than building it correctly now.

**Alternative B — Use LangChain or LlamaIndex as abstraction layer**
Rejected. LangChain and LlamaIndex are large, fast-moving dependencies with breaking
changes in every minor version. The interface required by TITAN OS is minimal — one
`generate()` method. Introducing a 50k+ line framework dependency for one method is
out of scope (ADR-0028 complexity budget principle). The custom `LLMBackend` ABC above
is 30 lines and has zero external dependencies.

**Alternative C — Support OpenAI API format only (compatible with both Ollama and many
cloud models)**
Partially adopted. Ollama's `/api/generate` endpoint is not OpenAI-compatible by default,
but Ollama also exposes an OpenAI-compatible `/v1/chat/completions` endpoint. This
alternative is noted for Phase 10 implementors: if the Ollama backend is simplified by
using the OpenAI-compatible endpoint, that is acceptable — the interface contract above
does not constrain the internal implementation.

**Alternative D — Use Apple MLX directly (for M-series Macs)**
Not recommended as primary path. MLX is Apple-only and would require a third backend
implementation with no cross-platform compatibility. Ollama already supports MLX
acceleration on M-series Macs transparently — the Ollama backend works on Apple Silicon
without any changes.

---

## Consequences

- Positive: Phase 10 can be deployed with zero external API dependencies for coaches
  who have a capable local machine or server. This is particularly valuable in
  environments with data sovereignty requirements.
- Positive: The abstraction cost is minimal (one ABC + two concrete implementations +
  env-based resolution). This is a one-time 1-day investment.
- Positive: `TITAN_LLM_BACKEND=none` (the default) means Phase 10 code ships with
  the LLM layer fully disabled by default — consistent with the ML kill-switch pattern.
  No coach accidentally activates LLM data processing without setting the env variable.
- Positive: Backend switching in production requires only an env variable change and
  a restart — no code change. Coaches can move from `claude` to `ollama` as local
  hardware improves without touching application code.
- Negative (acceptable): Two backend implementations to maintain instead of one.
  Maintenance cost is low: the interface is stable, and each backend is ~30 lines.
- Constraint: Phase 10 implementation must include a mock backend for CI
  (`MockLLMBackend` that returns a fixed fixture string). No live API calls in CI.
