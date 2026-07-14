"""
Per-call cost computation for observability.

Pure logic — no I/O. Produces a 4-line USD breakdown (llm / tts / stt /
telephony) + total for a single call. Rates live in core/config.py so they can
be updated without code changes; pass an explicit ``CostRates`` in tests.

Accuracy notes (documented, not bugs):
  - LLM cost is computed per the ACTIVE model (``model=`` argument). Rate tables
    cover every model selectable in the runtime stack config (core/runtime_config
    ``LLM_MODELS``): ``gpt-4o`` (default), ``gpt-5.4-mini``, ``gpt-4.1``,
    ``gpt-4.1-mini`` (openai) and ``claude-sonnet-4-6``, ``claude-haiku-4-5``
    (anthropic). Unknown models fall back to gpt-4o rates — safer to overcount
    than undercount in monitoring.
  - The AMD classifier, the ambiguous tiebreaker, and the prompt-cache prewarm
    are separate (gpt-4.1-mini) calls NOT in the captured prompt/completion
    accumulators — ~$0.005-$0.01/call, left unmetered for simplicity.
  - Prompt cache: ``cached_prompt_tokens`` is an optional input billed at the
    model's cached-input rate (gpt-4o: 50% of input; gpt-5.4-mini: 10%; gpt-4.1
    family: 25%; Claude: cache-read ~10% of input). If 0 (default), ALL
    prompt_tokens are billed at the uncached rate
    — an UPPER bound on actual cost when caching is active. Capture this from
    OpenAI's ``usage.prompt_tokens_details.cached_tokens`` for full accuracy.
  - TTS is billed per character (Cartesia); we pass total agent-transcript chars.
  - Telephony charges single-leg on total duration; the brief warm-transfer
    two-leg overlap is not separately metered (slight underestimate).
Net: total_usd is accurate to within ~5% for gpt-4o, ~10-20% high for
gpt-5.4-mini when ``cached_prompt_tokens`` is 0 (cache hits not credited).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostRates:
    """USD rates per 1M tokens (LLM) / per unit (others). Defaults mirror
    core/config.py and OpenAI's published pricing (verified Jun 2026)."""
    # --- gpt-4o (current prod default) ---
    gpt4o_in_per_mtok: float = 2.50
    gpt4o_cached_in_per_mtok: float = 1.25
    gpt4o_out_per_mtok: float = 10.00
    # --- gpt-5.4-mini (released 2026-03-17) ---
    gpt5_4_mini_in_per_mtok: float = 0.75
    gpt5_4_mini_cached_in_per_mtok: float = 0.075
    gpt5_4_mini_out_per_mtok: float = 4.50
    # --- gpt-4.1 ---
    gpt4_1_in_per_mtok: float = 2.00
    gpt4_1_cached_in_per_mtok: float = 0.50
    gpt4_1_out_per_mtok: float = 8.00
    # --- gpt-4.1-mini ---
    gpt4_1_mini_in_per_mtok: float = 0.40
    gpt4_1_mini_cached_in_per_mtok: float = 0.10
    gpt4_1_mini_out_per_mtok: float = 1.60
    # --- claude-sonnet-4-6 (Anthropic; cache-read ~10% of input) ---
    claude_sonnet_4_6_in_per_mtok: float = 3.00
    claude_sonnet_4_6_cached_in_per_mtok: float = 0.30
    claude_sonnet_4_6_out_per_mtok: float = 15.00
    # --- claude-haiku-4-5 (Anthropic; cache-read ~10% of input) ---
    claude_haiku_4_5_in_per_mtok: float = 1.00
    claude_haiku_4_5_cached_in_per_mtok: float = 0.10
    claude_haiku_4_5_out_per_mtok: float = 5.00
    # --- non-LLM (model-independent) ---
    cartesia_per_mchar: float = 50.00
    deepgram_stt_per_min: float = 0.0077
    telephony_per_min: float = 0.018


def rates_from_settings() -> CostRates:
    """Build CostRates from the live settings (so ops can tune rates via env/config)."""
    from core.config import settings
    return CostRates(
        gpt4o_in_per_mtok=settings.cost_gpt4o_input_per_mtok,
        gpt4o_cached_in_per_mtok=settings.cost_gpt4o_cached_input_per_mtok,
        gpt4o_out_per_mtok=settings.cost_gpt4o_output_per_mtok,
        gpt5_4_mini_in_per_mtok=settings.cost_gpt5_4_mini_input_per_mtok,
        gpt5_4_mini_cached_in_per_mtok=settings.cost_gpt5_4_mini_cached_input_per_mtok,
        gpt5_4_mini_out_per_mtok=settings.cost_gpt5_4_mini_output_per_mtok,
        gpt4_1_in_per_mtok=settings.cost_gpt4_1_input_per_mtok,
        gpt4_1_cached_in_per_mtok=settings.cost_gpt4_1_cached_input_per_mtok,
        gpt4_1_out_per_mtok=settings.cost_gpt4_1_output_per_mtok,
        gpt4_1_mini_in_per_mtok=settings.cost_gpt4_1_mini_input_per_mtok,
        gpt4_1_mini_cached_in_per_mtok=settings.cost_gpt4_1_mini_cached_input_per_mtok,
        gpt4_1_mini_out_per_mtok=settings.cost_gpt4_1_mini_output_per_mtok,
        claude_sonnet_4_6_in_per_mtok=settings.cost_claude_sonnet_4_6_input_per_mtok,
        claude_sonnet_4_6_cached_in_per_mtok=settings.cost_claude_sonnet_4_6_cached_input_per_mtok,
        claude_sonnet_4_6_out_per_mtok=settings.cost_claude_sonnet_4_6_output_per_mtok,
        claude_haiku_4_5_in_per_mtok=settings.cost_claude_haiku_4_5_input_per_mtok,
        claude_haiku_4_5_cached_in_per_mtok=settings.cost_claude_haiku_4_5_cached_input_per_mtok,
        claude_haiku_4_5_out_per_mtok=settings.cost_claude_haiku_4_5_output_per_mtok,
        cartesia_per_mchar=settings.cost_cartesia_per_mchar,
        deepgram_stt_per_min=settings.cost_deepgram_stt_per_min,
        telephony_per_min=settings.cost_telephony_per_min,
    )


