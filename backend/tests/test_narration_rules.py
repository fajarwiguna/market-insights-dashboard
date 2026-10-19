"""Uji policy layer narasi: parsing, default, dan aturan yang dipaksa kode."""

from __future__ import annotations

from pathlib import Path

from market_report.domain import narrative_rules
from market_report.domain.narrative_rules import (
    DEFAULTS,
    HARD_RULES,
    RuleSet,
    load_rules,
    parse_rules_text,
    resolve_rules_path,
)

SAMPLE = """# Rules

## [global]
- language: id
- max_paragraphs: 1
- deductive: true

## Macros (frasa aman)
- neutral_phrasing_no_catalyst: Belum ada katalis memadai.

## [dashboard]
- max_words: 90
- must_cover: [domestic, global]

## Catatan manusia
- kalimat bebas yang bukan konfigurasi
"""


def test_parse_sections_and_types():
    values, unknown = parse_rules_text(SAMPLE)
    assert values["global"]["language"] == "id"
    assert values["global"]["max_paragraphs"] == 1
    assert values["global"]["deductive"] is True
    assert values["dashboard"]["max_words"] == 90
    assert values["dashboard"]["must_cover"] == ["domestic", "global"]
    assert values["macros"]["neutral_phrasing_no_catalyst"] == "Belum ada katalis memadai."
    assert "Catatan manusia" not in values
    # Baris di bawah heading non-konfigurasi adalah prosa, bukan nilai.
    assert unknown == ()


def test_parse_nested_bullet_lists():
    text = (
        "# Rules\n\n## [equity_snapshot]\n"
        "- max_words: 250\n"
        "- sections:\n"
        "  - market\n"
        "  - macro\n"
        "- must_cover:\n"
        "  - index\n"
        "  - foreign_flow\n"
        "- inline: [a, b]\n"
    )
    values, unknown = parse_rules_text(text)
    assert values["equity_snapshot"]["sections"] == ["market", "macro"]
    assert values["equity_snapshot"]["must_cover"] == ["index", "foreign_flow"]
    assert values["equity_snapshot"]["inline"] == ["a", "b"]
    assert unknown == ()


def test_repository_policy_file_is_loaded_and_typed():
    rules = load_rules()
    assert rules.available is True
    assert Path(rules.rules_path).is_file()
    assert rules.text("sources.mode") == "seeded"
    assert rules.text("sources.min_source_tier") == "major_media"
    assert rules.integer("dashboard.max_words") == 250
    assert rules.integer("equity_snapshot.max_sentences") == 8
    assert rules.integer("equity_snapshot.max_words") == 250
    # Daftar bertingkat pada policy terbaca sebagai list, bukan dianggap unknown.
    assert rules.get("equity_snapshot.sections") == ["market", "macro", "foreign", "sector"]
    assert "index_daily_change" in rules.get("equity_snapshot.must_cover")
    assert rules.flag("numbers.never_invent") is True
    assert rules.macro("neutral_phrasing_no_catalyst").startswith("Belum terdapat katalis")
    assert rules.rules_hash and len(rules.rules_hash) == 64
    assert rules.unknown_keys == ()


def test_page_limits_follow_policy():
    rules = load_rules()
    assert rules.page_limits("dashboard") == (10, 250)
    assert rules.page_limits("equity_snapshot") == (8, 250)


def test_hard_rules_cannot_be_loosened(tmp_path):
    policy = tmp_path / "llm_rules.md"
    policy.write_text(
        "# Rules\n\n## [numbers]\n- never_invent: false\n- preserve_sign: false\n\n"
        "## [validation]\n- number_validation: optional\n",
        encoding="utf-8",
    )
    rules = load_rules(policy)
    assert rules.flag("numbers.never_invent") is True
    assert rules.flag("numbers.preserve_sign") is True
    assert rules.text("validation.number_validation") == "required"
    assert set(rules.forced_keys) == {
        "numbers.never_invent", "numbers.preserve_sign", "validation.number_validation",
    }
    for key in rules.forced_keys:
        section, _, name = key.partition(".")
        assert (section, name) in HARD_RULES


def test_missing_file_falls_back_to_defaults_without_raising():
    rules = load_rules(Path("tidak-ada-file-policy.md"))
    assert rules.available is False
    assert "tidak-ada-file-policy.md" in rules.rules_path
    assert rules.text("sources.mode") == DEFAULTS["sources"]["mode"]
    assert rules.integer("cost.max_calls_per_day") == DEFAULTS["cost"]["max_calls_per_day"]
    assert rules.rules_hash == "unavailable"


def test_partial_file_keeps_defaults_for_missing_keys(tmp_path):
    policy = tmp_path / "llm_rules.md"
    policy.write_text("## [dashboard]\n- max_words: 42\n", encoding="utf-8")
    rules = load_rules(policy)
    assert rules.integer("dashboard.max_words") == 42
    assert rules.integer("dashboard.max_sentences") == DEFAULTS["dashboard"]["max_sentences"]
    assert rules.flag("numbers.never_invent") is True


def test_rules_hash_changes_with_content(tmp_path):
    first = tmp_path / "a.md"
    second = tmp_path / "b.md"
    first.write_text("## [dashboard]\n- max_words: 100\n", encoding="utf-8")
    second.write_text("## [dashboard]\n- max_words: 101\n", encoding="utf-8")
    assert load_rules(first).rules_hash != load_rules(second).rules_hash


def test_unavailable_ruleset_exposes_defaults():
    rules = RuleSet.unavailable("x.md", "gagal")
    assert rules.available is False
    assert rules.get("sources.mode") == "seeded"
    assert rules.page_limits("dashboard") == (4, 100)


def test_env_override_for_rules_file(tmp_path, monkeypatch):
    custom = tmp_path / "custom.md"
    custom.write_text("## [dashboard]\n- max_words: 77\n", encoding="utf-8")
    monkeypatch.setenv("LLM_RULES_FILE", str(custom))
    assert resolve_rules_path() == custom
    assert load_rules().integer("dashboard.max_words") == 77


def test_defaults_cover_every_hard_rule_section():
    for section, key in HARD_RULES:
        assert section in DEFAULTS and key in DEFAULTS[section]
