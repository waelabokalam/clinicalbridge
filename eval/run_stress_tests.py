"""
run_stress_tests.py

Executes all 8 stress tests defined in stress_tests.py against the relevant
single agent (not the full orchestrator -- these are targeted single-agent
probes, not end-to-end scenarios). Saves results for manual review and
write-up in the failure mode analysis / iteration log.

NOTE on ANAMNESIS_TEST_1 and ANAMNESIS_TEST_2: these use synthetic excerpts
that bypass the real vector store retrieval (since our actual dataset doesn't
contain mental-health or heavily-colloquial content by design). This directly
tests the LLM's interpretation behavior given specific input, isolated from
retrieval quality -- which is exactly what we want to probe here.

Run from project root: python3 -m eval.run_stress_tests
"""
import json
import os
import time
from agents.triage_agent import run_triage
from agents.ehr_agent import run_ehr_agent
from agents.anamnesis_agent import build_anamnesis_chain
from agents.synthesis_agent import run_synthesis_agent
from eval import stress_tests as st

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results", "stress_tests")
DELAY = 4  # seconds between calls, rate-limit safety


def run_anamnesis_on_synthetic(synthetic_excerpt: str, clinical_question: str) -> dict:
    """Runs the Anamnesis Agent's LLM directly on a synthetic excerpt,
    bypassing retrieval (see module docstring)."""
    chain = build_anamnesis_chain()
    response = chain.invoke({
        "clinical_question": clinical_question,
        "anamnesis_query": clinical_question,
        "patient_id": "SYNTHETIC-TEST",
        "retrieved_excerpts": synthetic_excerpt,
    })
    raw = response.content.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    results = {}

    print(f"\n{'='*70}\nTRIAGE_TEST_1: {st.TRIAGE_TEST_1['name']}\n{'='*70}")
    print(f"Rationale: {st.TRIAGE_TEST_1['rationale']}\n")
    results["triage_1"] = run_triage(st.TRIAGE_TEST_1["alert"])
    print(json.dumps(results["triage_1"], indent=2))
    time.sleep(DELAY)

    print(f"\n{'='*70}\nTRIAGE_TEST_2: {st.TRIAGE_TEST_2['name']}\n{'='*70}")
    print(f"Rationale: {st.TRIAGE_TEST_2['rationale']}\n")
    results["triage_2"] = run_triage(st.TRIAGE_TEST_2["alert"])
    print(json.dumps(results["triage_2"], indent=2))
    time.sleep(DELAY)

    print(f"\n{'='*70}\nEHR_TEST_1: {st.EHR_TEST_1['name']}\n{'='*70}")
    print(f"Rationale: {st.EHR_TEST_1['rationale']}\n")
    results["ehr_1"] = run_ehr_agent(
        st.EHR_TEST_1["patient_id"], st.EHR_TEST_1["clinical_question"], st.EHR_TEST_1["ehr_query"]
    )
    print(json.dumps(results["ehr_1"], indent=2))
    time.sleep(DELAY)

    print(f"\n{'='*70}\nEHR_TEST_2: {st.EHR_TEST_2['name']}\n{'='*70}")
    print(f"Rationale: {st.EHR_TEST_2['rationale']}\n")
    results["ehr_2"] = run_ehr_agent(
        st.EHR_TEST_2["patient_id"], st.EHR_TEST_2["clinical_question"], st.EHR_TEST_2["ehr_query"]
    )
    print(json.dumps(results["ehr_2"], indent=2))
    time.sleep(DELAY)

    print(f"\n{'='*70}\nANAMNESIS_TEST_1: {st.ANAMNESIS_TEST_1['name']}\n{'='*70}")
    print(f"Rationale: {st.ANAMNESIS_TEST_1['rationale']}\n")
    results["anamnesis_1"] = run_anamnesis_on_synthetic(
        st.ANAMNESIS_TEST_1["synthetic_excerpt"], st.ANAMNESIS_TEST_1["clinical_question"]
    )
    print(json.dumps(results["anamnesis_1"], indent=2))
    time.sleep(DELAY)

    print(f"\n{'='*70}\nANAMNESIS_TEST_2: {st.ANAMNESIS_TEST_2['name']}\n{'='*70}")
    print(f"Rationale: {st.ANAMNESIS_TEST_2['rationale']}\n")
    results["anamnesis_2"] = run_anamnesis_on_synthetic(
        st.ANAMNESIS_TEST_2["synthetic_excerpt"], st.ANAMNESIS_TEST_2["clinical_question"]
    )
    print(json.dumps(results["anamnesis_2"], indent=2))
    time.sleep(DELAY)

    print(f"\n{'='*70}\nSYNTHESIS_TEST_1: {st.SYNTHESIS_TEST_1['name']}\n{'='*70}")
    print(f"Rationale: {st.SYNTHESIS_TEST_1['rationale']}\n")
    results["synthesis_1"] = run_synthesis_agent(
        st.SYNTHESIS_TEST_1["triage_output"], st.SYNTHESIS_TEST_1["ehr_output"],
        st.SYNTHESIS_TEST_1["anamnesis_output"], st.SYNTHESIS_TEST_1["original_alert"],
    )
    print(json.dumps(results["synthesis_1"], indent=2))

    output_path = os.path.join(RESULTS_DIR, "all_stress_test_results.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n\nAll stress test results saved to: {output_path}")


if __name__ == "__main__":
    main()