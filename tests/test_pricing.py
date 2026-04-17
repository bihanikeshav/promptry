"""Tests for promptry.pricing — cache-aware cost math."""

from __future__ import annotations

import pytest

from promptry.pricing import (
    RATES,
    calculate_cost,
    cache_hit_rate,
    cache_savings,
    _lookup_rates,
)


class TestLookupRates:
    def test_exact_match(self):
        assert _lookup_rates("gpt-4o") == RATES["gpt-4o"]

    def test_prefix_match_dated_openai_model(self):
        # "gpt-4o-2024-11-20" should fall back to "gpt-4o"
        assert _lookup_rates("gpt-4o-2024-11-20") == RATES["gpt-4o"]

    def test_prefix_match_prefers_longer_key(self):
        # "gpt-4o-mini-2024-07-18" must match "gpt-4o-mini", not "gpt-4o"
        assert _lookup_rates("gpt-4o-mini-2024-07-18") == RATES["gpt-4o-mini"]

    def test_anthropic_prefix(self):
        assert _lookup_rates("claude-sonnet-4-20250514") == RATES["claude-sonnet-4"]

    def test_unknown_model(self):
        assert _lookup_rates("totally-made-up-model") is None

    def test_empty_model(self):
        assert _lookup_rates("") is None


class TestCalculateCostOpenAI:
    def test_basic_cost_no_cache(self):
        # 1M in, 1M out at gpt-4o rates
        cost = calculate_cost("gpt-4o", tokens_in=1_000_000, tokens_out=1_000_000)
        assert cost == pytest.approx(2.50 + 10.00)

    def test_cached_discount(self):
        # 1000 tokens in, 800 cached
        cost = calculate_cost(
            "gpt-4o", tokens_in=1000, tokens_out=0, cached_tokens=800
        )
        # 200 @ 2.50/M + 800 @ 1.25/M
        expected = (200 / 1_000_000) * 2.50 + (800 / 1_000_000) * 1.25
        assert cost == pytest.approx(round(expected, 6))

    def test_gpt4o_mini_known_rate(self):
        cost = calculate_cost("gpt-4o-mini", tokens_in=1_000_000, tokens_out=1_000_000)
        assert cost == pytest.approx(0.15 + 0.60)


class TestCalculateCostAnthropic:
    def test_anthropic_cache_write(self):
        # Claude Sonnet: 1000 total in = 500 uncached + 500 cache write
        cost = calculate_cost(
            "claude-sonnet-4",
            tokens_in=1000,
            tokens_out=0,
            cache_write_tokens=500,
        )
        # uncached_in = 1000 - 0 - 500 = 500
        # 500 @ 3.00/M + 500 @ 3.75/M
        expected = (500 / 1_000_000) * 3.00 + (500 / 1_000_000) * 3.75
        assert cost == pytest.approx(round(expected, 6))

    def test_anthropic_cache_read_heavy_discount(self):
        # 1000 total in, 900 cache read
        cost = calculate_cost(
            "claude-sonnet-4",
            tokens_in=1000,
            tokens_out=0,
            cached_tokens=900,
        )
        expected = (100 / 1_000_000) * 3.00 + (900 / 1_000_000) * 0.30
        assert cost == pytest.approx(round(expected, 6))


class TestCalculateCostGemini:
    def test_gemini_flash(self):
        cost = calculate_cost(
            "gemini-2.5-flash", tokens_in=1_000_000, tokens_out=1_000_000
        )
        assert cost == pytest.approx(0.30 + 2.50)


class TestCalculateCostGrok:
    def test_grok_2(self):
        cost = calculate_cost("grok-2", tokens_in=1_000_000, tokens_out=0)
        assert cost == pytest.approx(2.00)

    def test_grok_3_with_cache(self):
        cost = calculate_cost(
            "grok-3", tokens_in=1000, tokens_out=0, cached_tokens=500
        )
        expected = (500 / 1_000_000) * 3.00 + (500 / 1_000_000) * 0.75
        assert cost == pytest.approx(round(expected, 6))


class TestCalculateCostEdgeCases:
    def test_unknown_model_returns_none(self):
        assert calculate_cost("bogus-9000", tokens_in=1000, tokens_out=1000) is None

    def test_zero_tokens(self):
        assert calculate_cost("gpt-4o", tokens_in=0, tokens_out=0) == 0.0

    def test_cached_greater_than_total_does_not_go_negative(self):
        # Defensive: if cached_tokens > tokens_in, uncached clamps to 0
        cost = calculate_cost(
            "gpt-4o", tokens_in=100, tokens_out=0, cached_tokens=500
        )
        # uncached clamped to 0, cached fully counted
        expected = (500 / 1_000_000) * 1.25
        assert cost == pytest.approx(round(expected, 6))


class TestCacheHitRate:
    def test_half(self):
        assert cache_hit_rate(500, 1000) == 0.5

    def test_full_hit(self):
        assert cache_hit_rate(1000, 1000) == 1.0

    def test_zero_input(self):
        assert cache_hit_rate(0, 0) == 0.0

    def test_no_hits(self):
        assert cache_hit_rate(0, 1000) == 0.0


class TestCacheSavings:
    def test_openai_savings(self):
        # gpt-4o: uncached 2.50, cached 1.25 -> saves 1.25/M per cached token
        savings = cache_savings("gpt-4o", cached_tokens=1_000_000)
        assert savings == pytest.approx(1.25)

    def test_anthropic_savings(self):
        # claude-sonnet-4: 3.00 - 0.30 = 2.70/M
        savings = cache_savings("claude-sonnet-4", cached_tokens=1_000_000)
        assert savings == pytest.approx(2.70)

    def test_unknown_model_returns_none(self):
        assert cache_savings("bogus", cached_tokens=1000) is None

    def test_zero_cached(self):
        assert cache_savings("gpt-4o", cached_tokens=0) == 0.0
