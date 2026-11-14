"""Tests for betting analysis calculations."""

from sports_skills.betting._calcs import (
    convert_odds,
    devig,
    evaluate_bet,
    find_arbitrage,
    find_edge,
    kelly_criterion,
    line_movement,
    parlay_analysis,
)

# ============================================================
# Convert Odds
# ============================================================


class TestConvertOdds:
    def test_american_negative(self):
        # -150 → prob = 150/250 = 0.6
        result = convert_odds({"params": {"odds": -150, "from_format": "american"}})
        assert result["status"] is True
        assert abs(result["data"]["implied_probability"] - 0.6) < 0.001

    def test_american_positive(self):
        # +130 → prob = 100/230 ≈ 0.4348
        result = convert_odds({"params": {"odds": 130, "from_format": "american"}})
        assert result["status"] is True
        assert abs(result["data"]["implied_probability"] - 0.4348) < 0.001

    def test_american_even(self):
        # +100 → prob = 100/200 = 0.5
        result = convert_odds({"params": {"odds": 100, "from_format": "american"}})
        assert result["status"] is True
        assert abs(result["data"]["implied_probability"] - 0.5) < 0.001

    def test_american_heavy_favorite(self):
        # -500 → prob = 500/600 ≈ 0.8333
        result = convert_odds({"params": {"odds": -500, "from_format": "american"}})
        assert result["status"] is True
        assert abs(result["data"]["implied_probability"] - 0.8333) < 0.001

    def test_decimal(self):
        # 2.50 → prob = 1/2.5 = 0.4
        result = convert_odds({"params": {"odds": 2.50, "from_format": "decimal"}})
        assert result["status"] is True
        assert abs(result["data"]["implied_probability"] - 0.4) < 0.001

    def test_decimal_invalid(self):
        result = convert_odds({"params": {"odds": 0.5, "from_format": "decimal"}})
        assert result["status"] is False

    def test_probability(self):
        # 0.6 → american = -150, decimal = 1.6667
        result = convert_odds({"params": {"odds": 0.6, "from_format": "probability"}})
        assert result["status"] is True
        assert abs(result["data"]["american"] - (-150.0)) < 0.1
        assert abs(result["data"]["decimal"] - 1.6667) < 0.001

    def test_probability_invalid(self):
        result = convert_odds({"params": {"odds": 1.5, "from_format": "probability"}})
        assert result["status"] is False

    def test_unknown_format(self):
        result = convert_odds({"params": {"odds": 100, "from_format": "fractional"}})
        assert result["status"] is False

    def test_roundtrip_american(self):
        # Convert american → prob → american should be consistent
        r1 = convert_odds({"params": {"odds": -200, "from_format": "american"}})
        prob = r1["data"]["implied_probability"]
        r2 = convert_odds({"params": {"odds": prob, "from_format": "probability"}})
        assert abs(r2["data"]["american"] - (-200.0)) < 0.5


# ============================================================
# De-vig
# ============================================================


class TestDevig:
    def test_standard_spread(self):
        # -110/-110 → each side ~52.38% → fair 50%/50%
        result = devig({"params": {"odds": "-110,-110", "format": "american"}})
        assert result["status"] is True
        outcomes = result["data"]["outcomes"]
        assert len(outcomes) == 2
        assert abs(outcomes[0]["fair_prob"] - 0.5) < 0.001
        assert abs(outcomes[1]["fair_prob"] - 0.5) < 0.001
        assert result["data"]["vig_pct"] > 0

    def test_two_way_market(self):
        # -150/+130 → probs sum > 1, de-vig removes overround
        result = devig({"params": {"odds": "-150,+130", "format": "american"}})
        assert result["status"] is True
        outcomes = result["data"]["outcomes"]
        total_fair = sum(o["fair_prob"] for o in outcomes)
        assert abs(total_fair - 1.0) < 0.001

    def test_three_way_soccer(self):
        # Soccer 3-way moneyline
        result = devig({"params": {"odds": "-120,+250,+350", "format": "american"}})
        assert result["status"] is True
        outcomes = result["data"]["outcomes"]
        assert len(outcomes) == 3
        total_fair = sum(o["fair_prob"] for o in outcomes)
        assert abs(total_fair - 1.0) < 0.001

    def test_decimal_format(self):
        result = devig({"params": {"odds": "1.91,1.91", "format": "decimal"}})
        assert result["status"] is True
        outcomes = result["data"]["outcomes"]
        assert abs(outcomes[0]["fair_prob"] - 0.5) < 0.01

    def test_probability_format(self):
        result = devig({"params": {"odds": "0.55,0.50", "format": "probability"}})
        assert result["status"] is True
        total_fair = sum(o["fair_prob"] for o in result["data"]["outcomes"])
        assert abs(total_fair - 1.0) < 0.001

    def test_list_input(self):
        result = devig({"params": {"odds": [-150, 130], "format": "american"}})
        assert result["status"] is True

    def test_single_outcome_error(self):
        result = devig({"params": {"odds": "-150", "format": "american"}})
        assert result["status"] is False

    def test_missing_odds(self):
        result = devig({"params": {}})
        assert result["status"] is False

    def test_overround_positive(self):
        # Any real book odds should have positive vig
        result = devig({"params": {"odds": "-110,-110", "format": "american"}})
        assert result["data"]["overround"] > 1.0
        assert result["data"]["vig_pct"] > 0


