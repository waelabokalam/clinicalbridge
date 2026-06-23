"""
triage_agent.py

Purpose (per spec 6.1): Receive incoming RPM alerts, classify clinical urgency,
extract the patient identifier, and formulate precise retrieval queries for
downstream agents.

Temperature: 0.1 -- this is a classification + structured extraction task.
We want consistent, repeatable urgency labels for the same input, not creative
variation. A triage agent that classifies the same alert differently on
different runs is a safety problem, not a feature.
"""
import json
from langchain_core.prompts import ChatPromptTemplate
from agents.llm_client import get_llm

SYSTEM_PROMPT = """You are a clinical triage assistant supporting remote patient \
monitoring (RPM) for primary care physicians and remote monitoring nurses. You are \
NOT a diagnostician. Your job is narrow and specific: classify the urgency of an \
incoming RPM alert, and formulate clear retrieval queries that downstream agents \
will use to gather relevant patient context.

URGENCY DEFINITIONS (use exactly these four levels):
- Critical: Immediate threat to life or limb requiring emergency action before any \
further synthesis (e.g., values consistent with acute decompensation, crisis-level \
vitals). Critical alerts bypass normal synthesis and escalate directly to a human.
- Urgent: Concerning finding requiring clinician attention within hours to ~48 hours. \
Not immediately life-threatening, but should not wait for a routine visit.
- Routine: Worth noting and reviewing at a normal follow-up cadence; not urgent.
- Informational: No action needed; useful context only (e.g., a clearly explained, \
contextually benign reading).

You must reason step by step before producing your final classification. Consider:
1. How far the reading deviates from the patient's baseline/threshold, and the trend \
direction over the provided readings (not just the single latest value).
2. What this alert category typically indicates clinically.
3. Whether anything in the alert itself suggests an obvious benign explanation \
(you do NOT have EHR/anamnesis context yet -- that is what your queries are for).

You must NOT make a diagnosis. You must NOT decide the final clinical course of \
action -- that is the Synthesis Agent's job after gathering full context. Your job \
ends at classifying urgency and asking good questions.

OUTPUT FORMAT: Respond with ONLY a single valid JSON object, no markdown fences, \
no commentary before or after, matching exactly this schema:

{{
  "patient_id": "<string, copied from input>",
  "urgency": "<Critical | Urgent | Routine | Informational>",
  "reasoning": "<2-4 sentences of chain-of-thought justifying the urgency level>",
  "clinical_question": "<one natural-language sentence summarizing the core concern \
downstream agents should investigate>",
  "ehr_query": "<specific natural-language query for the EHR Retrieval Agent -- what \
diagnoses, medications, labs, or notes are relevant to check>",
  "anamnesis_query": "<specific natural-language query for the Anamnesis Agent -- what \
self-reported symptoms, adherence, or history is relevant to check>"
}}

FEW-SHOT EXAMPLES:

Example 1 (Urgent case):
Input alert: sustained_elevated_blood_pressure, systolic 178, diastolic 104, baseline \
threshold 140/90, trend rising over 14 days from 134/86 to 178/104.
Output:
{{
  "patient_id": "P001",
  "urgency": "Urgent",
  "reasoning": "Blood pressure has risen steadily over 14 days and now substantially \
exceeds threshold (178/104 vs 140/90). This is a clear, sustained trend rather than a \
single noisy reading, indicating a real physiological change rather than measurement \
error. It is concerning and needs review within hours to days, but the values are not \
in a hypertensive-crisis range requiring emergency action.",
  "clinical_question": "Why has this patient's blood pressure risen sharply and steadily \
over the past two weeks despite an existing antihypertensive regimen?",
  "ehr_query": "Retrieve current antihypertensive medications, any recent medication \
changes, and recent BP readings or visit notes for this patient.",
  "anamnesis_query": "Check for any self-reported medication non-adherence, side effects, \
or lifestyle changes that could explain a rising blood pressure trend."
}}

Example 2 (Informational/benign-leaning case -- note you still query, you don't assume):
Input alert: elevated_fasting_glucose, value 195 mg/dL, baseline threshold 130 mg/dL, \
rising over 7 days from 145 to 195.
Output:
{{
  "patient_id": "P002",
  "urgency": "Routine",
  "reasoning": "Fasting glucose has risen over a week and exceeds threshold. Without \
further context this would warrant Urgent classification, but a recent medication \
dose increase or dietary change could plausibly and benignly explain a transient rise. \
Since I cannot confirm that without querying EHR and anamnesis, I classify conservatively \
as Routine pending context rather than assuming the benign explanation -- the Synthesis \
Agent will re-assess once context is in hand.",
  "clinical_question": "Why has this patient's fasting glucose risen over the past week, \
and is this consistent with a known treatment change or a new uncontrolled trend?",
  "ehr_query": "Retrieve current diabetes medications, any recent dose changes, and recent \
HbA1c or glucose lab values.",
  "anamnesis_query": "Check for any recently reported dietary changes, medication \
adherence issues, or new symptoms of hyperglycemia."
}}

Example 3 (EDGE CASE -- sparse/ambiguous alert, incomplete baseline):
Input alert: elevated_blood_pressure, systolic 156, diastolic 96, baseline threshold \
140/90 explicitly marked as "estimated, not confirmed in record".
Output:
{{
  "patient_id": "P004",
  "urgency": "Urgent",
  "reasoning": "Blood pressure is elevated across two available readings, but the \
baseline threshold itself is marked as unconfirmed, meaning even the comparison point \
is uncertain. Given this is a recently transferred patient with a sparse record, I \
cannot rule out untreated or undertreated hypertension. I classify as Urgent rather \
than Routine because the uncertainty itself is a risk factor -- an unconfirmed and \
possibly absent treatment history with elevated readings should not be treated as low \
priority.",
  "clinical_question": "Is this patient's elevated blood pressure being treated at all, \
and what can be established about their actual cardiovascular history given the sparse \
record?",
  "ehr_query": "Retrieve any available antihypertensive medications, diagnoses, and prior \
BP readings, and explicitly note what is missing or unconfirmed in the record.",
  "anamnesis_query": "Check self-reported medication history, headache or other symptoms, \
and any details the patient can provide about prior treatment for high blood pressure."
}}
"""

