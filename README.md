# RTR's TN Election Watch 2026

A self-hostable transparency tool for Tamil Nadu's 2026 Legislative Assembly Election. Browse, search, compare, and analyze official candidate affidavit data across all 234 constituencies.

## Features

- **Browse Constituencies** – View all candidates in any of the 233 constituency folders
- **Candidate Profiles** – Parsed affidavit data: assets, education, criminal cases, profession
- **Compare Candidates** – Side-by-side comparison of any candidates in a constituency
- **Analytics Dashboard** – Party-wise stats, wealth distribution, education breakdown, crorepati list
- **Search** – Find any candidate by name, party, or constituency
- **PDF Viewer** – View or download original affidavit PDFs directly
- **CSV Export** – Download structured data for analysis/journalism
- **OCR Pipeline** – Extracts text from image-based PDF affidavits in the background

## Quick Start

### Prerequisites

- Python 3.10+
- Tesseract OCR: `brew install tesseract`
- Poppler (for PDF rendering): `brew install poppler`

### Setup

```bash
cd TN_election_suite
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Run the Web App

```bash
python run.py
# Open http://localhost:8000
```

The site works immediately with candidate names, parties, and constituencies parsed from filenames. No OCR needed for basic browsing.

### Run OCR Extraction (Background)

This enriches profiles with age, education, assets, criminal cases, etc.

```bash
# Process all candidates (takes several hours)
python scripts/ocr_extract.py

# Process a single constituency
python scripts/ocr_extract.py --constituency KOLATHUR

# Adjust parallelism
python scripts/ocr_extract.py --workers 4

# Re-process everything
python scripts/ocr_extract.py --reset
```

Progress is visible on the web UI. Analytics update automatically as data is extracted.

### Self-Hosting (Static IP)

```bash
# Serve on port 80 (may need sudo)
python run.py --port 80

# Or use a higher port
python run.py --port 8000
```

Then share `http://<your-static-ip>:8000` with anyone.

## Project Structure

```
TN_election_suite/
├── run.py                          # Entry point
├── config.py                       # Configuration
├── requirements.txt                # Python dependencies
├── scripts/
│   └── ocr_extract.py              # OCR extraction pipeline
├── app/
│   ├── main.py                     # FastAPI application
│   ├── database.py                 # SQLite DB + queries
│   ├── routers/
│   │   ├── pages.py                # HTML page routes
│   │   └── api.py                  # JSON API + CSV export
│   ├── templates/                  # Jinja2 HTML templates
│   └── static/                     # CSS + JS
├── data/
│   └── election.db                 # SQLite database (auto-created)
└── TamilNadu_candidate_affidavits/ # Source PDFs
    ├── ALANDUR/
    ├── ANNA_NAGAR/
    └── ... (233 folders)
```

## Known Issues

1. Two constituencies are named Tirupattur – all candidates are in a single folder
2. ~25 PDFs could not be scraped (listed in errors.txt)

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/constituencies` | List all constituencies |
| `GET /api/candidates/{id}` | Candidates in a constituency |
| `GET /api/search?q=...` | Search candidates |
| `GET /api/compare?ids=1,2,3` | Compare candidates |
| `GET /api/party-stats` | Party-wise statistics |
| `GET /api/progress` | OCR extraction progress |
| `GET /api/export/candidates` | Download CSV |
