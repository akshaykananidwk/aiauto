"""Token estimation and cost accounting."""
from app.services.costs import estimate_cost, estimate_tokens, price_for_model


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd" * 100) == 100
    assert estimate_tokens("x") == 1


def test_price_lookup_by_prefix():
    assert price_for_model("gpt-4o-2024-11-20") == price_for_model("gpt-4o")
    assert price_for_model("claude-sonnet-4-5") == (3.00, 15.00)
    assert price_for_model("unknown-model") == (0.0, 0.0)


def test_cost_math():
    # 1M input + 1M output tokens of gpt-4o = $2.50 + $10.00
    assert estimate_cost("gpt-4o", 1_000_000, 1_000_000) == 12.5


def test_browser_provider_has_no_marginal_cost():
    assert estimate_cost("chatgpt-web", 500_000, 500_000, images=3) == 0.0


def test_image_cost_added_for_api_models():
    cost = estimate_cost("gpt-image-1", 0, 0, images=2)
    assert cost == 0.08