USER_TEMPLATE = """Here is the incoming RPM alert to triage:

{alert_json}

Classify this alert and produce your structured output now."""


def build_triage_chain():
    llm = get_llm(temperature=0.1, agent_name="TriageAgent")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("user", USER_TEMPLATE),
    ])
    return prompt | llm


def run_triage(alert: dict) -> dict:
    """
    Runs the Triage Agent on a single RPM alert.
    Returns the parsed triage decision dict, or raises ValueError if the
    model's output could not be parsed as valid JSON matching the schema.
    """
    chain = build_triage_chain()
    response = chain.invoke({"alert_json": json.dumps(alert, indent=2)})
    raw_text = response.content.strip()

    # Defensive cleanup in case the model wraps output in markdown fences
    # despite instructions not to -- this happens occasionally with Gemini.
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"TriageAgent returned non-JSON output: {raw_text[:500]}"
        ) from e

    required_keys = {"patient_id", "urgency", "reasoning", "clinical_question",
                      "ehr_query", "anamnesis_query"}
    missing = required_keys - result.keys()
    if missing:
        raise ValueError(f"TriageAgent output missing required keys: {missing}")

    if result["urgency"] not in {"Critical", "Urgent", "Routine", "Informational"}:
        raise ValueError(f"TriageAgent returned invalid urgency value: {result['urgency']}")

    return result


if __name__ == "__main__":
    # Quick manual smoke test against scenario 1's alert
    import os
    test_alert = json.load(open(os.path.join(
        os.path.dirname(__file__), "..", "data", "scenarios", "S1_missed_medication.json"
    )))["input_alert"]

    print("Input alert:", json.dumps(test_alert, indent=2))
    print("\nRunning triage...\n")
    result = run_triage(test_alert)
    print(json.dumps(result, indent=2))