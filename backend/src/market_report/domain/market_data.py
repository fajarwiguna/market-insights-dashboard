"""Pencarian instrumen pada data pasar."""

def find_key(data: dict, *needles: str, exclude: tuple[str, ...] = ()) -> str | None:
    """Cari nama key pertama yang mengandung semua kata kunci (case-insensitive)."""
    for k in data or {}:
        kl = str(k).lower()
        if all(n.lower() in kl for n in needles) and not any(e.lower() in kl for e in exclude):
            return k
    return None


def pick(data: dict, *needles: str, exclude: tuple[str, ...] = ()) -> dict:
    """Ambil satu baris data (dict) berdasarkan kata kunci nama instrument."""
    if not isinstance(data, dict):
        return {}
    key = find_key(data, *needles, exclude=exclude)
    val = data.get(key) if key else None
    return val if isinstance(val, dict) else {}
