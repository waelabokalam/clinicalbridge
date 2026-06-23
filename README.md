# ClinicalBridge

A multi-agent, LLM-powered prototype that synthesizes Electronic Health Records
(EHR), Remote Patient Monitoring (RPM) alerts, and patient-reported Anamnesis
data into a structured Clinical Context Brief — built for COP-3442 (Prompt
Engineering), Bahçeşehir University.

**This is an educational prototype using entirely simulated, fictional patient
data. It is not a clinical tool and must never be used for real clinical
decision-making.** See `portfolio/PROJECT_REPORT.md`, Section on Ethical
Considerations, for full disclaimers.

---

## What this does

A clinician receives dozens of RPM alerts a day and often can't quickly tell
which ones matter. ClinicalBridge takes a raw RPM alert (e.g., "blood pressure
spiked") and automatically:

1. **Triages** the alert's urgency
2. **Retrieves** relevant EHR history via RAG (ChromaDB + Gemini embeddings)
3. **Retrieves and interprets** the patient's self-reported history (symptoms,
   adherence, lifestyle)
4. **Synthesizes** all three into a single Clinical Context Brief with
   explicit source citations, confidence scoring, and flagged uncertainties

Critical alerts bypass the full pipeline and escalate immediately, per the
safety guardrail in Chapter 6.5 of the project spec.

## Example result

Given an RPM alert showing a patient's blood pressure spiking over two weeks,
ClinicalBridge's EHR agent correctly reports the medical record shows nothing
unusual — then the Anamnesis agent independently surfaces that the patient
quietly stopped taking their blood pressure medication three weeks earlier due
to a side effect, without telling their doctor. The Synthesis agent connects
these two facts, clearly marking the causal link as its own inference rather
than blurring which source said what — see `data/scenarios/S1_missed_medication.json`
for the full scenario and `portfolio/EVALUATION_REPORT.md` Section 2.1 for the
actual system output.

## Architecture

```
RPM Alert
    |
    v
[Triage Agent] -- classifies urgency, writes retrieval queries
    |
    +-- Critical? --> immediate escalation, bypass everything below
    |
    v
[EHR Agent]  (RAG over ChromaDB)      [Anamnesis Agent]  (RAG over ChromaDB)
    |                                          |
    +------------------+-----------------------+
                       v
              [Synthesis Agent]
                       |
                       v
           Clinical Context Brief
```

Five components total: 4 specialized agents + 1 orchestrator. See
`portfolio/PROMPT_ENGINEERING_PORTFOLIO.md` for full prompt design,
temperature rationale, and per-agent testing detail.

**Note:** the orchestrator dispatches EHR and Anamnesis retrieval
*sequentially*, not in parallel as originally specified. This was a
deliberate, documented adaptation to a free-tier API rate limit — see
Portfolio Section 1 and the Project Report's Known Limitations for the full
explanation.

## Tech stack

- **Orchestration:** LangChain
- **LLM:** Google Gemini (`gemini-2.5-flash-lite` in the final configuration;
  see Portfolio Section 1 for the full model-selection history)
- **Vector store:** ChromaDB, with `gemini-embedding-001` embeddings
- **Dataset:** 10 fully fictional patients, generated programmatically
  (`scripts/generate_dataset.py`) — see Data Model section below

## Repository structure

