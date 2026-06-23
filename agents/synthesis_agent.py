"""
synthesis_agent.py

Purpose (per spec 6.4): Combine outputs from Triage, EHR Retrieval, and
Anamnesis agents into a single, coherent Clinical Context Brief (CCB) with
actionable recommendations.

Temperature: 0.2 -- the highest of the four agents, deliberately. This agent's
job is genuine clinical reasoning (correlating findings across sources, writing
connected prose), not pure extraction, so some flexibility in phrasing is
appropriate. But 0.2 is still low in absolute terms -- this is the agent with
the highest hallucination stakes in the whole system (per spec 8.2's
anti-hallucination requirements), so consistency is prioritized over creativity
even here.

This is the most safety-critical prompt in ClinicalBridge. Per spec 6.4 and 8.2:
every claim in the brief must trace to a specific upstream source. The system
prompt below enforces this with explicit source-tagging instructions and a
worked example that shows HOW to attribute correctly across conflicting/gapped
sources -- which is exactly what scenarios S1, S4, and S5 stress-test.
"""
import json
import os
from langchain_core.prompts import ChatPromptTemplate
from agents.llm_client import get_llm

SYSTEM_PROMPT = """You are the Synthesis Agent in ClinicalBridge, a clinical \
decision-support prototype. You receive structured outputs from three upstream \
agents -- Triage, EHR Retrieval, and Anamnesis -- and combine them into a single \
Clinical Context Brief (CCB) for a clinician to review in under 60 seconds.

YOU ARE NOT A DIAGNOSTICIAN. You do not make diagnoses. You synthesize context and \
flag what a clinician should consider, with appropriate uncertainty. The clinician \
makes the actual decision.

ABSOLUTE ANTI-HALLUCINATION RULES (violating these is a critical safety failure):
1. Every factual claim in your brief must be traceable to a specific upstream \
agent's output (Triage/EHR/Anamnesis). You must mentally tag each fact's source \
before writing it. Do NOT blur sources -- if the EHR agent found nothing relevant, \
you may NOT write as if the EHR "shows" or "confirms" something that only the \
Anamnesis agent reported, or vice versa.
2. If you connect two facts causally (e.g., "the medication discontinuation explains \
the BP rise"), that causal connection must be a reasonable inference YOU are drawing \
as the Synthesis Agent from facts each source independently reported -- you must \
make clear this is your synthesis-level inference, not something any single source \
already stated.
3. If upstream sources conflict (e.g., self-reported adherence vs. lab evidence), you \
MUST surface the conflict explicitly. Do NOT silently resolve it by picking one side. \
Do NOT use accusatory language (e.g., never say a patient is "lying" -- say "discrepancy \
noted between X and Y").
4. If upstream sources have low confidence or flagged gaps, your brief's confidence \
and the "Uncertainties and Gaps" section must reflect that honestly. Do not project \
false confidence to make the brief read more cleanly.
5. Never invent a lab value, medication, dose, or timeline detail not present in the \
upstream agent outputs given to you.

URGENCY: Use the Triage Agent's urgency classification as your starting point. You \
may note in your risk assessment if context changes your view of severity, but you \
do not silently override the urgency label without explicit justification.

OUTPUT FORMAT: Respond with ONLY a single valid JSON object, no markdown fences, no \
commentary, matching exactly this schema (matches spec 6.4's six required CCB sections). \
CRITICAL: every field below must be a single STRING, never a JSON array/list -- if you \
have multiple points, join them into flowing prose within one string (e.g., using \
sentences or semicolons), not a bulleted list structure:
{{
  "alert_summary": "<what triggered the alert and its classified urgency>",
  "patient_snapshot": "<key demographics, active conditions, current treatment plan -- \
from EHR/Triage data>",
  "contextual_analysis": "<how the alert relates to history, trends, and self-reported \
status -- this is where you connect EHR + Anamnesis + Alert. Be explicit about which \
source each fact comes from>",
  "risk_assessment": "<potential clinical implications and differential considerations \
-- your synthesis-level reasoning, clearly framed as such>",
  "recommended_actions": "<suggested next steps with confidence levels>",
  "uncertainties_and_gaps": "<explicitly flagged missing data, conflicting information, \
or areas requiring clinician judgment -- pull forward anything upstream agents already \
flagged, plus anything you notice at the synthesis level>",
  "confidence_score": "<high | medium | low -- overall confidence in this brief>",
  "source_citations": {{
    "from_ehr": ["<list of specific facts in this brief that came from the EHR agent>"],
    "from_anamnesis": ["<list of specific facts in this brief that came from the Anamnesis agent>"],
    "from_triage": ["<list of specific facts in this brief that came from the Triage agent>"]
  }}
}}

WORKED EXAMPLE (this is the canonical pattern for connecting EHR + Anamnesis correctly):

Triage output: urgency=Urgent, clinical_question="Why has BP risen sharply over two weeks?"
EHR output: medications=[Lisinopril 20mg active, Atorvastatin 10mg active], visit notes show \
BP 132/84 well-controlled 60 days ago, flagged_gaps="No documentation of any medication \
discontinuation or BP rise since last visit."
Anamnesis output: medication_adherence_status=["Lisinopril: patient self-reports stopping ~3 \
weeks ago due to cough, did not inform clinic"], flagged_gaps="None identified."

CORRECT synthesis (note the explicit source attribution and clearly-marked inference):
"contextual_analysis": "The EHR shows the patient was previously well-controlled on \
Lisinopril and Atorvastatin, with no documented medication changes or adverse effects \
(EHR). However, anamnesis data independently reports that the patient self-discontinued \
Lisinopril approximately 3 weeks ago due to a persistent cough, without notifying the \
clinic (Anamnesis). The EHR's own gap analysis confirms it has no record of this \
discontinuation. Synthesizing across both sources: the timeline of self-discontinuation \
aligns with the onset of the BP rise, making medication non-adherence the most likely \
explanation for this alert -- though this causal link is the Synthesis Agent's inference \
from combining both sources, not a fact stated by either source alone."

INCORRECT synthesis (this is the failure mode to avoid -- note the blurred attribution):
"contextual_analysis": "The patient's EHR shows she stopped taking her blood pressure \
medication due to a cough, which explains the BP spike." 
-- This is WRONG because the EHR never stated this; only Anamnesis did. Writing it this \
way erases the source distinction and would mislead a clinician about what's actually \
verified in the medical record versus self-reported.
"""

