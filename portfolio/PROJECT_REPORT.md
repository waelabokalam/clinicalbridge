# ClinicalBridge — Project Report

**Bridging the Clinical Context Gap: An LLM-Powered Multi-Agent System for
Synthesizing Electronic Health Records, Remote Patient Monitoring, and
Anamnesis Data**

COP-3442: Prompt Engineering
Bahçeşehir University, Artificial Intelligence Engineering Department
Author: Wael Abo Kalam

*This document updates the original capstone definition document with actual
implementation details, results, and reflections, per Deliverable #1 in
Chapter 11 of the project specification.*

---

## 1. Executive Summary

ClinicalBridge was implemented as specified: a four-agent, LLM-powered
prototype, coordinated by a central orchestrator, that transforms a simulated
RPM alert into a structured Clinical Context Brief (CCB) by retrieving and
synthesizing the patient's EHR history and self-reported anamnesis data.

The system was built using LangChain for orchestration, Google's Gemini API
for all LLM calls, and ChromaDB for vector-based retrieval over both the EHR
and Anamnesis data sources. All four specialized agents (Triage, EHR
Retrieval, Anamnesis, Synthesis) and the Orchestrator were implemented
according to the role definitions in Chapter 6 of the original specification.

The implementation was tested against all 5 required clinical scenarios, plus
8 additional stress tests designed specifically to exercise spec requirements
the 5 main scenarios do not cover. All 5 scenarios passed their designed
failure-mode checks (15/15). The stress tests surfaced one genuine bug in the
EHR Agent, which was diagnosed, an initial fix attempt was tested and found
insufficient, the root cause was isolated through direct component testing,
and a working fix was implemented at the code level. The Critical-alert safety
escalation guardrail, never exercised by the 5 main scenarios since none of
them are Critical-urgency by design, was separately verified working via a
synthetic test.

One significant deviation from the original specification was required and is
reported honestly throughout this document: the EHR and Anamnesis retrieval
agents are dispatched **sequentially**, not in parallel as specified in
Section 4.2, due to a hard rate limit (5 requests/minute, later found to also
include a 20-requests/day cap on a specific model) on the free-tier Gemini API
key used for development. This tradeoff is discussed in full in Section 12.3.

---

## 2. Problem Statement: The Clinical Context Gap

*(Unchanged from the original specification — the problem statement,
background on EHR/RPM/Anamnesis fragmentation, and rationale for why this is
a prompt engineering problem were accepted as given and used directly to
drive system design. See the original capstone definition document, Chapter
2, for full text.)*

---

## 3. Project Objective and Scope

The implemented system matches the in-scope items specified in Section 3.2 of
the original document:

- Simulated EHR, RPM, and anamnesis datasets — implemented, 10 fictional
  patients, generated programmatically rather than hand-authored (see Section
  7 below for rationale).
- Multi-agent architecture with specialized agents — implemented as 4 agents
  + 1 orchestrator.
- Prompt engineering for each agent role — implemented; full detail in the
  companion Prompt Engineering Portfolio document.
- RAG pipeline for EHR context retrieval — implemented using ChromaDB; **this
  was extended beyond the minimum spec to also apply RAG to the Anamnesis
  data source**, since the project judged that anamnesis records (semi-structured,
  narrative, multiple entries per patient) benefited from the same
  chunk-and-retrieve approach as EHR records, rather than being passed to the
  Anamnesis Agent in full every time.
- Memory and tool integration for agents — the vector store retrieval tools
  (`retrieve_chunks()` in both the EHR and Anamnesis agents) constitute the
  primary tool integration in this implementation. Conversation/summary/entity
  memory across multiple alerts for the same patient (as might be relevant in
  a longer-running deployment) was not implemented, as the project scope was
  bounded to single-alert processing per the primary objective in Section 3.1.
- Evaluation framework with defined metrics — implemented; see the companion
  Evaluation Report.
- Prompt iteration portfolio with version history — implemented; see the
  companion Prompt Engineering Portfolio, including an honest discussion of
  which agents required genuine iteration versus which performed correctly
  from first implementation.

No out-of-scope items (real patient data, production deployment, FDA
compliance, real-time device integration, custom fine-tuning, full HL7/FHIR
interoperability, or frontend development) were attempted, consistent with
the original specification's scope boundaries.

---

## 4. Implemented Solution Architecture

The implemented architecture matches Section 4.1 of the original
specification exactly in terms of agent roles and responsibilities. The data
flow (Section 4.2) was implemented with one documented deviation:

**Specified:** "The Orchestrator dispatches queries to the EHR Retrieval
Agent and the Anamnesis Agent in parallel."

