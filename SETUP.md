# ClinicalBridge — Setup

Run these on your own machine (Mac), not in this sandbox — you'll want the repo on your
disk so you can push to GitHub and keep iterating.

## 1. Get the project onto your machine

If you're starting from what's in this chat, download the project files I've created
so far (I'll package them at the end of each day), or just recreate the folder structure
locally and I'll keep generating files into it as we go.

```
clinicalbridge/
├── data/
│   ├── ehr/            # 10 patient EHR JSON files
│   ├── rpm/            # 10 patient RPM JSON files
│   ├── anamnesis/      # 10 patient anamnesis JSON files
│   └── scenarios/      # 5 gold-standard test scenarios
├── scripts/
│   ├── patient_cohort.py
│   └── generate_dataset.py
├── requirements.txt
└── .env.example
```

## 2. Create a virtual environment

```bash
cd clinicalbridge
python3 -m venv venv
source venv/bin/activate        # on Mac/Linux
```

You'll need to run `source venv/bin/activate` every time you open a new terminal
to work on this project. Your prompt should show `(venv)` when it's active.

## 3. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Get a Gemini API key

1. Go to https://aistudio.google.com/app/apikey
2. Create a key (free tier is fine for this project's scale)
3. Copy it

## 5. Set up your .env file

```bash
cp .env.example .env
```

Then open `.env` and paste your real key in:

```
GOOGLE_API_KEY=AIza...your-actual-key...
GEMINI_MODEL=gemini-2.0-flash
```

**Never commit `.env` to git** — only `.env.example` (with placeholder values) goes
in the repo. Add this to a `.gitignore`:

```
venv/
.env
__pycache__/
*.pyc
chroma_db/
```

## 6. Regenerate the dataset (if needed)

The dataset is already generated and committed as JSON, but if you ever change
`patient_cohort.py` or `generate_dataset.py` and need to rebuild it:

```bash
cd scripts
python3 generate_dataset.py
```

## 7. Verify everything works

```bash
python3 -c "
import langchain
import langchain_google_genai
import chromadb
import os
from dotenv import load_dotenv
load_dotenv()
print('Imports OK')
print('API key loaded:', bool(os.getenv('GOOGLE_API_KEY')))
"
```

If that prints `API key loaded: True`, you're ready for Day 2 — building the agents.

---

**Where we are:** Day 1 done (dataset + 5 gold-standard scenarios).
**Next:** Day 2 — build the 4 agents + orchestrator against this data.
