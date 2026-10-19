"""Uji Number Registry: pelindung angka payload dari karangan LLM."""

from __future__ import annotations

from decimal import Decimal

from market_report.domain.number_registry import (
    NumberEntry,
    NumberRegistry,
    decimal_candidates,
    extract_numbers,
)

NUMBERS = {
    "market.ihsg.last": 6147,
    "market.ihsg.change_pct": -0.75,
    "fx.usd_idr.last": 17903,
    "foreign_flow.value": -1613.46,
    "sector.energy.mtd_pct": 2.39,
    "rates.sbn10.change_bp": -2.4,
    "spread.sbn10_ust10": 225,
    "breadth.rising_sectors": 4,
    "market.dji.last": 46120.5,
}
UNITS = {
    "market.ihsg.last": "index",
    "market.ihsg.change_pct": "percent",
    "fx.usd_idr.last": "IDR/USD",
    "foreign_flow.value": "IDR_bn",
    "sector.energy.mtd_pct": "percent",
    "rates.sbn10.change_bp": "bp",
    "spread.sbn10_ust10": "bp",
    "breadth.rising_sectors": "count",
    "market.dji.last": "index",
}
AS_OF = {
    "market.ihsg.last": "2026-10-16",
    "market.ihsg.change_pct": "2026-10-16",
    "fx.usd_idr.last": "2026-10-16",
    "foreign_flow.value": "2026-10-16",
    "sector.energy.mtd_pct": "2026-10-16",
    "rates.sbn10.change_bp": "2026-10-15",
    "spread.sbn10_ust10": "2026-10-15",
    "breadth.rising_sectors": "2026-10-16",
    "market.dji.last": "2026-10-15",
}


def registry(**overrides) -> NumberRegistry:
    return NumberRegistry.from_mapping(NUMBERS, units=UNITS, as_of=AS_OF, **overrides)


def codes(text: str, **kwargs) -> list[str]:
    return [issue.code for issue in registry(**kwargs).validate(text)]


def test_indonesian_and_english_number_interpretation():
    assert Decimal("6147") in decimal_candidates("6.147")
    assert Decimal("1613.46") in decimal_candidates("1.613,46")
    assert Decimal("17903") in decimal_candidates("17.903")
    assert Decimal("0.75") in decimal_candidates("0,75")
    assert Decimal("-0.75") in decimal_candidates("-0,75")
    assert decimal_candidates("abc") == ()


def test_extract_numbers_reads_unit_hints():
    tokens = {token.raw: token.unit_hint for token in extract_numbers("IHSG -0,75% dan Rp17.903")}
    assert tokens["-0,75"] == "percent"
    assert tokens["17.903"] == "prefix"


def test_labels_and_tenors_are_not_market_numbers():
    raws = [token.raw for token in extract_numbers("LQ45 dan IDX30, SBN 10 tahun, UST 10Y naik 1,2 bp")]
    assert raws == ["1,2"]


def test_valid_narrative_has_no_issues():
    text = ("Rupiah ditutup di Rp17.903 per dolar AS dan IHSG turun 0,75% ke 6.147 "
            "pada 16 Oktober 2026.")
    assert codes(text) == []


def test_fabricated_number_is_rejected():
    issues = registry().validate("IHSG naik ke 6.500 pada 16 Oktober 2026.")
    assert [issue.code for issue in issues] == ["unknown_number"]
    assert issues[0].is_error is True
    assert "6.500" in issues[0].message


def test_sign_flip_is_reported_as_sign_mismatch():
    issues = registry().validate("IHSG naik 0,75% hari ini.")
    assert [issue.code for issue in issues] == ["sign_mismatch"]


def test_exact_negative_value_is_accepted():
    assert codes("IHSG turun 0,75% dan net foreign flow -1.613,46 miliar.") == []


def test_unit_warning_when_percent_label_mismatches():
    issues = registry().validate("Spread SBN dua tahun 225%.")
    assert [issue.code for issue in issues] == ["unit_mismatch"]
    assert issues[0].is_error is False


def test_unknown_date_and_year_are_rejected():
    assert "unknown_date" in codes("Data per 20 Desember 2026 menunjukkan tekanan.")
    assert "future_year" in codes("Proyeksi 2031 tidak tersedia.")


def test_number_from_another_observation_date_is_only_a_warning():
    issues = registry().validate("Imbal hasil SBN 10Y turun 2,4 bp pada 16 Oktober 2026.")
    assert [(issue.code, issue.severity) for issue in issues] == [("mixed_observation_date", "warning")]
    assert "2026-10-15" in issues[0].message


def test_mixed_observation_warning_can_be_disabled():
    built = registry(require_separate_labels=False)
    assert built.validate("Imbal hasil SBN 10Y turun 2,4 bp pada 16 Oktober 2026.") == []


def test_allowed_month_and_year_are_accepted():
    assert codes("Energi menguat 2,39% MTD pada September 2026.") == []
    assert codes("Data per Oktober 2026 belum lengkap.") == []


def test_trailing_zero_is_the_same_value():
    assert codes("Spread SBN dua tahun 225,0 bp.") == []


def test_rounding_is_rejected_unless_enabled():
    assert codes("Dow Jones 46.120 pada 15 Oktober 2026.") == ["unknown_number"]
    assert codes("Dow Jones 46.120 pada 15 Oktober 2026.", allow_rounding=True) == []


def test_rounding_never_rescues_a_wrong_sign():
    assert codes("IHSG naik 0,8% ke level 6147.", allow_rounding=True) == ["sign_mismatch"]


def test_direction_word_supplies_the_sign_for_a_bare_magnitude():
    assert codes("IHSG turun 0,75% ke 6.147.") == []
    assert codes("IHSG menguat 0,75% ke 6.147.") == ["sign_mismatch"]
    assert codes("Net foreign flow keluar 1.613,46 miliar rupiah.") == []


def test_prompt_payload_carries_values_units_and_dates():
    payload = {row["key"]: row for row in registry().prompt_payload()}
    assert payload["market.ihsg.last"] == {
        "key": "market.ihsg.last", "value": 6147.0, "unit": "index",
        "as_of": "2026-10-16", "label": "",
    }


def test_null_entries_are_kept_as_context_but_not_as_values():
    built = NumberRegistry.from_mapping({"a": None}, units={"a": "percent"}, as_of={"a": "2026-10-16"})
    assert built.prompt_payload() == [
        {"key": "a", "value": None, "unit": "percent", "as_of": "2026-10-16", "label": ""}
    ]
    assert Decimal("0") not in built.allowed_values


def test_entries_can_be_built_directly():
    built = NumberRegistry.from_entries([NumberEntry("x", Decimal("1.5"), "percent", "2026-10-16")])
    assert built.validate("Nilai 1,5% sesuai data.") == []
    assert built.summary() == {"entries": 1, "values": 1, "dates": 1}