**Implemented:** The Orchestrator dispatches these two agents **sequentially**,
with a fixed delay between calls.

**Reason for deviation:** The free Gemini API tier used for this project
enforces a hard rate limit (initially observed as 5 requests/minute; later,
on a different model, an additional 20-requests/day cap was also
encountered). True parallel dispatch — two simultaneous API calls — risked
tripping this limit and causing a transient failure unrelated to the actual
correctness of the system's design. Sequential dispatch with a short delay
trades a small amount of added latency for reliability under this real
infrastructure constraint. This is the kind of tradeoff a production engineer
operating under a real API budget would recognize, and it is reported here
rather than silently diverging from the spec without explanation.

This deviation is also why end-to-end latency for a complete scenario run
(several minutes, including deliberate rate-limit-safety delays) significantly
exceeds the spec's 30-second target — see Section 12.3 and the companion
Evaluation Report, Section 5, for full discussion.

---

## 5. Module-to-Capstone Mapping (as implemented)

| Course Module | How it was actually applied |
|---|---|
| M1: Intro to LLMs & Prompt Engineering | Model selection was driven by real constraints, not just preference — see Section 9 below for the full story of testing `gemini-2.0-flash` (found to have zero free-tier quota), `gemini-2.5-flash` (worked, but daily quota exhausted mid-evaluation), and `gemini-2.5-flash-lite` (final working choice). |
| M2: Designing LLM Applications | Application architecture and agent I/O contracts implemented directly per Chapter 6's specifications; documented in code docstrings and the companion Portfolio document. |
| M3: Prompt Content & Assembling the Prompt | Full system prompts, few-shot examples (2-3 per agent, including edge cases), and output schemas implemented for all 4 agents; see Portfolio for verbatim prompts and rationale. |
| M4: Conversational Agency & LLM Workflows | Chain-of-thought reasoning is explicitly required in the Triage Agent's prompt (urgency classification must be justified before being stated) and the Synthesis Agent's prompt (causal inferences must be explicitly marked as the agent's own reasoning, not attributed to upstream sources). |
| M5: Testing LLM Applications | Implemented at two levels: the 5 designed gold-standard scenarios (written before any agent code existed), and 8 additional stress tests designed after initial implementation specifically to probe spec requirements the main scenarios don't exercise. See companion Evaluation Report. |
| M6: Advanced Techniques with LangChain | RAG implemented for both EHR and Anamnesis retrieval (extending beyond the spec's EHR-only RAG requirement). LangChain `ChatPromptTemplate` and chain composition (`prompt | llm`) used throughout. |
| M7: Autonomous Agents with Memory & Tools | Each retrieval agent's vector store query function constitutes its primary tool. Memory across multiple alerts for the same patient was not implemented (see Section 3, scope discussion). |
| M8: Multi-Agent System | Full orchestration implemented in `orchestrator/orchestrator.py`: sequential routing (deviation documented above), retry logic with exponential-ish backoff, fallback to explicit low-confidence placeholder outputs when an agent fails after retries, the Critical-alert safety bypass, and a structured session log for auditability. |

---

## 6. Detailed System Components (as implemented)

All four agents and the orchestrator were implemented matching the role,
input/output, and prompt engineering focus areas specified in Chapter 6 of
the original document. Verbatim prompts, few-shot examples, and output
schemas for each are documented in full in the companion **Prompt Engineering
Portfolio**, rather than duplicated here.

One implementation detail worth noting at the architecture level: both the
EHR and Anamnesis retrieval agents enforce a **hard metadata filter on
`patient_id`** during vector similarity search, not merely a semantic
preference. This was treated as a safety-critical design decision: in a
multi-patient vector store, a semantically-similar chunk belonging to a
*different* patient could otherwise be retrieved, which would be a serious
safety defect in a clinical context. This is documented directly in both
agents' source code.

---

## 7. Data Model and Simulated Dataset (as implemented)

10 fictional patients were generated — at the lower end of the spec's 10-20
patient range, by deliberate choice. Patients P001-P005 were each purpose-built
to drive one of the 5 required gold-standard scenarios; patients P006-P010
exist to give the vector stores realistic multi-patient volume, so that
retrieval (and the patient-ID filtering safety property described in Section
6) could be meaningfully tested against more than a trivial single-patient
store.

**Generation method:** the dataset was built programmatically
(`scripts/generate_dataset.py`, `scripts/patient_cohort.py`) rather than
hand-authored as raw JSON. This was a deliberate efficiency choice: it kept
dataset creation fast and consistent, while still allowing every clinically
important detail for each of the 5 scenario patients (medication timelines,
lab values, symptom onset dates) to be deliberately, explicitly authored
within the generator rather than left to random generation. The 5 background
patients (P006-P010) use generic, less detailed records, since their only
purpose is to populate the vector store, not to drive scenario logic.

### 7.1 Scenario Design

All 5 required scenarios were implemented exactly as specified in the
original document's Section 7.2 (The Missed Medication, The False Alarm, The
Silent Deterioration, The Incomplete Record, The Conflicting Data). For each,
a full gold-standard Clinical Context Brief was authored *before* any agent
code was written, along with an explicit list of 3 specific failure-mode
checks per scenario — concrete, falsifiable behaviors the system would need
to exhibit (or avoid) to be judged successful. This ordering (gold standards
first, implementation second) was a deliberate methodological choice intended
to prevent the common failure pattern of writing "gold standards" that
retroactively justify whatever the system happened to produce.

---

## 8. Prompt Engineering (summary; full detail in companion Portfolio)

Each of the 4 agents received a distinct system prompt, 2-3 few-shot examples
(including at least one edge case per agent), and explicit output schema
enforcement. Temperature was set deliberately per-agent rather than defaulted
uniformly: 0.1 for Triage and EHR Retrieval (extraction-heavy, consistency
prioritized), 0.15 for Anamnesis (genuine colloquial-to-clinical translation
task, slightly more flexibility warranted), and 0.2 for Synthesis (genuine
multi-source reasoning, but still kept low given this agent's outsized
hallucination risk).

The single most substantive, fully real iteration story in the project
involves the EHR Agent: a stress test surfaced a real schema-compliance bug
(an omitted JSON key under a specific query type), a first fix attempt via
prompt engineering was tested and **found insufficient**, the root cause was
isolated by directly inspecting the retrieval step in code (which confirmed
the failure was generation-side, not a retrieval/data-availability issue),
and the fix was ultimately implemented at the code level rather than through
further prompt iteration. This full story, including the failed first
attempt, is documented in the Portfolio rather than omitted — it is judged to
be more representative of genuine prompt engineering practice than a
uniformly successful iteration log would be.

---

## 9. Model Selection — A Real Constraint, Not Just a Choice

This section is included because it materially shaped implementation and is
worth reporting honestly rather than treated as an unremarkable footnote.

Three Gemini model strings were used over the course of development:

1. `gemini-2.0-flash` — never successfully used. The Google AI Studio Rate
   Limit dashboard confirmed this model had a `0/0` requests-per-minute and
   tokens-per-minute allocation on a freshly created free-tier project,
   despite the project itself being active and other models showing nonzero
   quotas.
2. `gemini-2.5-flash` — worked correctly for the bulk of development and
   testing. A previously-unknown (to the author) **daily** quota of 20
   requests/day for this specific model on the free tier was exhausted while
   running the 5th of 5 main scenarios.
3. `gemini-2.5-flash-lite` — switched to in order to complete the remaining
   work, since free-tier quotas are allocated per-model, not per-project,
   making this a separate available quota bucket.

This experience directly informed the orchestrator's sequential-dispatch
design (Section 4) and is reported as a genuine engineering constraint
encountered during the project, not a hypothetical consideration.

---

## 10. Evaluation Results (summary; full detail in companion Evaluation Report)

- **5/5 main scenarios** produced a completed Clinical Context Brief matching
  gold-standard urgency classification, and **15/15** specific, pre-defined
  failure-mode checks passed.
- **8 stress tests**, designed after initial implementation to probe spec
  requirements the 5 main scenarios don't exercise (urgency-boundary
  stability, missing input fields, EHR-internal contradictions, sensitive
  mental-health/substance-use disclosures, heavily colloquial patient
  language, and universal low-confidence synthesis): 7 passed without any
  change required; 1 surfaced the real bug discussed in Section 8.
