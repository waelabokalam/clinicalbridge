# ClinicalBridge — Demonstration

This document shows two complete end-to-end runs of ClinicalBridge, captured
directly from terminal output, fulfilling the capstone's required
demonstration of "at least two different clinical scenarios end-to-end"
(spec deliverable #6).

Each run was produced by:
```bash
python3 -m eval.run_single_scenario <scenario_id>
```

---

## Demonstration 1: Scenario S1 — The Missed Medication

**What this demonstrates:** the EHR Agent correctly reports it has no record
explaining a blood pressure spike, the Anamnesis Agent independently surfaces
that the patient quietly stopped her medication, and the Synthesis Agent
connects the two without blurring which source said what.

**Command:**
python3 -m eval.run_single_scenario S1_missed_medication

**OUTPUT**
(venv) waelabokalam@waels-MacBook-Air clinicalbridge_day1 % python3 -m eval.run_single_scenario S1_missed_medication
Running scenario: The Missed Medication (S1_missed_medication)

  [SynthesisAgent] attempt 1 failed (Error calling model 'gemini-2.5-flash-lite' (RESOURCE_EXHAUSTED): 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20, model: gemini-2.5-flash-lite\nPlease retry in 53.721296722s.', 'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.Help', 'links': [{'description': 'Learn more about Gemini API quotas', 'url': 'https://ai.google.dev/gemini-api/docs/rate-limits'}]}, {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': 'generativelanguage.googleapis.com/generate_content_free_tier_requests', 'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', 'quotaDimensions': {'location': 'global', 'model': 'gemini-2.5-flash-lite'}, 'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '53s'}]}}); retrying in 3s...

Status: completed
Confidence: high

--- Contextual Analysis ---
The RPM alert on 2026-06-15 shows a blood pressure of 178/104 mmHg (RPM Alert). The EHR indicates the patient was initiated on Lisinopril 20mg daily on 2025-05-11 for hypertension and was noted to be tolerating it well, with a subsequent clinic BP reading of 132/84 mmHg on 2026-04-16 indicating good control (EHR). However, anamnesis data reveals the patient self-reported discontinuing Lisinopril approximately 3 weeks prior to the alert due to a persistent dry cough that began about a month ago and was resolving around 10 days ago (Anamnesis). The patient self-reports only 40% adherence to Lisinopril recently and admitted to not informing the clinic of the discontinuation, stating 'didn't think it was a big deal' (Anamnesis). The EHR has no documentation of medication changes or discontinuation (EHR). The timeline of self-discontinuation of Lisinopril, reported by the patient, aligns with the period preceding the elevated BP readings, suggesting a potential link between non-adherence and the current BP elevation. This causal inference is made by the Synthesis Agent based on combining anamnesis and EHR data.

Saved to: /Users/waelabokalam/Downloads/clinicalbridge_day1/eval/results/S1_missed_medication_result.json

---

## Demonstration 2: Scenario S5 — The Conflicting Data

**What this demonstrates:** the system surfaces a direct contradiction
between patient-reported medication adherence and objective lab evidence,
without resolving the conflict itself or using accusatory language.

**Command:**
python3 -m eval.run_single_scenario S5_conflicting_data

**OUTPUT**
venv) waelabokalam@waels-MacBook-Air clinicalbridge_day1 % python3 -m eval.run_single_scenario S5_conflicting_data
Running scenario: The Conflicting Data (S5_conflicting_data)

  [SynthesisAgent] attempt 1 failed (503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.', 'status': 'UNAVAILABLE'}}); retrying in 3s...

Status: completed
Confidence: medium

--- Contextual Analysis ---
The current alert indicates a sustained blood pressure of 163/98 mmHg, which is above the patient's baseline threshold of 140/90 mmHg (Triage). The patient has a history of Essential Hypertension and Chronic Kidney Disease Stage 2 (EHR). The EHR notes from a 2026-05-26 Nephrology follow-up indicate that BP 'remains elevated despite reported adherence to dual agent regimen' and that a urine drug screen suggested sub-therapeutic Losartan levels (EHR). The patient self-reports 100% adherence to both Amlodipine and Losartan, taking them every day, and expresses frustration that their blood pressure remains high despite 'doing everything right' (Anamnesis). The anamnesis record explicitly notes this self-report conflicts with the sub-therapeutic urine drug screen result in the EHR (Anamnesis). The patient denies experiencing chest pain, vision changes, or headache (Anamnesis). Lifestyle factors reported include recently starting a physically demanding new job and experiencing high stress associated with it (Anamnesis). The patient's father had chronic kidney disease (Anamnesis).

Saved to: /Users/waelabokalam/Downloads/clinicalbridge_day1/eval/results/S5_conflicting_data_result.json
