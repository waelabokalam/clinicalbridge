# ClinicalBridge

**Multi-agent RAG that turns a monitoring alert into a source-attributed context brief, with explicit escalation and failure handling.**

Four specialist agents plus an orchestrator combine an alert, retrieved EHR history and patient-reported history. The engineering focus is keeping sources distinct, carrying uncertainty forward, and making safety-critical routing deterministic.

This is an academic prototype using synthetic patient records, built for COP-3442 at Bahcesehir University. It is not a clinical decision tool.

## Inspect the proof

| Evidence | Where to look |
|---|---|
| **5/5 gold scenarios; 15/15 designed failure-mode checks** | [Evaluation report](portfolio/EVALUATION_REPORT.md) and [saved outputs](eval/results/); qualitative checks include manual review |
| **8 targeted stress cases** | [`eval/stress_tests.py`](eval/stress_tests.py) |
| A real schema defect, failed prompt-only fix, then a verified code fix | [Prompt engineering portfolio, section 3.6](portfolio/PROMPT_ENGINEERING_PORTFOLIO.md) |
| Critical-alert bypass, retries and low-confidence fallbacks | [`orchestrator/orchestrator.py`](orchestrator/orchestrator.py) |

## Architecture

```mermaid
flowchart TD
    INPUT["Synthetic RPM alert"] --> TRIAGE["Triage agent"]
    TRIAGE --> GUARD{"Critical urgency?"}
    GUARD -->|yes| HUMAN["Immediate human escalation"]
    GUARD -->|no| EHR["EHR agent: patient-filtered ChromaDB retrieval"]
    EHR --> ANAM["Anamnesis agent: patient-reported history"]
    ANAM --> SYN["Synthesis agent"]
    SYN --> CCB["Clinical Context Brief with source labels and uncertainty"]
    EHR --> LOG["Structured session log"]
    ANAM --> LOG
    SYN --> LOG
```

**Stack:** Python, LangChain, Gemini and ChromaDB. EHR and anamnesis retrieval are dispatched sequentially in the inspected implementation to accommodate provider rate limits.

## The most useful failure story

An off-topic EHR query exposed a missing-key defect: the model omitted `relevant_labs` instead of returning an empty list. A more explicit prompt and a matching example did not fix the repeated failure. Inspection confirmed retrieval had supplied the relevant context; the defect was in generated output.

The code-level fix normalizes the expected list fields after JSON parsing, before schema validation. The same stress case then returned a complete, valid structure. This is the tradeoff the project demonstrates: use the model for extraction and synthesis, and code for stable output contracts.

| Boundary | Implementation choice |
|---|---|
| Critical escalation | Orchestrator branch bypasses downstream retrieval/synthesis |
| Missing output fields | Deterministic normalization followed by schema validation |
| Retrieval failure | Bounded retry, then explicit empty/low-confidence input |
| Source disagreement | Preserve EHR and anamnesis attribution and uncertainty |
| Terminal generation failure | Return a failed workflow with a session log |

## Run and inspect

Use [SETUP.md](SETUP.md) for dependencies, vector-store preparation and provider configuration. Agent execution requires `GOOGLE_API_KEY`; `GEMINI_MODEL` configures the model. Keep credentials local.

```bash
# Inspect saved outputs without making model calls.
python3 -m eval.compare_results

# With the documented environment and vector stores configured:
python3 -m eval.run_all_scenarios
python3 -m orchestrator.test_critical_bypass
python3 -m eval.run_stress_tests
```

`compare_results` displays gold/actual comparisons and the designed review checks. It does not automatically grade every semantic check. The 5/5 and 15/15 results are the documented project evaluation, not a clinical accuracy claim; retrieval precision/recall was not numerically measured.

## Source tour

- [`agents/triage_agent.py`](agents/triage_agent.py): structured urgency classification and retrieval queries.
- [`agents/ehr_agent.py`](agents/ehr_agent.py): retrieval, output normalization and schema checks.
- [`agents/anamnesis_agent.py`](agents/anamnesis_agent.py): patient-reported evidence.
- [`agents/synthesis_agent.py`](agents/synthesis_agent.py): source-aware context brief.
- [`eval/run_stress_tests.py`](eval/run_stress_tests.py): targeted edge-case execution.

Course-project contributors listed in the evaluation report: Mhd Wael Abo Kalam, Marvan Ahmad, Talal Haneyeh and Karim S M Seyam.

More shipped product work: [TQEN](https://tqentech.com), [Crave It](https://craveitsyria.com), and [sanitized production architecture case studies](https://github.com/waelabokalam/production-systems-architecture).
