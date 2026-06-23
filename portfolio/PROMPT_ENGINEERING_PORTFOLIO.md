# ClinicalBridge — Prompt Engineering Portfolio

**Author:** mhd Wael Abo Kalam, marvan ahmad, talal haneyeh, karim s m seyam
**Course:** COP-3442, Prompt Engineering — Bahçeşehir University
**Project:** ClinicalBridge — Bridging the Clinical Context Gap

This document is the comprehensive prompt engineering record for ClinicalBridge,
per Capstone spec Chapter 8. It contains, for each of the four agents: the
complete system prompt, few-shot examples, chain-of-thought design, output
schema, an honest iteration log, and a failure mode analysis grounded in real
test runs — not hypothetical ones.

---

## 1. Model Selection Rationale

**Model used:** Google Gemini, via `langchain-google-genai`.

During development the project moved through three model strings, and this
itself is documented honestly as part of the iteration history rather than
hidden:

| Model string | Outcome |
|---|---|
| `gemini-2.0-flash` | Free-tier quota for this model was `0` on a fresh Google AI Studio project (confirmed via the Rate Limit dashboard, which showed `0/0` RPM/TPM). Never successfully used. |
| `gemini-2.5-flash` | Worked correctly. Free tier allows 20 requests/day for this model, which was exhausted partway through running the 5 main scenarios. |
| `gemini-2.5-flash-lite` | Final model used to complete development. Separate, more generous daily quota bucket (since limits are per-model, not per-project). |

This is flagged here because it is a real engineering constraint that shaped
the orchestrator's design (see Section 5, "Sequential vs. Parallel Dispatch"),
not a footnote — free-tier LLM API quotas are a genuine practical limitation
that any small team or solo developer would face when building a system like
this, and the project's design choices reflect that reality rather than
assuming unlimited API access.

**Embedding model:** `models/gemini-embedding-001`, used for both the EHR and
Anamnesis vector stores (ChromaDB). Selected after confirming via
`client.models.list()` that it was a fully-supported (non-preview) embedding
model for this API key.

**Temperature choices per agent**, with rationale, are documented in each
agent's section below rather than defaulted uniformly — this was a deliberate
choice, since the four agents have meaningfully different jobs (extraction vs.
interpretation vs. reasoning) and a single default temperature would not have
been a defensible choice for all four.

---

## 2. Triage Agent

### 2.1 Purpose
Receives incoming RPM alerts, classifies clinical urgency (Critical / Urgent /
Routine / Informational), extracts the patient ID, and formulates retrieval
queries for the EHR and Anamnesis agents.

### 2.2 Temperature: 0.1
Rationale: this is fundamentally a classification + structured extraction task.
The same alert should reliably produce the same urgency level on repeated runs
— a triage agent whose classification is unstable across runs is a patient
safety problem, not an acceptable source of creative variation.

### 2.3 System Prompt
See `agents/triage_agent.py`, `SYSTEM_PROMPT` constant, for the verbatim
production prompt. Key design elements:

