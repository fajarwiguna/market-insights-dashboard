"""Uji judul pasar: selalu searah data dan tidak boleh saling bertentangan."""

from __future__ import annotations

from market_report.domain.market_analysis import build_headline, headline_consistency_issues


def report(usd: float | None = None, ihsg: float | None = None) -> dict:
    data: dict = {"report_date_iso": "2026-10-16", "fx": {}, "indices": {}, "yields": {},
                  "commodities": {}, "bi": {}}
    if usd is not None:
        data["fx"]["USD/IDR"] = {"today": 17903, "prev": 17916, "change_pct": usd,
                                 "date": "2026-10-16"}
    if ihsg is not None:
        data["indices"]["IHSG (ID)"] = {"today": 6147, "prev": 6193, "change_pct": ihsg,
                                        "date": "2026-10-16"}
    return data


def test_headline_follows_data_direction():
    assert build_headline(report(usd=0.42, ihsg=-0.75)) == "Rupiah melemah, IHSG melemah"
    assert build_headline(report(usd=-0.42, ihsg=0.75)) == "Rupiah menguat, IHSG menguat"


def test_headline_marks_flat_moves_as_stable():
    assert build_headline(report(usd=0.01, ihsg=-0.02)) == "Rupiah stabil, IHSG stabil"


def test_headline_falls_back_neutral_without_data():
    assert build_headline(report()) == "Ringkasan Pasar Hari Ini"


def test_generated_headline_is_always_consistent():
    for usd in (-1.0, -0.06, 0.0, 0.05, 0.9):
        for ihsg in (-1.2, -0.06, 0.0, 0.04, 1.1):
            data = report(usd=usd, ihsg=ihsg)
            assert headline_consistency_issues(data, build_headline(data)) == []


def test_contradictory_headline_is_flagged():
    data = report(usd=0.42, ihsg=-0.75)  # rupiah melemah, IHSG melemah
    issues = headline_consistency_issues(data, "Rupiah menguat tipis, IHSG menguat")
    assert issues, "judul yang berlawanan arah harus dilaporkan"
    assert any("rupiah" in issue for issue in issues)
    assert any("ihsg" in issue for issue in issues)


def test_empty_headline_is_flagged():
    assert headline_consistency_issues(report(usd=0.4), "") == ["judul kosong"]