- The **Critical-alert safety escalation guardrail**, never exercised by any
  of the 5 main scenarios (none are Critical-urgency by design), was verified
  working via a dedicated synthetic test using a true hypertensive-crisis-range
  alert (205/128 mmHg). The orchestrator correctly bypassed EHR retrieval,
  Anamnesis retrieval, and Synthesis entirely upon detecting Critical
  classification, confirmed by the session log showing only a single API call
  (Triage) for that run.

---

## 11. Reflective Analysis

The most valuable finding from this project was not that the system worked —
it largely did, on first implementation, across both the designed scenarios
and a deliberately adversarial set of stress tests. The most valuable finding
was the **one place it didn't**, and what that revealed: a model that had
already been given an explicit instruction and a matching worked example
still failed to follow that instruction consistently under a specific input
condition. This is a genuinely useful, concrete lesson in the limits of
prompt-only correctness guarantees, and in when a defensive code-level fix is
the more reliable engineering choice than continued prompt iteration. That
lesson would not have surfaced from the 5 main scenarios alone — it only
appeared once edge cases were deliberately constructed specifically to find
weaknesses the main scenarios were not designed to probe.

A second reflection concerns the project's relationship to real-world
infrastructure constraints. The original specification's "parallel
dispatch" design is sound in an environment with generous API quotas; under
the free-tier constraints actually encountered, sequential dispatch with
explicit rate-limit-safety delays was the more reliable choice, even at a
real latency cost. Documenting this tradeoff explicitly, rather than quietly
deviating from the spec or pretending the parallel design was implemented
when it wasn't, was treated as itself part of the engineering discipline this
project was meant to develop.