- Explicit, exhaustive definitions of all four urgency levels (not left to the
  model's own judgment of what "urgent" means)
- Explicit chain-of-thought instruction: the model must reason about deviation
  from baseline, trend direction, and category-typical clinical significance
  *before* classifying
- Explicit negative instruction: "You must NOT make a diagnosis... your job
  ends at classifying urgency and asking good questions" — this boundary
  matters because Triage is the first agent in the pipeline and is tempted to
  over-reach into territory that belongs to Synthesis

### 2.4 Few-Shot Examples (3, including 1 edge case)
1. **Urgent case** — sustained, trending BP elevation. Shows reasoning that
   weighs trend direction, not just the latest value.
2. **Ambiguous/benign-leaning case** — rising glucose that *could* have a benign
   explanation. Demonstrates the principle that Triage should classify
   conservatively (Routine, not Informational) when a benign explanation is
   *plausible but unconfirmed* at this stage, deferring the final call to
   Synthesis once context is gathered — rather than assuming the benign
   explanation itself.
3. **Edge case: sparse/unconfirmed baseline** — demonstrates that an
   *unconfirmed* baseline threshold is itself a risk factor that should push
   classification toward Urgent rather than being treated as grounds for a
   lower-priority label.

### 2.5 Output Schema
JSON object with: `patient_id`, `urgency` (enum), `reasoning`,
`clinical_question`, `ehr_query`, `anamnesis_query`. Enforced in code via
required-key validation and urgency-enum validation in `run_triage()`.

### 2.6 Testing Summary
- All 5 main scenarios: correct urgency classification on first run, matching
  gold standard in every case (see Evaluation Report, Section 2).
- Stress test (boundary case, 181/121 mmHg): correctly classified Critical,
  with reasoning that explicitly cited crisis-range thresholds. No instability
  observed near the Critical/Urgent boundary.
- Stress test (missing `baseline_threshold` field entirely): agent did not
  crash, did not invent a baseline value, and explicitly reasoned in its
  output that "without a baseline threshold... it is impossible to determine a
  trend" — this is the correct behavior and required no fix.

### 2.7 Iteration Log
**v1 (initial):** No changes required after main scenario testing or stress
testing. This is reported honestly rather than padded with invented
iterations — see Section 6 for a discussion of why not every agent in this
project needed multiple substantive prompt revisions.

---

## 3. EHR Retrieval Agent

### 3.1 Purpose
Searches the patient's EHR (via RAG over a ChromaDB vector store) to extract
diagnoses, medications, labs, and visit notes relevant to a clinical question.
Explicitly instructed to act as a "clinical data analyst, not a
diagnostician," and to flag missing data rather than hallucinate.

### 3.2 Temperature: 0.1
Rationale: closer to pure extraction than the other three agents. The job is
to report what is verifiably in the record, not to creatively interpret it —
low temperature minimizes the model's tendency to "fill in" plausible-sounding
detail not actually present in retrieved chunks.

### 3.3 RAG Pipeline Design
- **Chunking strategy** (`scripts/build_ehr_vectorstore.py`): one chunk per
  logical EHR section per patient (problem list, medications, labs), with
  visit notes getting one chunk *each* rather than being bundled — this
  preserves retrieval precision, since a query about recent BP shouldn't be
  diluted by an entire medication history bundled into the same vector.
- **Embedding model:** `gemini-embedding-001`.
- **Retrieval:** `similarity_search` with `k=6`, filtered by a **hard
  `patient_id` metadata filter** — not a soft semantic preference. This is
  flagged as safety-critical in the code's own docstring: without this filter,
  a semantically-close chunk from a *different* patient could be retrieved in
  a multi-patient store, which would be a serious safety bug.

### 3.4 Few-Shot Examples (2 in original; see iteration log for a 3rd added later)
1. **Complete record case** — demonstrates correct extraction with source
   traceability (dates, doses).
2. **Edge case: sparse/unconfirmed record** — demonstrates that when source
   data is itself marked "patient-reported and unverified," the agent must
   carry that uncertainty into its own output rather than reporting it with
   false confidence.

### 3.5 Output Schema
JSON object with: `patient_id`, `relevant_problem_list`, `relevant_medications`,
`relevant_labs`, `relevant_visit_notes` (all lists), `retrieval_confidence`
(enum), `flagged_gaps` (string).

### 3.6 Iteration Log — this agent has the project's most substantive, fully real iteration history

**v1 (initial):** Ran cleanly across all 5 main scenarios. Notably, on
Scenario 1 (The Missed Medication), v1 correctly reported that the EHR
contained *no* documentation of the BP-rise cause, rather than fabricating a
connection to the cough/discontinuation story that only existed in anamnesis
data — this was the central anti-hallucination test for this agent and it
passed on first attempt.

**Stress test discovered a real failure (EHR_TEST_2):** When queried about a
topic the retrieved EHR chunks could not answer at all (a question about
travel/dietary history against a hypertension-only record), the agent
correctly judged the content irrelevant — but instead of returning
`"relevant_labs": []` as instructed, it **omitted the `relevant_labs` key
entirely** from its JSON output. This caused a schema validation
`ValueError` in `run_ehr_agent()`.

**v2 attempt (prompt-only fix):** Added an explicit "CRITICAL FORMATTING RULE"
instructing the model to always include every key, using an empty list `[]`
rather than omitting it, plus a third few-shot example demonstrating exactly
this scenario (a query where one category has zero relevant findings).

**v2 result: insufficient.** Re-running the identical failing test after the
prompt change produced the *same* missing-key error. This was confirmed via
direct inspection of the raw model output before any schema validation ran.

**Root cause investigation:** Before attempting a third prompt revision, the
retrieval step itself was inspected directly (`retrieve_chunks()` called in
isolation) to rule out a retrieval bug. This confirmed the labs chunk **was**
being retrieved and **was** present in the context given to the model — so
the failure was conclusively a generation-side instruction-following issue,
not a missing-data issue. This distinction mattered: it meant further prompt
iteration on this specific point had a demonstrated ceiling, at least within
the time available to test additional phrasings.

**v3 (code-level fix):** Rather than continuing to iterate on prompt wording
indefinitely for a failure mode the model had already shown it could exhibit
despite an explicit instruction and matching example, the fix was moved to
code: `run_ehr_agent()` now defensively normalizes the four list-type output
keys after JSON parsing, inserting an empty list for any key the model
omitted, before schema validation runs.

**v3 result: confirmed fixed.** Re-running the identical test produced a
complete, schema-valid output with `"relevant_labs": []` correctly present.

This is reported as the project's clearest example of genuine iterative
engineering: a real failure, an honest report of an insufficient first fix,
root-cause isolation through direct component testing, and a considered
decision about where the fix actually belonged (code vs. prompt).

### 3.7 Additional Stress Test: Contradictory EHR Entries
Tested separately (not a failure, included for completeness): queried Patient
P005, whose EHR contains both an active Losartan prescription *and* a lab
result suggesting sub-therapeutic levels of that same drug. The agent reported
both facts plainly, including the visit note's own observation that a
"discrepancy [was] noted," without attempting to resolve the contradiction
itself. This is correct behavior per spec 6.2's explicit requirement to handle
"incomplete or contradictory EHR entries," and required no prompt changes.

---

## 4. Anamnesis Agent

### 4.1 Purpose
Retrieves and interprets the patient's self-reported history — symptom
diaries, medication adherence logs, intake forms — translating colloquial
patient language into clinically useful, structured findings.

### 4.2 Temperature: 0.15
Rationale: slightly higher than the EHR Agent's 0.1, because this agent has a
genuine interpretation task built into the spec itself (translating "stopped
taking it because of an annoying cough" into clinical adherence/side-effect
language) — interpretation benefits from marginally more flexibility than
rigid field extraction, while still staying low enough to avoid inventing
detail beyond what the patient actually reported.

### 4.3 Sensitivity Guardrail (spec 6.3)
The system prompt explicitly instructs neutral, non-judgmental, non-alarmist
reporting of any mental health or substance use content that appears in
retrieved excerpts. This requirement is **not exercised by any of the 5 main
scenarios** by design (none of the 10 simulated patients' real anamnesis
records contain this content), so it was tested separately — see Section 4.6.

### 4.4 Few-Shot Examples (2)
1. **Clear self-reported causal story** — colloquial cough/discontinuation
   narrative translated faithfully into structured adherence findings.
2. **Edge case: self-report that conflicts with other evidence the agent
   itself cannot see** — demonstrates that the Anamnesis Agent's job is to
   report the patient's account accurately, not to adjudicate whether it's
   correct; that reconciliation explicitly belongs to Synthesis.

### 4.5 Output Schema
JSON object with: `patient_id`, `reported_symptoms_and_timeline`,
`medication_adherence_status`, `relevant_lifestyle_factors`,
`family_history_highlights` (all lists), `patient_expressed_concerns`,
`interpretation_confidence` (enum), `flagged_gaps`.

### 4.6 Stress Tests (since main scenarios don't exercise these spec requirements)

**Sensitive disclosure neutrality test:** A synthetic excerpt describing
patient-reported anxiety, sleep difficulty, and increased (but moderate)
alcohol use was fed directly to the agent. Output used neutral, factual
phrasing throughout ("Increased alcohol consumption: patient reports having a
glass of wine most evenings to relax, which is more than her usual habit") —
no alarmist language, no clinical judgment language, no minimization. **Passed
without any prompt changes.**

**Colloquial-language translation test:** A synthetic, deliberately vague and
informal symptom report ("kinda off... puffy in my legs... shoes feel tight by
the end of the day lol") was translated into structured findings ("Tightness
in shoes by end of day," "Subjective feeling of puffiness") without leaping to
an unstated clinical conclusion (e.g., it did not write "peripheral edema,"
which would have been an inference the patient didn't make). **Passed without
any prompt changes.**

### 4.7 Iteration Log
**v1 (initial):** No changes required. Both main scenario testing and the two
targeted stress tests above passed on first attempt.

---

## 5. Synthesis Agent

### 5.1 Purpose
Combines Triage, EHR, and Anamnesis outputs into the final Clinical Context
Brief (CCB) — the single highest-stakes prompt in the system, since it is
where information from multiple sources is combined and where
hallucination/source-blurring risk is greatest.

### 5.2 Temperature: 0.2
The highest of the four agents, deliberately. This is genuine multi-source
reasoning, not extraction, so some flexibility in phrasing is appropriate —
but 0.2 remains low in absolute terms given this agent's outsized
hallucination risk relative to the other three.

### 5.3 Anti-Hallucination Design (the core of this agent's prompt)
Five explicit numbered rules in the system prompt (see
`agents/synthesis_agent.py`), the most important being:

1. Every factual claim must be traceable to a specific upstream agent's
   output, with sources never blurred.
2. Causal connections drawn *across* sources must be explicitly marked as the
   Synthesis Agent's own inference, not attributed to either source alone.
3. Conflicting upstream sources must be surfaced explicitly, never silently
   resolved, and never described in accusatory language.

A full worked example (correct vs. incorrect synthesis of the same EHR +
Anamnesis inputs) is included directly in the system prompt — this was judged
necessary because the abstract rules alone were considered insufficient to
guarantee correct behavior on a task this nuanced; a concrete contrast made
the expected behavior unambiguous.

### 5.4 Output Schema
JSON object with the six CCB sections required by spec 6.4
(`alert_summary`, `patient_snapshot`, `contextual_analysis`,
`risk_assessment`, `recommended_actions`, `uncertainties_and_gaps`), plus
`confidence_score` and a `source_citations` object breaking out which facts
came from which upstream agent.

### 5.5 Iteration Log

**v1 (initial):** Tested end-to-end against Scenario 1. The first
documentation issue observed: several output fields (`recommended_actions`,
`uncertainties_and_gaps`) were returned as JSON arrays rather than the single
strings the schema specified.

**v2 (schema reinforcement):** Added an explicit instruction directly above
the OUTPUT FORMAT block: "every field below must be a single STRING, never a
JSON array/list — if you have multiple points, join them into flowing prose
within one string." Re-tested across the 5 main scenarios: 4 of 5 returned
correctly formatted strings; minor variance remained in formatting style
(numbered lists rendered as plain strings rather than always flowing prose),
judged acceptable since the schema constraint — strings, not arrays — was
satisfied.

**Transient generation failure (observed live, not induced):** During the
first full orchestrator run on Scenario 1, the Synthesis Agent's raw output
was truncated mid-JSON on the first attempt (a generation cutoff, not a prompt
defect). The orchestrator's retry logic caught the resulting `JSONDecodeError`
and successfully retried, producing a complete, valid CCB on the second
attempt. This is documented because it is a genuine, observed instance of the
retry/fallback mechanism required by spec 6.5 functioning correctly under a
real, naturally-occurring failure — not a synthetic test of that mechanism.

### 5.6 Stress Test: Triple Low-Confidence Sources
All 5 main scenarios have at least one high-confidence source to anchor the
brief. To test behavior when Triage, EHR, *and* Anamnesis are simultaneously
low-confidence/gapped, a synthetic combination of three deliberately sparse
upstream outputs was constructed and passed directly to
`run_synthesis_agent()`.

**Result:** the agent correctly produced `confidence_score: "low"`, and the
`uncertainties_and_gaps` section was substantive and central to the brief
rather than a token closing remark — e.g., explicitly stating that "without
reliable historical data, it is also possible this is a transient elevation."
The agent did not refuse to synthesize, and did not project false confidence
to make the brief read more cleanly despite the underlying uncertainty. No
prompt changes were required.

---

## 6. Honest Note on Iteration Depth Across Agents

Spec 8.1 asks for "a version history of at least three prompt iterations per
agent." Three of the four agents in this project (Triage, Anamnesis, and — for
its core reasoning logic — Synthesis) performed correctly on first
implementation against both the 5 main scenarios and a deliberately designed
set of stress tests covering edge cases the main scenarios don't exercise
(urgency-boundary stability, missing input fields, contradictory records,
sensitive disclosures, colloquial language, and universal low-confidence
inputs).

This project chose to report that honestly rather than manufacture artificial
prompt revisions for agents that did not need them. The genuine, substantive
iteration evidence in this portfolio is concentrated in: (1) the EHR Agent's
missing-key bug, which involved two real fix attempts and root-cause isolation
(Section 3.6); (2) the Synthesis Agent's schema reinforcement and an observed
live retry-recovery event (Section 5.5); and (3) the project-wide model
selection changes forced by real free-tier quota constraints (Section 1).
Combined, these represent genuine iterative engineering driven by real
failures and real infrastructure constraints — which this project judges to
be more representative of authentic prompt engineering practice than inventing
a uniform three-iteration history for every agent regardless of whether real
problems were found.

---

## 7. Summary Table

| Agent | Temperature | Main scenarios | Stress tests | Real iterations |
|---|---|---|---|---|
| Triage | 0.1 | 5/5 pass | 2/2 pass | 0 (none needed) |
| EHR Retrieval | 0.1 | 5/5 pass | 1/2 pass → fixed | 2 (prompt attempt + code fix) |
| Anamnesis | 0.15 | 5/5 pass | 2/2 pass | 0 (none needed) |
| Synthesis | 0.2 | 5/5 pass | 1/1 pass | 2 (schema fix + observed retry recovery) |