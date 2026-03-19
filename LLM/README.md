# JournalIndexing

OCR-based metadata extraction pipeline for academic journals using Tesseract and local LLMs (Ollama).

## Prerequisites

- Python 3.12.13
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed on your system
- [Ollama](https://ollama.com) installed and running

### Install Tesseract

**macOS:**
```bash
brew install tesseract
```

**Ubuntu/Debian:**
```bash
sudo apt install tesseract-ocr
```

**Windows:** Download the installer from [Tesseract at UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki)

### Install Ollama & Model

**macOS / Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Windows (PowerShell):**
```powershell
irm https://ollama.com/install.ps1 | iex
```

Or [download directly](https://ollama.com/download) for any platform.

Then pull the required model:
```bash
ollama pull qwen3.5:4b
```

## Setup

```bash
# Clone the repo
git clone <your-repo-url>
cd JournalIndexing

# Create virtual environment
# If using pyenv (.python-version will auto-select 3.12.13):
python -m venv env

# If not using pyenv, specify Python 3.12 manually:
python3.12 -m venv env

# Activate it
source env/bin/activate        # macOS/Linux
# env\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt
```

## Usage

Place your journal folders inside `Data/` with images in a `png/` subfolder:
```
Data/
├── ajil0120no1/
│   └── png/
│       ├── 0001.png
│       ├── 0002.png
│       └── ...
├── blj0143no1/
│   └── png/
└── ...
```

### Run the pipeline

```bash
# Process all journals in Data/:
python ocr_pipeline.py all
python ocr_pipeline.py              # also runs all (default)

# Process a specific journal:
python ocr_pipeline.py ajil0120no1

# Tab-completable path also works:
python ocr_pipeline.py Data/ajil0120no1

# Help:
python ocr_pipeline.py -h
```

### Output

Metadata JSONs and timing reports are saved to `output/`:
```
output/
├── metadata_ajil0120no1_20260307_001341.json
├── metadata_blj0143no1_20260307_064030.json
├── timing_20260307_083914.json
└── ...
```

## How It Works

1. **Initiate** — Scans `Data/{journal}/png/` for images, creates `ocrData` and `metadata` JSON files in `temp/`
2. **Extract** — For each page (up to 25), runs OCR then passes text to a local LLM to extract metadata fields
3. **Verify** — Each extracted field is validated (format, range, check digits) before being accepted
4. **Save** — Verified metadata is saved to `output/` with a timestamp

### Extracted Fields

| Field | Verifier | Example |
|-------|----------|---------|
| volume | Positive integer, 1–9999 | `120` |
| date | Month/Year, Season/Year, or Year | `January 2026` |
| title | 3–200 chars, contains letters | `American Journal of International Law` |
| issue_number | Positive integer, supports combined (1/2) | `1` |
| issn | NNNN-NNNN format with check digit validation | `0002-9300` |
| eissn | NNNN-NNNN format with check digit validation | `2161-7953` |

## Project Structure

```
JournalIndexing/
├── ocr_pipeline.py              # Main entry point (CLI)
├── requirements.txt             # Python dependencies
├── .python-version              # Python version (3.12.13)
├── .gitignore
├── README.md
├── source/
│   ├── initiateFiles.py         # Temp file setup (ocrData & metadata JSONs)
│   ├── llm.py                   # Ollama LLM integration
│   ├── metadata_extractor.py    # Orchestrator: OCR → LLM → Verify → Save
│   ├── ocr.py                   # Tesseract OCR extraction
│   └── verifier/
│       ├── verify_volume.py
│       ├── verify_date.py
│       ├── verify_title.py
│       ├── verify_issue.py
│       ├── verify_issn.py
│       └── verify_eissn.py
├── Data/                        # Journal image folders (git-ignored)
├── output/                      # Saved metadata & timing reports (git-ignored)
└── temp/                        # Runtime temp files (git-ignored)
```