# ============================================================
# Find Edge
# ============================================================


class TestFindEdge:
    def test_positive_edge(self):
        result = find_edge({"params": {"fair_prob": 0.60, "market_prob": 0.50}})
        assert result["status"] is True
        assert result["data"]["edge"] > 0
        assert result["data"]["ev_per_dollar"] > 0
        assert result["data"]["recommendation"] == "bet"

    def test_negative_edge(self):
        result = find_edge({"params": {"fair_prob": 0.40, "market_prob": 0.50}})
        assert result["status"] is True
        assert result["data"]["edge"] < 0
        assert result["data"]["ev_per_dollar"] < 0
        assert result["data"]["recommendation"] == "no bet"

    def test_zero_edge(self):
        result = find_edge({"params": {"fair_prob": 0.50, "market_prob": 0.50}})
        assert result["status"] is True
        assert result["data"]["edge"] == 0
        assert result["data"]["recommendation"] == "no bet"

    def test_known_values(self):
        # fair=0.60, market=0.50 → edge=0.10, EV=0.20, Kelly=0.20
        result = find_edge({"params": {"fair_prob": 0.60, "market_prob": 0.50}})
        assert abs(result["data"]["edge"] - 0.10) < 0.001
        assert abs(result["data"]["ev_per_dollar"] - 0.20) < 0.001
        assert abs(result["data"]["kelly_fraction"] - 0.20) < 0.001

    def test_invalid_fair_prob(self):
        result = find_edge({"params": {"fair_prob": 1.5, "market_prob": 0.50}})
        assert result["status"] is False

    def test_invalid_market_prob(self):
        result = find_edge({"params": {"fair_prob": 0.50, "market_prob": 0}})
        assert result["status"] is False


# ============================================================
# Kelly Criterion
# ============================================================


class TestKellyCriterion:
    def test_positive_edge(self):
        result = kelly_criterion({"params": {"fair_prob": 0.60, "market_prob": 0.50}})
        assert result["status"] is True
        assert result["data"]["kelly_fraction"] > 0
        assert result["data"]["recommendation"] == "bet"

    def test_negative_edge(self):
        result = kelly_criterion({"params": {"fair_prob": 0.40, "market_prob": 0.50}})
        assert result["status"] is True
        assert result["data"]["kelly_fraction"] < 0
        assert result["data"]["recommendation"] == "no bet"

    def test_known_kelly(self):
        # fair=0.60, market=0.50 → f* = (0.60-0.50)/(1-0.50) = 0.20
        result = kelly_criterion({"params": {"fair_prob": 0.60, "market_prob": 0.50}})
        assert abs(result["data"]["kelly_fraction"] - 0.20) < 0.001

    def test_small_edge(self):
        # fair=0.52, market=0.50 → f* = 0.02/0.50 = 0.04
        result = kelly_criterion({"params": {"fair_prob": 0.52, "market_prob": 0.50}})
        assert abs(result["data"]["kelly_fraction"] - 0.04) < 0.001

    def test_net_odds_computed(self):
        # market=0.40 → b = 1/0.40 - 1 = 1.5
        result = kelly_criterion({"params": {"fair_prob": 0.60, "market_prob": 0.40}})
        assert abs(result["data"]["net_odds"] - 1.5) < 0.001

    def test_invalid_fair_prob(self):
        result = kelly_criterion({"params": {"fair_prob": 0, "market_prob": 0.50}})
        assert result["status"] is False

    def test_invalid_market_prob(self):
        result = kelly_criterion({"params": {"fair_prob": 0.50, "market_prob": 1.0}})
        assert result["status"] is False


# ============================================================
# Evaluate Bet (all-in-one)
# ============================================================


