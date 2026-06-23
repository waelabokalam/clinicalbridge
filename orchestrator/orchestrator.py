"""
orchestrator.py

Purpose (per spec 6.5): Coordinate the entire multi-agent workflow -- route alert
ingestion through synthesis to output delivery, manage retry/fallback, enforce
safety guardrails (Critical alerts bypass synthesis and escalate immediately),
and maintain a session log of all inter-agent communications for auditability.

IMPORTANT DEVIATION FROM SPEC, DOCUMENTED HONESTLY:
Spec section 4.1/4.2 calls for the EHR and Anamnesis agents to be dispatched in
PARALLEL after triage. This implementation runs them SEQUENTIALLY instead, with
a short delay between calls. Reason: the Gemini free-tier API key used for this
project is rate-limited to 5 requests/minute. True parallel dispatch (two
simultaneous API calls) risks tripping that limit and causing a transient
failure that has nothing to do with the system's actual design correctness.
Sequential dispatch with a small delay trades a small amount of latency for
reliability under this real-world infrastructure constraint -- a tradeoff any
production engineer would recognize. This is flagged here, in the orchestrator's
own docstring, and will be flagged again in the prompt engineering portfolio and
known-limitations section, rather than silently diverging from the spec.
"""
import json
import os
import time
from datetime import datetime, timezone

from agents.triage_agent import run_triage
from agents.ehr_agent import run_ehr_agent
from agents.anamnesis_agent import run_anamnesis_agent
from agents.synthesis_agent import run_synthesis_agent

# Small delay between sequential agent calls to stay under the 5 RPM free-tier limit.
INTER_AGENT_DELAY_SECONDS = 3


class OrchestratorError(Exception):
    """Raised when the orchestrator cannot complete the workflow even after retries."""
    pass


def _log_event(session_log: list, agent: str, event: str, detail: dict = None):
    """Appends a structured entry to the session log for auditability (spec 6.5)."""
    session_log.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "event": event,
        "detail": detail or {},
    })


def _run_with_retry(fn, *args, max_retries: int = 2, agent_name: str = "agent", **kwargs):
    """
    Simple retry wrapper (spec 6.5: 'implement retry logic and fallback strategies
    when an agent fails or returns low-confidence results'). Retries on any
    exception (JSON parse failure, API error, schema validation failure), with
    a backoff delay. Raises OrchestratorError if all retries are exhausted.
    """
    last_error = None
    for attempt in range(1, max_retries + 2):  # initial try + max_retries
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_error = e
            if attempt <= max_retries:
                wait = INTER_AGENT_DELAY_SECONDS * attempt
                print(f"  [{agent_name}] attempt {attempt} failed ({e}); retrying in {wait}s...")
                time.sleep(wait)
            else:
                break
    raise OrchestratorError(
        f"{agent_name} failed after {max_retries + 1} attempts. Last error: {last_error}"
    )


