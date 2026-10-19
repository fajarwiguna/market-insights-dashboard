import os
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from market_report.services.narration.providers.registry import llm_provider

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print("Memulai Smoke Test Aion Labs...")
    
    # Inisialisasi provider berdasarkan variabel lingkungan yang aktif
    provider = llm_provider()
    print("Provider:", type(provider), getattr(provider, "model", None), getattr(provider, "base_url", None))
    
    system_prompt = "You are an AI that outputs valid JSON. Output format: {'health': 'OK'}"
    user_prompt = "Perform a quick system health check."
    
    try:
        # Menguji generate dengan ekspektasi JSON (karena LLM_JSON_MODE=true)
        response = provider.generate(system=system_prompt, user=user_prompt)
        response_text = response.text
        
        print("\nRespons Mentah dari LLM:")
        print(response_text)
        
        # Validasi apakah teks respons benar-benar JSON yang valid
        parsed_json = json.loads(response_text)
        print("\nValidasi JSON Sukses:", parsed_json)
        
    except Exception as e:
        print(f"\n❌ Pengujian Gagal: {str(e)}")

if __name__ == "__main__":
    main()