class TestEvaluateBet:
    def test_basic_evaluation(self):
        result = evaluate_bet({
            "params": {
                "book_odds": "-150,+130",
                "market_prob": 0.52,
            }
        })
        assert result["status"] is True
        assert "devig" in result["data"]
        assert "edge" in result["data"]
        assert "recommendation" in result["data"]
        assert "summary" in result["data"]

    def test_no_edge_no_bet(self):
        # If market prob matches fair prob, should be no bet
        # -110/-110 → fair 50%/50%, market at 0.50 → no edge
        result = evaluate_bet({
            "params": {
                "book_odds": "-110,-110",
                "market_prob": 0.50,
            }
        })
        assert result["status"] is True
        assert abs(result["data"]["edge"]["edge"]) < 0.01

    def test_decimal_format(self):
        result = evaluate_bet({
            "params": {
                "book_odds": "1.67,2.30",
                "book_format": "decimal",
                "market_prob": 0.52,
            }
        })
        assert result["status"] is True

    def test_second_outcome(self):
        # Evaluate the second outcome (away team / underdog)
        result = evaluate_bet({
            "params": {
                "book_odds": "-150,+130",
                "market_prob": 0.52,
                "outcome": 1,
            }
        })
        assert result["status"] is True
        # The away side fair prob should be ~42%
        fair_prob = result["data"]["devig"]["outcomes"][1]["fair_prob"]
        assert 0.35 < fair_prob < 0.50

    def test_missing_book_odds(self):
        result = evaluate_bet({"params": {"market_prob": 0.50}})
        assert result["status"] is False

    def test_invalid_market_prob(self):
        result = evaluate_bet({
            "params": {"book_odds": "-150,+130", "market_prob": 1.5}
        })
        assert result["status"] is False

    def test_outcome_out_of_range(self):
        result = evaluate_bet({
            "params": {
                "book_odds": "-150,+130",
                "market_prob": 0.50,
                "outcome": 5,
            }
        })
        assert result["status"] is False


# ============================================================
# Find Arbitrage
# ============================================================


class TestFindArbitrage:
    def test_arbitrage_exists(self):
        # Sum = 0.97 < 1.0 → arbitrage
        result = find_arbitrage({"params": {"market_probs": "0.48,0.49"}})
        assert result["status"] is True
        assert result["data"]["arbitrage_found"] is True
        assert result["data"]["arbitrage_pct"] > 0
        assert result["data"]["total_implied"] < 1.0

    def test_no_arbitrage(self):
        # Sum = 1.05 > 1.0 → no arbitrage
        result = find_arbitrage({"params": {"market_probs": "0.55,0.50"}})
        assert result["status"] is True
        assert result["data"]["arbitrage_found"] is False
        assert result["data"]["overround_pct"] > 0

    def test_three_way(self):
        # 3-way soccer market with arb
        result = find_arbitrage({"params": {"market_probs": "0.35,0.25,0.30"}})
        assert result["status"] is True
        assert result["data"]["arbitrage_found"] is True
        assert len(result["data"]["allocations"]) == 3

    def test_labels(self):
        result = find_arbitrage({
            "params": {"market_probs": "0.48,0.49", "labels": "home,away"}
        })
        assert result["data"]["allocations"][0]["label"] == "home"
        assert result["data"]["allocations"][1]["label"] == "away"

    def test_labels_mismatch(self):
        result = find_arbitrage({
            "params": {"market_probs": "0.48,0.49", "labels": "home,draw,away"}
        })
        assert result["status"] is False

    def test_single_outcome_error(self):
        result = find_arbitrage({"params": {"market_probs": "0.50"}})
        assert result["status"] is False

    def test_prob_out_of_range(self):
        result = find_arbitrage({"params": {"market_probs": "0.50,1.5"}})
        assert result["status"] is False

    def test_missing_probs(self):
        result = find_arbitrage({"params": {}})
        assert result["status"] is False

    def test_allocations_sum_to_100(self):
        result = find_arbitrage({"params": {"market_probs": "0.48,0.49"}})
        total_alloc = sum(a["allocation_pct"] for a in result["data"]["allocations"])
        assert abs(total_alloc - 100.0) < 0.1

    def test_list_input(self):
        result = find_arbitrage({"params": {"market_probs": [0.48, 0.49]}})
        assert result["status"] is True


# ============================================================
# Parlay Analysis
# ============================================================


