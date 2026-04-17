import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
AFFIDAVIT_DIR = BASE_DIR / "TamilNadu_candidate_affidavits"
DB_PATH = DATA_DIR / "election.db"

OCR_DPI = 200
OCR_WORKERS = max(1, os.cpu_count() - 2)
OCR_LANG = "eng"

PARTY_FULL_NAMES = {
    "DMK": "Dravida Munnetra Kazhagam",
    "AIADMK": "All India Anna Dravida Munnetra Kazhagam",
    "TVK": "Tamilaga Vettri Kazhagam",
    "NTK": "Naam Tamilar Katchi",
    "BSP": "Bahujan Samaj Party",
    "BJP": "Bharatiya Janata Party",
    "INC": "Indian National Congress",
    "DMDK": "Desiya Murpokku Dravida Kazhagam",
    "PMK": "Pattali Makkal Katchi",
    "MDMK": "Marumalarchi Dravida Munnetra Kazhagam",
    "PT": "Puthiya Tamilagam",
    "VCK": "Viduthalai Chiruthaigal Katchi",
    "CPI": "Communist Party of India",
    "CPM": "Communist Party of India (Marxist)",
    "CPIM": "Communist Party of India (Marxist)",
    "AMMK": "Amma Makkal Munnetra Kazhagam",
    "MNM": "Makkal Needhi Maiam",
    "AISMK": "All India Samathuva Makkal Katchi",
    "IJK": "Indhiya Jananayaga Katchi",
    "TMC": "Tamil Maanila Congress",
    "IUML": "Indian Union Muslim League",
    "KMK": "Kongunadu Munnetra Kazhagam",
    "MMK": "Manithaneya Makkal Katchi",
    "Indep": "Independent",
}

ELECTION_DATE = "April 23, 2026"
TOTAL_CONSTITUENCIES = 234
APP_TITLE = "RTR's TN Election Watch 2026"
