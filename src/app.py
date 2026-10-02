"""Entry point kompatibilitas untuk dashboard Streamlit selama migrasi."""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "backend" / "src"
LEGACY_APP = PROJECT_ROOT / "legacy" / "streamlit" / "app.py"

sys.path.insert(0, str(SOURCE_ROOT))
sys.path.insert(0, str(LEGACY_APP.parent))

# Eksekusi pada namespace yang sama agar fungsi tetap dapat dipakai oleh
# AppTest dan skrip kompatibilitas lama yang mengimpor modul `app`.
_entry_file = __file__
try:
    __file__ = str(LEGACY_APP)
    exec(compile(LEGACY_APP.read_text(encoding="utf-8"), str(LEGACY_APP), "exec"), globals())
finally:
    __file__ = _entry_file