class TestParlayAnalysis:
    def test_plus_ev_parlay(self):
        # 3 legs with good odds offered
        result = parlay_analysis({
            "params": {"legs": "0.58,0.62,0.55", "parlay_odds": 600}
        })
        assert result["status"] is True
        assert result["data"]["is_plus_ev"] is True
        assert result["data"]["edge"] > 0
        assert result["data"]["num_legs"] == 3

    def test_minus_ev_parlay(self):
        # Low payout relative to fair odds
        result = parlay_analysis({
            "params": {"legs": "0.58,0.62,0.55", "parlay_odds": 200}
        })
        assert result["status"] is True
        assert result["data"]["is_plus_ev"] is False
        assert result["data"]["edge"] < 0

    def test_single_leg(self):
        result = parlay_analysis({
            "params": {"legs": "0.60", "parlay_odds": 100}
        })
        assert result["status"] is True
        assert result["data"]["num_legs"] == 1

    def test_correlation_increases_prob(self):
        # Positive correlation means legs are more likely to all hit together
        # combined = independent + corr * (min_leg - independent) > independent
        r1 = parlay_analysis({
            "params": {"legs": "0.58,0.62", "parlay_odds": 300, "correlation": 0.0}
        })
        r2 = parlay_analysis({
            "params": {"legs": "0.58,0.62", "parlay_odds": 300, "correlation": 0.2}
        })
        assert r2["data"]["combined_fair_prob"] > r1["data"]["combined_fair_prob"]

    def test_decimal_odds_format(self):
        result = parlay_analysis({
            "params": {"legs": "0.58,0.62", "parlay_odds": 5.0, "odds_format": "decimal"}
        })
        assert result["status"] is True

    def test_invalid_leg_prob(self):
        result = parlay_analysis({
            "params": {"legs": "0.58,1.5", "parlay_odds": 300}
        })
        assert result["status"] is False

    def test_missing_legs(self):
        result = parlay_analysis({"params": {"parlay_odds": 300}})
        assert result["status"] is False

    def test_invalid_correlation(self):
        result = parlay_analysis({
            "params": {"legs": "0.58,0.62", "parlay_odds": 300, "correlation": 0.8}
        })
        assert result["status"] is False

    def test_kelly_fraction_computed(self):
        result = parlay_analysis({
            "params": {"legs": "0.58,0.62,0.55", "parlay_odds": 600}
        })
        assert "kelly_fraction" in result["data"]

    def test_combined_prob_is_product(self):
        result = parlay_analysis({
            "params": {"legs": "0.50,0.50", "parlay_odds": 400}
        })
        assert abs(result["data"]["combined_fair_prob"] - 0.25) < 0.001


# ============================================================
# Line Movement
# ============================================================


class TestLineMovement:
    def test_basic_moneyline_movement(self):
        result = line_movement({
            "params": {"open_odds": -140, "close_odds": -160}
        })
        assert result["status"] is True
        assert result["data"]["moneyline"]["prob_shift"] > 0
        assert result["data"]["moneyline"]["moved_toward"] == "favorite"

    def test_no_movement(self):
        result = line_movement({
            "params": {"open_odds": -150, "close_odds": -150}
        })
        assert result["status"] is True
        assert result["data"]["moneyline"]["prob_shift"] == 0
        assert result["data"]["moneyline"]["direction"] == "no movement"

    def test_underdog_movement(self):
        result = line_movement({
            "params": {"open_odds": -150, "close_odds": -130}
        })
        assert result["status"] is True
        assert result["data"]["moneyline"]["prob_shift"] < 0
        assert result["data"]["moneyline"]["moved_toward"] == "underdog"

    def test_spread_only(self):
        result = line_movement({
            "params": {"open_line": -6.5, "close_line": -7.5, "market_type": "spread"}
        })
        assert result["status"] is True
        assert result["data"]["spread"]["line_change"] == -1.0
        assert result["data"]["spread"]["direction"] == "moved toward favorite"

    def test_total_movement(self):
        result = line_movement({
            "params": {"open_line": 220.5, "close_line": 223.5, "market_type": "total"}
        })
        assert result["status"] is True
        assert result["data"]["spread"]["direction"] == "total moved up"

    def test_both_ml_and_spread(self):
        result = line_movement({
            "params": {
                "open_odds": -140,
                "close_odds": -160,
                "open_line": -6.5,
                "close_line": -7.5,
            }
        })
        assert result["status"] is True
        assert "moneyline" in result["data"]
        assert "spread" in result["data"]

    def test_large_movement_steam_move(self):
        # 6%+ probability shift
        result = line_movement({
            "params": {"open_odds": -120, "close_odds": -200}
        })
        assert result["data"]["magnitude"] == "large"
        assert result["data"]["classification"] == "steam_move"

    def test_small_movement(self):
        # < 2% probability shift
        result = line_movement({
            "params": {"open_odds": -150, "close_odds": -155}
        })
        assert result["data"]["magnitude"] == "small"
        assert result["data"]["classification"] == "minor_adjustment"

    def test_missing_both_pairs(self):
        result = line_movement({"params": {"open_odds": -140}})
        assert result["status"] is False

    def test_reverse_line_movement(self):
        # ML moves toward favorite but spread moves toward underdog
        result = line_movement({
            "params": {
                "open_odds": -140,
                "close_odds": -160,
                "open_line": -7.5,
                "close_line": -6.5,
            }
        })
        assert result["data"]["classification"] == "reverse_line_movement"