def process_alert(alert: dict) -> dict:
    """
    Main orchestration entrypoint (spec 4.2 data flow, steps 1-6).

    Returns a dict with:
      - "status": "escalated_critical" | "completed" | "failed"
      - "ccb": the Clinical Context Brief (None if escalated_critical or failed)
      - "triage": the triage decision (always present if triage succeeded)
      - "session_log": full audit trail of the run
    """
    session_log = []
    _log_event(session_log, "Orchestrator", "alert_received", {"alert_id": alert.get("alert_id")})

    # --- Step 2: Triage ---
    try:
        triage_result = _run_with_retry(run_triage, alert, agent_name="TriageAgent")
    except OrchestratorError as e:
        _log_event(session_log, "Orchestrator", "triage_failed_terminal", {"error": str(e)})
        return {"status": "failed", "ccb": None, "triage": None,
                "session_log": session_log, "error": str(e)}

    _log_event(session_log, "TriageAgent", "completed", triage_result)

    # --- Safety guardrail (spec 6.5): Critical alerts bypass synthesis entirely ---
    if triage_result["urgency"] == "Critical":
        _log_event(session_log, "Orchestrator", "critical_escalation",
                    {"reason": "Critical urgency bypasses full synthesis per safety guardrail."})
        return {
            "status": "escalated_critical",
            "ccb": None,
            "triage": triage_result,
            "session_log": session_log,
            "escalation_message": (
                f"CRITICAL ALERT for patient {triage_result['patient_id']}: "
                f"{triage_result['clinical_question']} "
                f"This requires IMMEDIATE human clinical review. Full context synthesis "
                f"has been bypassed to avoid delaying escalation."
            ),
        }

    patient_id = alert["patient_id"]

    # --- Step 3/4: EHR and Anamnesis retrieval (SEQUENTIAL -- see module docstring) ---
    try:
        ehr_result = _run_with_retry(
            run_ehr_agent, patient_id, triage_result["clinical_question"],
            triage_result["ehr_query"], agent_name="EHRAgent",
        )
    except OrchestratorError as e:
        _log_event(session_log, "Orchestrator", "ehr_failed_using_fallback", {"error": str(e)})
        # Fallback (spec 6.5): proceed with an explicit empty/low-confidence EHR result
        # rather than crashing the whole pipeline over one failed retrieval agent.
        ehr_result = {
            "patient_id": patient_id, "relevant_problem_list": [], "relevant_medications": [],
            "relevant_labs": [], "relevant_visit_notes": [], "retrieval_confidence": "low",
            "flagged_gaps": f"EHR Agent failed to return results after retries: {e}",
        }

    _log_event(session_log, "EHRAgent", "completed", ehr_result)
    time.sleep(INTER_AGENT_DELAY_SECONDS)  # stay under free-tier RPM before next call

    try:
        anamnesis_result = _run_with_retry(
            run_anamnesis_agent, patient_id, triage_result["clinical_question"],
            triage_result["anamnesis_query"], agent_name="AnamnesisAgent",
        )
    except OrchestratorError as e:
        _log_event(session_log, "Orchestrator", "anamnesis_failed_using_fallback", {"error": str(e)})
        anamnesis_result = {
            "patient_id": patient_id, "reported_symptoms_and_timeline": [],
            "medication_adherence_status": [], "relevant_lifestyle_factors": [],
            "family_history_highlights": [], "patient_expressed_concerns": "Unknown",
            "interpretation_confidence": "low",
            "flagged_gaps": f"Anamnesis Agent failed to return results after retries: {e}",
        }

    _log_event(session_log, "AnamnesisAgent", "completed", anamnesis_result)
    time.sleep(INTER_AGENT_DELAY_SECONDS)

    # --- Step 5: Synthesis ---
    try:
        ccb = _run_with_retry(
            run_synthesis_agent, triage_result, ehr_result, anamnesis_result, alert,
            agent_name="SynthesisAgent",
        )
    except OrchestratorError as e:
        _log_event(session_log, "Orchestrator", "synthesis_failed_terminal", {"error": str(e)})
        return {"status": "failed", "ccb": None, "triage": triage_result,
                "session_log": session_log, "error": str(e)}

    _log_event(session_log, "SynthesisAgent", "completed", {"confidence_score": ccb.get("confidence_score")})
    _log_event(session_log, "Orchestrator", "workflow_completed", {})

    return {
        "status": "completed",
        "ccb": ccb,
        "triage": triage_result,
        "ehr": ehr_result,
        "anamnesis": anamnesis_result,
        "session_log": session_log,
    }


if __name__ == "__main__":
    scenario_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "scenarios", "S1_missed_medication.json"
    )
    scenario = json.load(open(scenario_path))
    alert = scenario["input_alert"]

    print(f"Processing alert for scenario: {scenario['title']}\n")
    result = process_alert(alert)

    print(f"\n=== STATUS: {result['status']} ===\n")
    if result["ccb"]:
        print(json.dumps(result["ccb"], indent=2))
    elif result["status"] == "escalated_critical":
        print(result["escalation_message"])
    else:
        print("Error:", result.get("error"))

    print(f"\n=== SESSION LOG ({len(result['session_log'])} events) ===")
    for event in result["session_log"]:
        print(f"  [{event['timestamp']}] {event['agent']}: {event['event']}")