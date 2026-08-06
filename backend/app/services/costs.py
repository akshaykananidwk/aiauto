"""Token and cost estimation for usage analytics.

API providers report exact token usage; for the browser provider we
estimate (~4 characters per token). Prices are approximate USD per
million tokens and exist to give admins relative cost visibility, not
exact billing figures.
"""
from __future__ import annotations

# (input $/1M tokens, output $/1M tokens) by model prefix
PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1": (2.00, 8.00),
    "gpt-5": (1.25, 10.00),
    "o3": (2.00, 8.00),
    "claude-opus": (15.00, 75.00),
    "claude-sonnet": (3.00, 15.00),
    "claude-haiku": (0.80, 4.00),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini": (0.50, 2.00),
    "chatgpt-web": (0.0, 0.0),  # flat-rate subscription — no marginal cost
}

IMAGE_COST_USD = 0.04  # per generated image (approximate)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4) if text else 0


def price_for_model(model: str) -> tuple[float, float]:
    model = (model or "").lower()
    for prefix, price in PRICING.items():
        if model.startswith(prefix):
            return price
    return (0.0, 0.0)


def estimate_cost(model: str, input_tokens: int, output_tokens: int, images: int = 0) -> float:
    inp, out = price_for_model(model)
    cost = (input_tokens * inp + output_tokens * out) / 1_000_000
    cost += images * IMAGE_COST_USD if model and "chatgpt-web" not in model.lower() else 0.0
    return round(cost, 6)