def _llm_rates_for_model(model: str, rates: CostRates) -> tuple[float, float, float]:
    """Pick (input, cached_input, output) rates for the active model.

    Match by prefix after stripping any ``provider/`` qualifier (LiveKit logs
    models as ``openai/gpt-4o`` / ``anthropic/claude-haiku-4-5``) so snapshot
    strings like ``gpt-5.4-mini-2026-03-17`` resolve correctly. Order matters:
    more specific prefixes (``gpt-4.1-mini``) are checked before their parents
    (``gpt-4.1``). Unknown models default to gpt-4o rates — overcount, don't
    undercount.
    """
    m = model.lower()
    if "/" in m:                       # drop "openai/" / "anthropic/" qualifier
        m = m.split("/", 1)[1]

    if m.startswith("gpt-5.4-mini"):
        return (rates.gpt5_4_mini_in_per_mtok,
                rates.gpt5_4_mini_cached_in_per_mtok,
                rates.gpt5_4_mini_out_per_mtok)
    if m.startswith("gpt-4.1-mini"):
        return (rates.gpt4_1_mini_in_per_mtok,
                rates.gpt4_1_mini_cached_in_per_mtok,
                rates.gpt4_1_mini_out_per_mtok)
    if m.startswith("gpt-4.1"):
        return (rates.gpt4_1_in_per_mtok,
                rates.gpt4_1_cached_in_per_mtok,
                rates.gpt4_1_out_per_mtok)
    if m.startswith("claude-sonnet-4-6"):
        return (rates.claude_sonnet_4_6_in_per_mtok,
                rates.claude_sonnet_4_6_cached_in_per_mtok,
                rates.claude_sonnet_4_6_out_per_mtok)
    if m.startswith("claude-haiku-4-5"):
        return (rates.claude_haiku_4_5_in_per_mtok,
                rates.claude_haiku_4_5_cached_in_per_mtok,
                rates.claude_haiku_4_5_out_per_mtok)
    return (rates.gpt4o_in_per_mtok,
            rates.gpt4o_cached_in_per_mtok,
            rates.gpt4o_out_per_mtok)


def compute_call_cost(
    *,
    llm_prompt_tokens: int,
    llm_completion_tokens: int,
    tts_chars: int,
    stt_audio_s: float,
    duration_s: float,
    model: str = "gpt-4o",
    cached_prompt_tokens: int = 0,
    rates: CostRates | None = None,
    platform_fee_pct: float = 0,
) -> dict:
    """Return {llm_usd, tts_usd, stt_usd, telephony_usd, platform_fee_usd, total_usd} for one call.

    ``model`` selects LLM rate table; defaults to ``gpt-4o`` for backward
    compat. ``cached_prompt_tokens`` is billed at the model's cached-input
    rate; the remainder is billed at the uncached rate. ``platform_fee_pct``
    adds a platform fee as a percentage of the subtotal (default 0).
    """
    r = rates or CostRates()
    in_rate, cached_rate, out_rate = _llm_rates_for_model(model, r)

    cached = max(0, min(cached_prompt_tokens, llm_prompt_tokens))
    uncached = llm_prompt_tokens - cached

    llm = (
        (uncached / 1_000_000) * in_rate
        + (cached / 1_000_000) * cached_rate
        + (llm_completion_tokens / 1_000_000) * out_rate
    )
    tts = (tts_chars / 1_000_000) * r.cartesia_per_mchar
    stt = (stt_audio_s / 60.0) * r.deepgram_stt_per_min
    telephony = (duration_s / 60.0) * r.telephony_per_min
    subtotal = llm + tts + stt + telephony
    platform_fee = (subtotal * platform_fee_pct) / 100.0
    total = subtotal + platform_fee
    return {
        "llm_usd": round(llm, 4),
        "tts_usd": round(tts, 4),
        "stt_usd": round(stt, 4),
        "telephony_usd": round(telephony, 4),
        "platform_fee_usd": round(platform_fee, 4),
        "total_usd": round(total, 4),
    }
