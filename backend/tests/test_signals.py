"""Uji deteksi sinyal pasar dan turunan kueri pencarian (bagian 3A/3B)."""

from __future__ import annotations

from market_report.domain.narrative_rules import load_rules
from market_report.services.narration import signals


def test_thresholds_decide_which_moves_are_material():
    numbers = {
        "market.ihsg.change_pct": -0.10,      # di bawah ambang 0.35 -> bukan material
        "fx.usd_idr.change_pct": 0.40,        # di atas ambang 0.25 -> material
    }
    result = signals.detect_signals(numbers, thresholds={"index_material_pct": 0.35,
                                                         "fx_material_pct": 0.25})
    material = {signal.key for signal in result.material}
    assert material == {"fx.usd_idr"}
    assert result.summary() == ["USD/IDR naik 0.4%"]
    assert "indonesian_equity" in result.topics and "fx" in result.topics


def test_queries_are_derived_from_the_signal_not_a_static_list():
    numbers = {"market.ihsg.change_pct": -1.6}
    result = signals.detect_signals(numbers, report_date="2026-10-16")
    assert result.queries, "sinyal material harus menghasilkan kueri"
    assert all("IHSG" in query for query in result.queries)
    assert any("turun" in query for query in result.queries)
    # Kueri berasal dari instrumen + arah, bukan daftar kata kunci tetap.
    other = signals.detect_signals({"fx.usd_idr.change_pct": 0.9})
    assert all("USD/IDR" in query for query in other.queries)
    assert set(result.queries) != set(other.queries)


def test_query_count_is_capped_by_policy():
    numbers = {
        "market.ihsg.change_pct": -2.0,
        "fx.usd_idr.change_pct": 1.0,
        "rates.sbn10.change_bp": 9.0,
        "commodities.gold.change_pct": 2.0,
    }
    result = signals.detect_signals(numbers, max_queries=3)
    assert len(result.queries) == 3


def test_flat_and_missing_numbers_produce_no_queries():
    result = signals.detect_signals({"market.ihsg.change_pct": 0.0})
    assert result.queries == ()
    assert result.summary() == []


def test_divergence_notes_flag_cross_market_opposites():
    numbers = {
        "market.ihsg.change_pct": -1.0,
        "market.dji.change_pct": 0.9,
        "rates.sbn10.change_bp": 6.0,
        "rates.ust10.change_bp": -6.0,
    }
    result = signals.detect_signals(numbers)
    joined = " ".join(result.notes)
    assert "berlawanan arah" in joined
    assert "SBN" in joined and "Treasury" in joined


def test_flow_signal_uses_configurable_threshold():
    below = signals.detect_signals({"foreign_flow.net_idr": -1.0e11})
    assert not any(signal.key == "foreign_flow.net_idr" for signal in below.material)
    above = signals.detect_signals({"foreign_flow.net_idr": -1.5e12})
    flow = next(signal for signal in above.material if signal.key == "foreign_flow.net_idr")
    assert flow.direction < 0
    assert any("asing" in query for query in flow.queries)


def test_thresholds_from_rules_reads_the_policy_file():
    thresholds = signals.thresholds_from_rules(load_rules())
    assert thresholds["fx_material_pct"] == 0.25
    assert thresholds["yield_material_bp"] == 3.0
