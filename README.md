# Integrated-Hein

## Setup

```bash
# Clone the repo
git clone <your-repo-url>
cd Integrated-Hein

# Create virtual environment
# If using pyenv (.python-version will auto-select the correct version):
python -m venv env

# If not using pyenv, specify Python 3.12 manually:
python3.12 -m venv env

# Activate it
source env/bin/activate        # macOS/Linux
# env\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt
```

## Input Data

Place all journal folders inside a folder named `Input/` in the project root:

```
Input/
├── ajil0120no1/
├── blj0143no1/
└── ...
```