```
clinicalbridge/
├── README.md                          <- you are here
├── SETUP.md                           <- environment setup walkthrough
├── requirements.txt
├── .env.example                       <- copy to .env, add your Gemini API key
│
├── data/
│   ├── ehr/                           <- 10 patients' EHR records (JSON)
│   ├── rpm/                           <- 10 patients' RPM streams + alerts (JSON)
│   ├── anamnesis/                     <- 10 patients' self-reported history (JSON)
│   └── scenarios/                     <- 5 gold-standard test scenarios
│
├── scripts/
│   ├── patient_cohort.py              <- patient definitions
│   ├── generate_dataset.py            <- generates all EHR/RPM/anamnesis data
│   ├── build_ehr_vectorstore.py       <- chunks + embeds EHR into ChromaDB
│   └── build_anamnesis_vectorstore.py <- chunks + embeds Anamnesis into ChromaDB
│
├── agents/
│   ├── llm_client.py                  <- shared Gemini client config
│   ├── triage_agent.py
│   ├── ehr_agent.py
│   ├── anamnesis_agent.py
│   └── synthesis_agent.py
│
├── orchestrator/
│   ├── orchestrator.py                <- main pipeline: routing, retries, safety guardrail
│   └── test_critical_bypass.py        <- standalone test for the Critical-escalation path
│
├── eval/
│   ├── run_all_scenarios.py           <- runs all 5 scenarios through the full pipeline
│   ├── run_single_scenario.py         <- re-run one scenario by ID
│   ├── compare_results.py             <- side-by-side gold-standard vs. actual output
│   ├── stress_tests.py                <- 8 targeted edge-case test definitions
│   ├── run_stress_tests.py            <- executes all 8 stress tests
│   └── results/                       <- saved JSON output from every run
│
└── portfolio/
    ├── PROMPT_ENGINEERING_PORTFOLIO.md  <- full prompts, iteration logs, failure analysis
    ├── EVALUATION_REPORT.md             <- metrics, scenario results, known limitations
    └── PROJECT_REPORT.md                <- updated capstone report
```

## Running it

See `SETUP.md` for full environment setup (venv, dependencies, Gemini API
key).

```bash
# 1. Build the vector stores (one-time, or whenever data/ changes)
python3 -m scripts.build_ehr_vectorstore
python3 -m scripts.build_anamnesis_vectorstore

# 2. Run all 5 gold-standard scenarios end-to-end
python3 -m eval.run_all_scenarios

# 3. Compare actual output against gold standards
python3 -m eval.compare_results

# 4. Run the safety guardrail test
python3 -m orchestrator.test_critical_bypass

# 5. Run the 8 stress tests
python3 -m eval.run_stress_tests
```

To process a single custom alert programmatically:

```python
from orchestrator.orchestrator import process_alert

alert = {
    "alert_id": "ALT-001",
    "patient_id": "P001",
    "timestamp": "2026-06-15T05:00:00",
    "device_type": "home BP cuff",
    "alert_category": "sustained_elevated_blood_pressure",
    "measured_values": {"systolic": 178, "diastolic": 104},
    "baseline_threshold": {"systolic": 140, "diastolic": 90},
}

result = process_alert(alert)
print(result["ccb"])  # the Clinical Context Brief
```

## Data model

10 fictional patients across hypertension, type 2 diabetes, and heart failure
— entirely fabricated, generated programmatically rather than hand-written.
Patients P001-P005 are specifically constructed to each test one of the 5
gold-standard scenarios (missed medication, false alarm, silent
deterioration, incomplete record, conflicting data); P006-P010 exist purely
to give the vector stores realistic multi-patient volume, so retrieval can be
meaningfully tested against more than a single-patient store.

## Evaluation highlights

- **5/5 scenarios passed**, matching gold-standard urgency classification and
  all 15 designed failure-mode checks (anti-hallucination, source
  attribution, appropriate hedging under uncertainty).
- **8 additional stress tests** probed spec-required behaviors the 5 main
  scenarios don't exercise (urgency-boundary stability, missing input data,
  EHR-internal contradictions, sensitive disclosures, colloquial language
  translation, universal low-confidence synthesis). 7 passed outright; 1
  surfaced a real bug.
- **One real bug found and fixed**, with an honestly-reported failed first
  attempt: see `portfolio/PROMPT_ENGINEERING_PORTFOLIO.md` Section 3.6 for
  the full root-cause story.
- **The Critical-alert safety guardrail was verified working**, not just
  assumed correct — confirmed with a synthetic crisis-range alert that
  correctly bypassed the full pipeline.

Full detail in `portfolio/EVALUATION_REPORT.md`.

## Known limitations

Documented in full in `portfolio/PROJECT_REPORT.md` and
`portfolio/EVALUATION_REPORT.md` Section 5. Briefly: sequential (not
parallel) agent dispatch due to free-tier API rate limits; no numeric
retrieval precision/recall computed; small sample size (10 patients, 5
scenarios); single-evaluator grading against self-authored gold standards;
end-to-end latency exceeds the spec's 30-second target due to the rate-limit
mitigations.