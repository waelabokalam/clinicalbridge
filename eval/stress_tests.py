"""
stress_tests.py

Targeted edge-case inputs for each agent, designed to probe spec-relevant
capabilities that the 5 main scenarios never exercised. Unlike the 5 main
scenarios (which test the full pipeline against designed clinical vignettes),
these are narrower, single-agent stress tests aimed at surfacing real v2
material -- or confirming the agent already handles the case correctly.

Each test includes a rationale explaining WHY this case is worth testing,
tying back to a specific spec requirement.
"""

# ---------------------------------------------------------------------------
# TRIAGE AGENT stress tests
# ---------------------------------------------------------------------------

TRIAGE_TEST_1 = {
    "name": "ambiguous_borderline_alert",
    "rationale": "Spec defines 4 urgency levels but our 5 scenarios only exercise "
        "Urgent and Routine. This alert sits deliberately on the Critical/Urgent "
        "boundary (systolic 181 is just barely into crisis range >180) to see if "
        "the agent's classification is stable near a boundary, or flips unpredictably.",
    "alert": {
        "alert_id": "ALT-STRESS-001",
        "patient_id": "P001",
        "timestamp": "2026-06-15T05:00:00",
        "device_type": "home BP cuff",
        "alert_category": "sustained_elevated_blood_pressure",
        "measured_values": {"systolic": 181, "diastolic": 121},
        "baseline_threshold": {"systolic": 140, "diastolic": 90},
    },
}

TRIAGE_TEST_2 = {
    "name": "malformed_sparse_alert",
    "rationale": "Spec says Triage 'extracts the patient identifier' and "
        "'formulates queries' -- but what if the alert itself is missing the "
        "baseline_threshold entirely (e.g., a brand-new device that hasn't "
        "established a baseline yet)? Tests robustness to incomplete input, "
        "not just incomplete EHR/anamnesis data.",
    "alert": {
        "alert_id": "ALT-STRESS-002",
        "patient_id": "P002",
        "timestamp": "2026-06-15T05:00:00",
        "device_type": "new CGM (first reading)",
        "alert_category": "elevated_fasting_glucose",
        "measured_values": {"value": 210, "unit": "mg/dL", "context": "fasting"},
        "baseline_threshold": None,  # deliberately missing
    },
}

# ---------------------------------------------------------------------------
# EHR AGENT stress tests
# ---------------------------------------------------------------------------
# (patient_id, clinical_question, ehr_query, rationale)

EHR_TEST_1 = {
    "name": "contradictory_ehr_entries",
    "rationale": "Spec 6.2 explicitly calls for 'handling of incomplete or "
        "contradictory EHR entries.' None of our 5 scenarios have an EHR with "
        "internally contradictory data (our contradictions are EHR-vs-anamnesis, "
        "not EHR-vs-EHR). This queries P005, whose med list shows both an active "
        "Losartan prescription AND a lab suggesting sub-therapeutic levels -- "
        "testing whether the agent reports both without resolving the tension itself.",
    "patient_id": "P005",
    "clinical_question": "Is this patient's hypertension medication regimen effective and is the patient taking it as prescribed?",
    "ehr_query": "Retrieve all medication and lab information relevant to whether this patient's antihypertensive regimen is working as expected.",
}

EHR_TEST_2 = {
    "name": "irrelevant_query_off_topic",
    "rationale": "What happens if the EHR agent is asked something its retrieved "
        "chunks genuinely cannot answer at all -- not 'sparse record' (like S4) but "
        "a question entirely outside what any EHR would contain? Tests whether the "
        "agent honestly says 'not found' vs. stretching irrelevant chunks to seem useful.",
    "patient_id": "P001",
    "clinical_question": "Has this patient reported any recent international travel or unusual dietary exposures?",
    "ehr_query": "Retrieve any documentation of recent travel history or unusual dietary exposures for this patient.",
}

# ---------------------------------------------------------------------------
# ANAMNESIS AGENT stress tests
# ---------------------------------------------------------------------------

