"""Deteksi sinyal pasar dan rencana pencarian berita (blueprint §3A–§3B).

Modul ini hanya membaca angka payload yang sudah tampil
(`NarrativeContext.numbers()`), lalu menurunkannya menjadi:

- instrumen mana yang bergerak material beserta arahnya,
- kueri pencarian berita yang diturunkan dari sinyal itu (dinamis per hari),
- catatan divergensi antar pasar.

Tidak ada I/O dan tidak ada panggilan LLM. Semua ambang berasal dari policy
(bagian `[thresholds]`) sehingga operator bisa menyetelnya tanpa mengubah kode.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

DEFAULT_THRESHOLDS: dict[str, float] = {
    "index_material_pct": 0.35,
    "fx_material_pct": 0.25,
    "commodity_material_pct": 0.5,
    "yield_material_bp": 3.0,
    "coal_material_pct": 1.0,
    "foreign_flow_material_idr_bn": 250.0,
    "capital_flow_material_usd_mn": 100.0,
    "max_query_count": 6,
    "queries_per_signal": 2,
}

# Instrumen tetap: prefix key -> (label, jenis, topik bukti).
_INSTRUMENTS: dict[str, tuple[str, str, str]] = {
    "market.ihsg": ("IHSG", "index", "indonesian_equity"),
    "market.dji": ("Dow Jones (DJI)", "index", "global_equity"),
    "fx.usd_idr": ("USD/IDR", "fx", "fx"),
    "fx.dxy": ("indeks dolar AS (DXY)", "fx", "fx"),
    "commodities.gold": ("harga emas", "commodity", "commodities"),
    "commodities.brent": ("minyak Brent", "commodity", "commodities"),
    "commodities.antam": ("harga emas Antam", "commodity", "commodities"),
    "rates.sbn10": ("imbal hasil SBN 10 tahun", "yield", "yields"),
    "rates.sbn5": ("imbal hasil SBN 5 tahun", "yield", "yields"),
    "rates.ust10": ("imbal hasil UST 10 tahun", "yield", "global_macro"),
    "rates.ust5": ("imbal hasil UST 5 tahun", "yield", "global_macro"),
}

_THRESHOLD_KEY = {
    "index": "index_material_pct",
    "fx": "fx_material_pct",
    "commodity": "commodity_material_pct",
    "yield": "yield_material_bp",
}

_UP = ("naik", "menguat", "menanjak", "melonjak")
_DOWN = ("turun", "melemah", "menyusut", "anjlok")


@dataclass(frozen=True)
class Signal:
    """Satu pergerakan bermakna beserta kueri pencarian yang diturunkan darinya."""

    key: str
    label: str
    kind: str
    change: float
    unit: str
    direction: int
    threshold: float
    topics: tuple[str, ...] = ()
    queries: tuple[str, ...] = ()

    @property
    def material(self) -> bool:
        return abs(self.change) >= self.threshold

    @property
    def direction_word(self) -> str:
        if self.direction > 0:
            return _UP[0]
        if self.direction < 0:
            return _DOWN[0]
        return "bergerak"

    def describe(self) -> str:
        value = f"{abs(self.change):.2f}".rstrip("0").rstrip(".")
        suffix = "%" if self.unit == "percent" else "bp"
        return f"{self.label} {self.direction_word} {value}{suffix}"


@dataclass(frozen=True)
class SignalSet:
    """Kumpulan sinyal + topik + kueri untuk satu sesi laporan."""

    signals: tuple[Signal, ...] = ()
    topics: tuple[str, ...] = ()
    queries: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def material(self) -> list[Signal]:
        return [signal for signal in self.signals if signal.material]

    def summary(self) -> list[str]:
        return [signal.describe() for signal in self.material]


def _number(numbers: dict, key: str) -> float | None:
    value = numbers.get(key)
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _direction(change: float) -> int:
    if change > 1e-9:
        return 1
    if change < -1e-9:
        return -1
    return 0


def _queries_for(label: str, kind: str, direction: int, *, limit: int) -> list[str]:
    """Bentuk kueri pencarian dari sinyal, bukan dari daftar kata kunci statis."""
    word = _UP[0] if direction > 0 else _DOWN[0] if direction < 0 else "bergerak"
    queries = [f"katalis {label} {word}", f"penyebab {label} {word} hari ini"]
    if kind == "fx":
        queries.append(f"nilai tukar rupiah terhadap dolar {word}")
    elif kind == "yield":
        queries.append(f"pasar obligasi {label} {word}")
    elif kind == "index":
        queries.append(f"arus modal asing bursa {word}")
    elif kind == "commodity":
        queries.append(f"faktor harga {label} {word}")
    return queries[: max(1, limit)]


def _instrument_signals(numbers: dict, thresholds: dict[str, float], *, per_signal: int) -> list[Signal]:
    signals: list[Signal] = []
    for prefix, (label, kind, topic) in _INSTRUMENTS.items():
        change = _number(numbers, f"{prefix}.change_pct")
        unit = "percent"
        if change is None:
            change = _number(numbers, f"{prefix}.change_bp")
            unit = "bp"
        if change is None:
            continue
        threshold = float(thresholds[_THRESHOLD_KEY[kind]])
        direction = _direction(change)
        signal = Signal(key=prefix, label=label, kind=kind, change=change, unit=unit,
                        direction=direction, threshold=threshold, topics=(topic,))
        if signal.material:
            signal = replace(signal, queries=tuple(_queries_for(label, kind, direction,
                                                                limit=per_signal)))
        signals.append(signal)
    return signals


def _flow_signals(numbers: dict, thresholds: dict[str, float], *, per_signal: int) -> list[Signal]:
    signals: list[Signal] = []
    net_idr = _number(numbers, "foreign_flow.net_idr")
    threshold_idr = float(thresholds["foreign_flow_material_idr_bn"]) * 1e9
    if net_idr is not None:
        direction = _direction(net_idr)  # arus keluar (negatif) menekan pasar
        flow_word = "keluar" if net_idr < 0 else "masuk"
        queries = (f"arus modal asing saham {flow_word}",
                   f"net {'jual' if net_idr < 0 else 'beli'} asing IHSG")[: max(1, per_signal)]
        signals.append(Signal(key="foreign_flow.net_idr", label="arus dana asing saham",
                              kind="flow", change=net_idr, unit="IDR", direction=direction,
                              threshold=threshold_idr,
                              topics=("capital_market",),
                              queries=tuple(queries) if abs(net_idr) >= threshold_idr else ()))

    capital = _number(numbers, "capital_flow.saham.1d")
    threshold_usd = float(thresholds["capital_flow_material_usd_mn"])
    if capital is not None:
        signals.append(Signal(key="capital_flow.saham.1d", label="arus modal asing saham (1D)",
                              kind="flow", change=capital, unit="USD_mn",
                              direction=_direction(capital), threshold=threshold_usd,
                              topics=("capital_market",)))
    return signals


def detect_signals(numbers: dict, *, thresholds: dict | None = None, report_date: str = "",
                   max_queries: int | None = None) -> SignalSet:
    """Ubah angka payload menjadi himpunan sinyal, topik, dan kueri pencarian.

    Hanya instrumen dengan perubahan material yang menghasilkan kueri, tetapi
    topik tetap dikumpulkan agar bukti pendukung (mis. makro) tetap dapat dicari.
    """
    limits = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    per_signal = int(limits.get("queries_per_signal", 2) or 2)
    cap = int(max_queries if max_queries is not None else limits.get("max_query_count", 6) or 6)

    signals = _instrument_signals(numbers, limits, per_signal=per_signal)
    signals += _flow_signals(numbers, limits, per_signal=per_signal)

    # Instrumen dinamis dari halaman equity (indeks pembanding, penggerak saham).
    index_threshold = float(limits["index_material_pct"])
    for key, value in numbers.items():
        if key.startswith("market_performance.") and key.endswith(".change_pct"):
            change = _number(numbers, key)
            if change is None:
                continue
            slug = key.split(".")[1]
            label = f"indeks {slug.replace('_', ' ')}"
            signals.append(Signal(key=key, label=label, kind="index", change=change, unit="percent",
                                  direction=_direction(change), threshold=index_threshold,
                                  topics=("global_equity",),
                                  queries=tuple(_queries_for(label, "index", _direction(change),
                                                             limit=per_signal))
                                  if abs(change) >= index_threshold else ()))
        elif key.startswith("movers.") and key.endswith(".change_pct"):
            change = _number(numbers, key)
            if change is None:
                continue
            ticker = key.split(".")[2].upper() if len(key.split(".")) > 2 else key
            label = f"saham {ticker}"
            material = abs(change) >= float(limits["commodity_material_pct"])
            signals.append(Signal(key=key, label=label, kind="equity", change=change, unit="percent",
                                  direction=_direction(change),
                                  threshold=float(limits["commodity_material_pct"]),
                                  topics=("corporate_action", "indonesian_equity"),
                                  queries=(f"berita saham {ticker}",) if material else ()))
        elif key == "coal.mtd_pct":
            change = _number(numbers, key)
            if change is not None:
                signals.append(Signal(key=key, label="harga batubara (MTD)", kind="commodity",
                                      change=change, unit="percent", direction=_direction(change),
                                      threshold=float(limits["coal_material_pct"]),
                                      topics=("commodities",)))

    material = [signal for signal in signals if signal.material]
    queries: list[str] = []
    for signal in material:
        for query in signal.queries:
            if query not in queries:
                queries.append(query)
    queries = queries[:cap]

    topics: list[str] = []
    for signal in signals:
        for topic in signal.topics:
            if topic not in topics:
                topics.append(topic)

    notes = _divergence_notes(numbers, limits)
    # Topik tambahan yang tidak berupa pergerakan tunggal (paritas dengan topic_plan).
    if any(str(key).startswith("macro.") for key in numbers) and "indonesia_macro" not in topics:
        topics.append("indonesia_macro")
    if any(str(key).startswith("flows.") for key in numbers) and "global_equity" not in topics:
        topics.append("global_equity")
    return SignalSet(signals=tuple(signals), topics=tuple(topics), queries=tuple(queries), notes=tuple(notes))


def _divergence_notes(numbers: dict, thresholds: dict[str, float]) -> list[str]:
    """Catat divergensi arah yang layak disebut analisis lintas pasar."""
    notes: list[str] = []
    ihsg = _number(numbers, "market.ihsg.change_pct")
    dji = _number(numbers, "market.dji.change_pct")
    index_threshold = float(thresholds["index_material_pct"])
    if ihsg is not None and dji is not None:
        if abs(ihsg) >= index_threshold and abs(dji) >= index_threshold and _direction(ihsg) != _direction(dji):
            notes.append("Pasar domestik dan global bergerak berlawanan arah.")
    usd = _number(numbers, "fx.usd_idr.change_pct")
    dxy = _number(numbers, "fx.dxy.change_pct")
    fx_threshold = float(thresholds["fx_material_pct"])
    if usd is not None and dxy is not None:
        if abs(usd) >= fx_threshold and abs(dxy) >= fx_threshold and _direction(usd) != _direction(dxy):
            notes.append("Rupiah bergerak tidak searah dengan indeks dolar AS.")
    sbn = _number(numbers, "rates.sbn10.change_bp")
    ust = _number(numbers, "rates.ust10.change_bp")
    yield_threshold = float(thresholds["yield_material_bp"])
    if sbn is not None and ust is not None:
        if abs(sbn) >= yield_threshold and abs(ust) >= yield_threshold and _direction(sbn) != _direction(ust):
            notes.append("Imbal hasil SBN dan US Treasury bergerak berlawanan arah.")
    return notes


def thresholds_from_rules(rules) -> dict[str, float]:
    """Ambil ambang sinyal dari RuleSet policy (bagian [thresholds])."""
    values: dict[str, float] = {}
    for key, default in DEFAULT_THRESHOLDS.items():
        values[key] = rules.number(f"thresholds.{key}", default)
    return values


__all__ = ["Signal", "SignalSet", "detect_signals", "thresholds_from_rules", "DEFAULT_THRESHOLDS"]