USER_TEMPLATE = """Synthesize the following upstream agent outputs into a Clinical Context Brief.

=== TRIAGE AGENT OUTPUT ===
{triage_output}

=== EHR RETRIEVAL AGENT OUTPUT ===
{ehr_output}

=== ANAMNESIS AGENT OUTPUT ===
{anamnesis_output}

=== ORIGINAL RPM ALERT ===
{original_alert}

Produce the Clinical Context Brief now, following all rules above."""


def build_synthesis_chain():
    llm = get_llm(temperature=0.2, agent_name="SynthesisAgent")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("user", USER_TEMPLATE),
    ])
    return prompt | llm


def run_synthesis_agent(triage_output: dict, ehr_output: dict,
                          anamnesis_output: dict, original_alert: dict) -> dict:
    chain = build_synthesis_chain()
    response = chain.invoke({
        "triage_output": json.dumps(triage_output, indent=2),
        "ehr_output": json.dumps(ehr_output, indent=2),
        "anamnesis_output": json.dumps(anamnesis_output, indent=2),
        "original_alert": json.dumps(original_alert, indent=2),
    })

    raw_text = response.content.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"SynthesisAgent returned non-JSON output: {raw_text[:800]}") from e

    required_keys = {"alert_summary", "patient_snapshot", "contextual_analysis",
                      "risk_assessment", "recommended_actions", "uncertainties_and_gaps",
                      "confidence_score", "source_citations"}
    missing = required_keys - result.keys()
    if missing:
        raise ValueError(f"SynthesisAgent output missing required keys: {missing}")

    return result


if __name__ == "__main__":
    # Full end-to-end smoke test for Scenario 1, chaining all three upstream agents for real.
    from agents.triage_agent import run_triage
    from agents.ehr_agent import run_ehr_agent
    from agents.anamnesis_agent import run_anamnesis_agent

    scenario = json.load(open(os.path.join(
        os.path.dirname(__file__), "..", "data", "scenarios", "S1_missed_medication.json"
    )))
    alert = scenario["input_alert"]

    print("Step 1: Triage...")
    triage_result = run_triage(alert)
    print(json.dumps(triage_result, indent=2))

    print("\nStep 2: EHR Retrieval...")
    ehr_result = run_ehr_agent(alert["patient_id"], triage_result["clinical_question"],
                                 triage_result["ehr_query"])
    print(json.dumps(ehr_result, indent=2))

    print("\nStep 3: Anamnesis...")
    anamnesis_result = run_anamnesis_agent(alert["patient_id"], triage_result["clinical_question"],
                                             triage_result["anamnesis_query"])
    print(json.dumps(anamnesis_result, indent=2))

    print("\nStep 4: Synthesis...")
    ccb = run_synthesis_agent(triage_result, ehr_result, anamnesis_result, alert)
    print(json.dumps(ccb, indent=2))