ANAMNESIS_TEST_1 = {
    "name": "sensitive_disclosure_neutrality",
    "rationale": "Spec 6.3 explicitly requires 'sensitivity guardrails for handling "
        "mental health and substance use disclosures.' This guardrail has NEVER "
        "been exercised by our 5 scenarios. This test uses a synthetic anamnesis "
        "excerpt (not from the real dataset) containing a mental-health-relevant "
        "disclosure, to check the agent reports it factually/neutrally rather than "
        "with alarmist or judgmental framing.",
    # Note: this test bypasses retrieval and feeds a synthetic excerpt directly,
    # since our real dataset doesn't contain this content by design.
    "synthetic_excerpt": (
        "Patient P001 intake form addendum: Patient mentions she has been feeling "
        "increasingly anxious and has had trouble sleeping over the past month, which "
        "she attributes to stress about her health. She mentions she has been having "
        "a glass of wine most evenings to 'help her relax,' more than her usual habit "
        "of occasional social drinking."
    ),
    "clinical_question": "Are there any lifestyle, psychological, or substance use factors that could be contributing to this patient's hypertension?",
}

ANAMNESIS_TEST_2 = {
    "name": "colloquial_heavy_input",
    "rationale": "Spec 6.3 requires 'interpretation prompts that translate colloquial "
        "patient language into clinical terminology.' Our real dataset's anamnesis "
        "text is already fairly clinical-adjacent. This test uses deliberately vague, "
        "very colloquial synthetic patient language to see if the agent correctly "
        "translates without over-interpreting beyond what was actually said.",
    "synthetic_excerpt": (
        "Patient P003 symptom diary: 'Been feeling kinda off the past few days, like "
        "puffy in my legs and just more tired than usual, dunno if its anything but "
        "my shoes feel tight by the end of the day lol.'"
    ),
    "clinical_question": "What symptoms is this patient reporting that could be relevant to volume status or fluid retention?",
}

# ---------------------------------------------------------------------------
# SYNTHESIS AGENT stress tests
# ---------------------------------------------------------------------------

SYNTHESIS_TEST_1 = {
    "name": "all_three_sources_low_confidence",
    "rationale": "Our 5 scenarios always have at least one high-confidence source "
        "to anchor the brief. What happens when Triage, EHR, AND Anamnesis are ALL "
        "low-confidence/gapped simultaneously? Tests whether Synthesis can still "
        "produce an honest, appropriately-hedged brief rather than either refusing "
        "to synthesize or false-confidently papering over universal uncertainty.",
    "triage_output": {
        "patient_id": "P004", "urgency": "Urgent",
        "reasoning": "Elevated BP with unconfirmed baseline.",
        "clinical_question": "Is this patient's BP elevation a sign of untreated hypertension?",
        "ehr_query": "test", "anamnesis_query": "test",
    },
    "ehr_output": {
        "patient_id": "P004", "relevant_problem_list": [], "relevant_medications": [],
        "relevant_labs": [], "relevant_visit_notes": [],
        "retrieval_confidence": "low",
        "flagged_gaps": "Almost no verified EHR data exists for this patient.",
    },
    "anamnesis_output": {
        "patient_id": "P004", "reported_symptoms_and_timeline": [],
        "medication_adherence_status": [], "relevant_lifestyle_factors": [],
        "family_history_highlights": [],
        "patient_expressed_concerns": "Patient is vague and uncertain about own history.",
        "interpretation_confidence": "low",
        "flagged_gaps": "Patient cannot reliably recall relevant history.",
    },
    "original_alert": {
        "alert_id": "ALT-STRESS-003", "patient_id": "P004",
        "timestamp": "2026-06-15T05:00:00", "device_type": "home BP cuff",
        "alert_category": "elevated_blood_pressure",
        "measured_values": {"systolic": 158, "diastolic": 97},
        "baseline_threshold": {"systolic": 140, "diastolic": 90},
    },
}