---

## 12. Ethical Considerations and Limitations

### 12.1 Critical Disclaimers (unchanged from original spec, restated for completeness)

- **Not a clinical tool.** This is an educational prototype and must never be
  used for actual clinical decision-making.
- **No real patient data.** All data in this project — all 10 patients, all
  EHR/RPM/anamnesis records — is entirely fictional and was generated
  programmatically for this project. No real or de-identified patient data of
  any kind was used at any stage.
- **No diagnostic claims.** Every agent's prompt explicitly instructs against
  making a diagnosis. All outputs are framed as contextual summaries intended
  to support, not replace, clinical judgment.

### 12.2 Ethical Design Principles, as Implemented

- **Transparency:** every Clinical Context Brief includes a confidence score
  and a `source_citations` breakdown of which specific facts came from which
  upstream agent. This was verified in practice, not just specified — the
  Synthesis Agent's prompt includes an explicit worked example contrasting
  correct vs. incorrect source attribution, and testing confirmed source
  attribution remained accurate and unblurred across all 5 scenarios and the
  relevant stress test.
- **Human-in-the-loop:** every agent's prompt explicitly forbids diagnostic
  claims and frames output as decision *support*. No component of the system
  takes or recommends an automated action; every recommended action is
  explicitly framed for clinician review.
- **Bias awareness:** the simulated dataset's demographic composition (ages
  48-75, mixed sex, single set of chronic conditions per the spec's named
  conditions) is narrow and was not designed with bias analysis as a primary
  goal; a real deployment would need a far more demographically and
  clinically diverse dataset to make any claim about equitable performance
  across patient populations. This is reported as a known gap rather than
  implied to have been addressed.
- **Safety guardrails:** the Critical-alert bypass was implemented and
  separately verified working (Section 10), satisfying the "fail safe, escalate
  rather than automate" principle from the original specification.

### 12.3 Known Limitations (expanded with real findings from this implementation)

- **Sequential, not parallel, agent dispatch**, due to free-tier API rate
  limits — see Section 4 and Section 9. This is the most significant
  architectural deviation from the original specification and the primary
  reason end-to-end latency exceeds the spec's 30-second target.
- **No numeric retrieval precision/recall was computed** against spec 9.1's
  targets; only qualitative review was performed, for reasons of project
  timeline. See companion Evaluation Report, Section 5, for full discussion.
- **Small sample size:** 10 patients, 5 main scenarios, 8 stress tests. This
  is enough to demonstrate the architecture works and to surface at least one
  genuine, non-trivial failure mode, but is not a statistically powered
  evaluation.
- **Single-evaluator grading:** all pass/fail judgments in the Evaluation
  Report were made by the same person who authored the gold standards being
  evaluated against. This is the exact limitation the original specification
  itself anticipates in Section 9.3 ("the evaluation framework relies on your
  own gold standards, which may themselves contain errors or biases").
- **LLM hallucination risk remains non-zero.** While no hallucinated clinical
  facts were identified across the 13 reviewed outputs in this project's
  testing, this is a sample-based finding, not a guarantee, and any real
  deployment would require substantially more extensive evaluation before
  any claim of negligible hallucination risk could be responsibly made.
- **Multi-agent coordination failure modes were only partially tested.** The
  retry/fallback logic was exercised by one naturally-occurring transient
  failure (a Synthesis Agent output truncation, recovered automatically by
  the orchestrator's retry logic) and was not separately stress-tested for
  every possible agent-failure combination (e.g., what happens if both EHR
  and Anamnesis fail simultaneously after exhausting retries — this specific
  combination was not tested).

---

## 13. References

*(Unchanged from the original specification — see the original capstone
definition document, Chapter 13, for the complete bibliography. No additional
sources were identified or cited during implementation beyond those already
provided.)*