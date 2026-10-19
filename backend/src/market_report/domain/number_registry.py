"""Number Registry: angka payload sebagai satu-satunya angka yang sah.

Registry dibangun dari payload laporan/snapshot (angka yang sudah tampil di
halaman) lalu dipakai untuk memeriksa narasi: nilai, tanda, satuan, dan tanggal.
Modul ini murni (tanpa I/O dan tanpa panggilan LLM) supaya mudah diuji.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

MONTHS_ID = ("Januari", "Februari", "Maret", "April", "Mei", "Juni",
             "Juli", "Agustus", "September", "Oktober", "November", "Desember")
MONTH_NUMBERS = {name.lower(): index + 1 for index, name in enumerate(MONTHS_ID)}

# Satuan yang dikenal registry. `percent` dipakai untuk perubahan (%), `bp` untuk
# perubahan imbal hasil dalam basis poin, `count` untuk jumlah yang dihitung dari payload.
UNIT_PERCENT = "percent"
UNIT_BP = "bp"
UNIT_COUNT = "count"

_TOKEN_RE = re.compile(r"(?P<num>-?\d+(?:[.,]\d+)*)")
_PREFIX_RE = re.compile(r"(?P<prefix>Rp|IDR|USD|US\$|\$|EUR|CNY|JPY|SGD|MYR|£|€)\s?$", re.IGNORECASE)
_SUFFIX_RE = re.compile(r"^(?P<suffix>\s?(?:%|persen|bp|poin|points?|Mn|Tn|Bn|miliar|triliun|juta"
                        r"|trillion|billion|million))", re.IGNORECASE)
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_ID_DATE_RE = re.compile(r"\b(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\b")
_MONTH_YEAR_RE = re.compile(r"\b([A-Za-z]+)\s+(\d{4})\b")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
# Label tenor ("SBN 10 tahun", "UST 10 thn") bukan angka pasar.
_TENOR_RE = re.compile(r"^\s?(?:tahun|thn|tahunnya|yr|y)\b", re.IGNORECASE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

_CURRENCY_UNITS = {"IDR", "USD", "IDR_bn", "IDR_tn", "IDR_mn", "IDR/gr", "USD_mn",
                   "IDR/USD", "index", "USD/oz", "USD/bbl", "USD/ton", "USD/mt"}
_PERCENT_TOKENS = {"%", "persen"}

# Kata arah menentukan tanda yang dimaksud narasi. Prosa Indonesia lazim menulis
# besaran tanpa tanda ("turun 0,75%"); yang wajib dijaga adalah arahnya tidak terbalik.
_UP_WORDS = ("naik", "menguat", "meningkat", "melonjak", "menanjak", "positif", "surplus",
             "inflow", "menggapai", "di atas", "masuk")
_DOWN_WORDS = ("turun", "melemah", "menyusut", "berkurang", "negatif", "defisit", "outflow",
               "melandai", "merosot", "di bawah", "keluar")
_POLARITY_WINDOW_BEFORE = 40
_POLARITY_WINDOW_AFTER = 24


@dataclass(frozen=True)
class NumberEntry:
    """Satu angka payload beserta identitasnya."""

    key: str
    value: Decimal | None
    unit: str = ""
    as_of: str = ""
    label: str = ""

    def display(self) -> dict[str, object]:
        return {
            "key": self.key,
            "value": None if self.value is None else float(self.value),
            "unit": self.unit,
            "as_of": self.as_of,
            "label": self.label,
        }


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    token: str
    message: str
    severity: str = "error"

    @property
    def is_error(self) -> bool:
        return self.severity == "error"


@dataclass(frozen=True)
class ExtractedNumber:
    raw: str
    candidates: tuple[Decimal, ...]
    decimals: int
    unit_hint: str = ""
    polarity: int = 0
    explicit_sign: bool = False
    position: int = 0

    @property
    def magnitude(self) -> Decimal:
        return abs(self.candidates[0])


def _to_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def decimal_candidates(raw: str) -> tuple[Decimal, ...]:
    """Tafsirkan token angka gaya Indonesia maupun Inggris.

    `6.147` bisa berarti enam ribu seratus empat puluh tujuh (gaya ID) atau
    6,147 (gaya EN). Keduanya dikembalikan agar narasi yang sah tidak ditolak,
    sementara angka yang memang tidak ada di payload tetap terdeteksi.
    """
    text = raw.strip().rstrip(".,")
    sign = ""
    if text.startswith("-"):
        sign, text = "-", text[1:]
    if not text or not text.replace(".", "").replace(",", "").isdigit():
        return ()
    has_dot, has_comma = "." in text, "," in text
    variants: set[str] = set()
    if has_dot and has_comma:
        if text.rfind(".") > text.rfind(","):
            variants.add(text.replace(",", ""))
        else:
            variants.add(text.replace(".", "").replace(",", "."))
    elif has_dot:
        parts = text.split(".")
        if all(len(part) == 3 for part in parts[1:]) and len(parts) > 1:
            variants.add(text.replace(".", ""))
        variants.add(text)
        if len(parts[-1]) != 3:
            variants.add(text.replace(".", ""))
    elif has_comma:
        parts = text.split(",")
        if all(len(part) == 3 for part in parts[1:]) and len(parts) > 1:
            variants.add(text.replace(",", ""))
        variants.add(text.replace(",", "."))
        if len(parts[-1]) == 3:
            variants.add(text.replace(",", ""))
    else:
        variants.add(text)
    result: list[Decimal] = []
    for variant in variants:
        try:
            result.append(Decimal(f"{sign}{variant}"))
        except InvalidOperation:
            continue
    return tuple(result)


def _is_label_token(text: str, match: re.Match) -> bool:
    """Benar bila token adalah bagian label/kode, bukan angka pasar.

    Contoh label: `LQ45`, `IDX30`, `US5Y`, `10Y`, `SBN 10 tahun` (ditangani terpisah).
    Awalan mata uang seperti `Rp17.903` tetap dianggap angka pasar.
    """
    before = text[:match.start()]
    after = text[match.end():]
    if before and (before[-1].isalnum() or before[-1] == "_"):
        if not _PREFIX_RE.search(before):
            return True
    if after[:1] and (after[:1].isalnum() or after[:1] == "_"):
        return True
    return False


def _date_spans(text: str) -> list[tuple[int, int]]:
    """Rentang posisi tanggal pada teks; bagian tanggal bukan angka pasar."""
    spans: list[tuple[int, int]] = []
    for pattern in (_ISO_DATE_RE, _ID_DATE_RE, _MONTH_YEAR_RE):
        spans.extend((match.start(), match.end()) for match in pattern.finditer(text or ""))
    return spans


def _in_span(position: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= position < end for start, end in spans)


def _dates_in(text: str) -> list[tuple[str, str]]:
    """Temukan tanggal pada teks: (bentuk tertulis, bentuk ISO/YYYY-MM)."""
    found: list[tuple[str, str]] = []
    for match in _ISO_DATE_RE.finditer(text or ""):
        found.append((match.group(0), match.group(0)))
    for match in _ID_DATE_RE.finditer(text or ""):
        day, month, year = match.groups()
        number = MONTH_NUMBERS.get(month.lower())
        if number:
            found.append((match.group(0), f"{year}-{number:02d}-{int(day):02d}"))
    for match in _MONTH_YEAR_RE.finditer(text or ""):
        month, year = match.groups()
        number = MONTH_NUMBERS.get(month.lower())
        if number:
            found.append((match.group(0), f"{year}-{number:02d}"))
    return found


def _sentences(text: str) -> list[tuple[str, int, int]]:
    """Potong teks menjadi kalimat beserta rentang posisinya."""
    result: list[tuple[str, int, int]] = []
    start = 0
    for match in _SENTENCE_SPLIT_RE.finditer(text or ""):
        result.append((text[start:match.start()], start, match.start()))
        start = match.end()
    tail = (text or "")[start:]
    if tail:
        result.append((tail, start, start + len(tail)))
    return result


def _direction_polarity(text: str, start: int, end: int) -> int:
    """Tentukan arah yang dimaksud narasi di sekitar sebuah angka (0 = tidak jelas)."""
    before = (text[max(0, start - _POLARITY_WINDOW_BEFORE):start] or "").lower()
    after = (text[end:end + _POLARITY_WINDOW_AFTER] or "").lower()
    for window in (before, after):
        position_up = max((window.rfind(word) for word in _UP_WORDS), default=-1)
        position_down = max((window.rfind(word) for word in _DOWN_WORDS), default=-1)
        if position_up < 0 and position_down < 0:
            continue
        return 1 if position_up > position_down else -1
    return 0


def extract_numbers(text: str) -> list[ExtractedNumber]:
    """Ambil semua token angka dari narasi beserta tafsir nilainya."""
    found: list[ExtractedNumber] = []
    spans = _date_spans(text)
    for match in _TOKEN_RE.finditer(text or ""):
        if _in_span(match.start(), spans) or _is_label_token(text, match):
            # Bagian tanggal atau label/kode — bukan angka pasar.
            continue
        raw = match.group("num")
        candidates = decimal_candidates(raw)
        if not candidates:
            continue
        digits = raw.split(".")[-1] if "," not in raw else raw.split(",")[-1]
        decimals = len(digits) if len(digits) <= 2 else 0
        before = text[:match.start()]
        after = text[match.end():]
        hint = ""
        if _PREFIX_RE.search(before):
            hint = "prefix"
        suffix = _SUFFIX_RE.match(after)
        if suffix:
            token = suffix.group("suffix").strip().lower()
            hint = "percent" if token in _PERCENT_TOKENS else ("bp" if token == "bp" else token)
        if _TENOR_RE.match(after):
            continue
        found.append(ExtractedNumber(
            raw=raw, candidates=candidates, decimals=decimals, unit_hint=hint,
            polarity=_direction_polarity(text, match.start(), match.end()),
            explicit_sign=raw.startswith(("-", "+")), position=match.start(),
        ))
    return found


class NumberRegistry:
    """Himpunan angka, satuan, dan tanggal yang sah untuk satu halaman."""

    def __init__(self, entries: list[NumberEntry], *, allow_rounding: bool = False,
                 require_separate_labels: bool = True):
        self.entries: tuple[NumberEntry, ...] = tuple(entry for entry in entries if entry is not None)
        self.allow_rounding = allow_rounding
        self.require_separate_labels = require_separate_labels
        self.allowed_values: frozenset[Decimal] = frozenset(
            entry.value for entry in self.entries if entry.value is not None
        )
        self.values_by_magnitude: dict[Decimal, list[NumberEntry]] = {}
        for entry in self.entries:
            if entry.value is None:
                continue
            self.values_by_magnitude.setdefault(abs(entry.value), []).append(entry)
        self.allowed_dates: frozenset[str] = frozenset(
            entry.as_of for entry in self.entries if entry.as_of
        )
        self.allowed_months: frozenset[str] = frozenset(date[:7] for date in self.allowed_dates)
        self.allowed_years: frozenset[int] = frozenset(
            int(date[:4]) for date in self.allowed_dates if len(date) >= 4 and date[:4].isdigit()
        )
        self.units_by_key: dict[str, str] = {entry.key: entry.unit for entry in self.entries}

    # ── pembangunan ─────────────────────────────────────────────

    @classmethod
    def from_mapping(cls, numbers: dict[str, object], *, units: dict[str, str] | None = None,
                     as_of: dict[str, str] | None = None, allow_rounding: bool = False,
                     require_separate_labels: bool = True) -> "NumberRegistry":
        """Bangun registry dari kamus `key -> nilai` (nilai null tetap dicatat tanpa angka)."""
        units = units or {}
        as_of = as_of or {}
        entries = [
            NumberEntry(key=key, value=_to_decimal(value), unit=units.get(key, ""),
                        as_of=as_of.get(key, ""))
            for key, value in numbers.items()
        ]
        return cls(entries, allow_rounding=allow_rounding,
                   require_separate_labels=require_separate_labels)

    @classmethod
    def from_entries(cls, entries: list[NumberEntry], *, allow_rounding: bool = False,
                     require_separate_labels: bool = True) -> "NumberRegistry":
        return cls(entries, allow_rounding=allow_rounding,
                   require_separate_labels=require_separate_labels)

    # ── introspeksi ─────────────────────────────────────────────

    def matches_value(self, key: str, value) -> bool:
        """Cek satu pasangan key→value (dipakai untuk memeriksa `numbers_used` LLM)."""
        decimal = _to_decimal(value)
        if decimal is None:
            return False
        for entry in self.entries:
            if entry.key != key or entry.value is None:
                continue
            if entry.value == decimal:
                return True
            if self.allow_rounding and abs(entry.value - decimal) <= self._tolerance(abs(decimal)):
                return True
        return False

    def prompt_payload(self) -> list[dict[str, object]]:
        """Daftar angka yang diberikan ke LLM (tanpa himpunan internal validator)."""
        return [entry.display() for entry in self.entries]

    def _tolerance(self, magnitude: Decimal) -> Decimal:
        """Toleransi tampilan: setengah dari digit terakhir yang ditulis narasi.

        `5.988,71` (dua desimal) mentoleransi selisih 0,005 dari nilai payload;
        `6.500` (tanpa desimal) hanya 0,5 — sehingga angka karangan tetap tertangkap.
        """
        exponent = magnitude.as_tuple().exponent
        if not isinstance(exponent, int) or exponent >= 0:
            return Decimal("0.5")
        return Decimal("0.5") * (Decimal(10) ** exponent)

    def _close_to_any(self, candidate: Decimal) -> bool:
        """Toleransi tampilan tetap menghormati tanda: hanya nilai bertanda sama yang cocok."""
        tolerance = self._tolerance(abs(candidate))
        return any(entry.value is not None and abs(entry.value - candidate) <= tolerance
                   for entry in self.entries)

    def _matches(self, candidate: Decimal) -> bool:
        """Cocokkan nilai secara utuh, termasuk tandanya."""
        if candidate in self.allowed_values:
            return True
        return self.allow_rounding and self._close_to_any(candidate)

    # ── validasi ────────────────────────────────────────────────

    def validate(self, text: str) -> list[ValidationIssue]:
        """Periksa angka dan tanggal pada narasi terhadap registry."""
        issues: list[ValidationIssue] = []
        matched: list[tuple[ExtractedNumber, NumberEntry]] = []
        for token in extract_numbers(text):
            if self._is_year_token(token):
                # Tahun diperiksa oleh aturan tanggal, bukan aturan angka.
                continue
            entry = self._matched_entry(token)
            if entry is not None:
                matched.append((token, entry))
                if token.unit_hint in {UNIT_PERCENT, UNIT_BP}:
                    issues.extend(self._check_unit(token))
                continue
            issues.append(self._unmatched_issue(token))
        issues.extend(self._check_dates(text))
        if self.require_separate_labels:
            issues.extend(self._check_mixed_dates(text, matched))
        return issues

    def _check_mixed_dates(self, text: str,
                           matched: list[tuple[ExtractedNumber, NumberEntry]]) -> list[ValidationIssue]:
        """Peringatkan bila satu kalimat menyebut satu tanggal tetapi memuat angka
        dari observasi bertanggal lain (N5: jangan mencampur tanggal)."""
        if not matched:
            return []
        issues: list[ValidationIssue] = []
        for sentence, start, end in _sentences(text):
            dates = {iso for _, iso in _dates_in(sentence)
                     if len(iso) == 10 and iso in self.allowed_dates}
            if len(dates) != 1:
                continue
            mentioned = next(iter(dates))
            for token, entry in matched:
                if not (start <= token.position < end) or not entry.as_of:
                    continue
                if entry.as_of != mentioned:
                    issues.append(ValidationIssue(
                        "mixed_observation_date", token.raw,
                        f"Angka {token.raw} berasal dari {entry.as_of}, bukan {mentioned}.",
                        severity="warning"))
        return issues

    def _entry_for_value(self, candidate: Decimal) -> NumberEntry | None:
        tolerance = self._tolerance(abs(candidate))
        for entry in self.entries:
            if entry.value is None:
                continue
            if entry.value == candidate:
                return entry
            if self.allow_rounding and abs(entry.value - candidate) <= tolerance:
                return entry
        return None

    def _matched_entry(self, token: ExtractedNumber) -> NumberEntry | None:
        """Kembalikan entri payload yang cocok, atau None bila angka tidak sah.

        Besaran tanpa tanda diterima hanya bila kata arah pada narasi sesuai
        dengan tanda di payload ("turun 0,75%" untuk perubahan -0,75%).
        """
        for candidate in token.candidates:
            if self._matches(candidate):
                return self._entry_for_value(candidate)
        if token.explicit_sign or token.polarity == 0:
            return None
        for candidate in token.candidates:
            magnitude = abs(candidate)
            tolerance = self._tolerance(magnitude)
            for entry in self.entries:
                if entry.value is None:
                    continue
                if abs(abs(entry.value) - magnitude) > tolerance:
                    continue
                if (entry.value > 0) == (token.polarity > 0):
                    return entry
        return None

    def _is_year_token(self, token: ExtractedNumber) -> bool:
        """Token 4 digit 19xx/20xx diperlakukan sebagai tahun, bukan angka pasar."""
        raw = token.raw.lstrip("-")
        return len(raw) == 4 and raw.isdigit() and raw[:2] in {"19", "20"}

    def _unmatched_issue(self, token: ExtractedNumber) -> ValidationIssue:
        """Bedakan angka yang tidak ada dari angka yang arahnya terbalik."""
        for candidate in token.candidates:
            tolerance = self._tolerance(abs(candidate))
            for entry in self.entries:
                if entry.value is None:
                    continue
                same_magnitude = abs(abs(entry.value) - abs(candidate)) <= tolerance
                opposite_sign = entry.value == -candidate or (same_magnitude
                                                              and (entry.value > 0) != (candidate > 0))
                if opposite_sign:
                    return ValidationIssue("sign_mismatch", token.raw,
                                           f"Angka {token.raw} ada di payload dengan arah berlawanan.")
        return ValidationIssue("unknown_number", token.raw,
                               f"Angka {token.raw} tidak ada pada data halaman.")

    def _check_unit(self, token: ExtractedNumber) -> list[ValidationIssue]:
        wanted = UNIT_PERCENT if token.unit_hint == UNIT_PERCENT else UNIT_BP
        for entry in self.entries:
            if entry.value is None:
                continue
            if any(abs(entry.value) == abs(candidate) for candidate in token.candidates):
                if entry.unit == wanted:
                    return []
        return [ValidationIssue("unit_mismatch", token.raw,
                                f"Satuan '{token.unit_hint}' pada {token.raw} tidak sesuai data.",
                                severity="warning")]

    def _check_dates(self, text: str) -> list[ValidationIssue]:
        found = _dates_in(text)
        issues: list[ValidationIssue] = []
        for raw, iso in found:
            if len(iso) == 10 and iso in self.allowed_dates:
                continue
            if len(iso) == 7 and iso in self.allowed_months:
                continue
            if len(iso) == 10 and iso[:7] in self.allowed_months and int(iso[:4]) in self.allowed_years:
                issues.append(ValidationIssue("unknown_date", raw,
                                              f"Tanggal {raw} tidak ada pada data halaman.",
                                              severity="warning"))
                continue
            if len(iso) == 7 and int(iso[:4]) in self.allowed_years:
                continue
            issues.append(ValidationIssue("unknown_date", raw,
                                          f"Tanggal {raw} tidak berasal dari data halaman."))
        for match in _YEAR_RE.finditer(text or ""):
            year = int(match.group(0))
            if self.allowed_years and year not in self.allowed_years:
                issues.append(ValidationIssue("future_year", match.group(0),
                                              f"Tahun {year} tidak ada pada data halaman."))
        return issues

    def errors(self, text: str) -> list[ValidationIssue]:
        return [issue for issue in self.validate(text) if issue.is_error]

    def summary(self) -> dict[str, int]:
        return {"entries": len(self.entries), "values": len(self.allowed_values),
                "dates": len(self.allowed_dates)}
