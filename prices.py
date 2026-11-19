"""Price table and the one function that turns token counts into dollars.

Source: https://platform.claude.com/docs/en/about-claude/pricing (read 2026-11-19).
Dollar figures made with this file are COMPUTED "API-equivalent cost": measured token
counts times list prices. On a subscription plan this is not what you were billed.
"""

# US$ per million tokens: (input, 5-min cache write, 1-h cache write, cache read, output)
PRICES = {
    "claude-fable-5-2":  (8.00, 10.00, 16.00, 0.20, 40.00),
    "claude-fable-5-1":  (10.00, 12.50, 20.00, 0.25, 50.00),
    "claude-opus-5-5":   (4.00, 5.00, 8.00, 0.20, 20.00),
    "claude-opus-5":     (5.00, 6.25, 10.00, 0.50, 25.00),
    "claude-sonnet-5-5": (2.00, 2.50, 4.00, 0.10, 10.00),
    "claude-haiku-5-5":  (0.10, 0.125, 0.20, 0.01, 0.50),
}
FAST_MODE_MULT = 2            # fast mode doubles every price (Fable 5.2, Opus 5.5, Opus 5)
HAIKU_LONG_PROMPT_TOKENS = 100_000  # Haiku 5.5 prompts above this size...
HAIKU_LONG_PROMPT_MULT = 5          # ...pay 5x on every token of that call


def cost_parts(model, n_in, n_write_5m, n_write_1h, n_read, n_out, fast=0):
    """US$ for one API call, split as (input, output, cache write, cache read)."""
    p_in, p_w5m, p_w1h, p_read, p_out = PRICES[model]  # unknown model -> KeyError, on purpose
    k = (FAST_MODE_MULT if fast else 1) / 1e6
    if model == "claude-haiku-5-5" and n_in + n_write_5m + n_write_1h + n_read > HAIKU_LONG_PROMPT_TOKENS:
        k *= HAIKU_LONG_PROMPT_MULT
    return n_in * p_in * k, n_out * p_out * k, (n_write_5m * p_w5m + n_write_1h * p_w1h) * k, n_read * p_read * k
