"""
run_all_scenarios.py

Runs all 5 gold-standard scenarios through the full ClinicalBridge orchestrator
and saves results for comparison against the gold-standard CCBs.

This is the script that generates the raw evidence for:
  - Chapter 9's evaluation framework (scenario pass rate, hallucination spot-checks)
  - The prompt iteration log (what v1 actually produced, to compare against v2/v3)
  - The failure mode analysis

Output: eval/results/{scenario_id}_result.json for each scenario, plus a
summary printed to console.

Run from project root: python3 -m eval.run_all_scenarios
"""
import json
import os
import time
from orchestrator.orchestrator import process_alert

SCENARIOS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "scenarios")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

# Pause between full scenario runs (each scenario itself makes 3-4 API calls
# with internal delays already; this extra pause is between SCENARIOS, to be
# safe against the 5 RPM ceiling when moving from one scenario's last call
# to the next scenario's first call).
INTER_SCENARIO_DELAY_SECONDS = 5


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)

    scenario_files = sorted([
        f for f in os.listdir(SCENARIOS_DIR) if f.endswith(".json")
    ])

    summary = []

    for i, fname in enumerate(scenario_files):
        scenario_path = os.path.join(SCENARIOS_DIR, fname)
        scenario = json.load(open(scenario_path))
        scenario_id = scenario["scenario_id"]
        alert = scenario["input_alert"]

        print(f"\n{'='*70}")
        print(f"Running scenario {i+1}/{len(scenario_files)}: {scenario['title']} ({scenario_id})")
        print(f"{'='*70}")

        result = process_alert(alert)

        # Save full result (CCB + triage + ehr + anamnesis + session log)
        output_path = os.path.join(RESULTS_DIR, f"{scenario_id}_result.json")
        with open(output_path, "w") as f:
            json.dump(result, f, indent=2)

        print(f"Status: {result['status']}")
        if result["status"] == "completed":
            print(f"Confidence: {result['ccb'].get('confidence_score')}")
        print(f"Saved to: {output_path}")

        summary.append({
            "scenario_id": scenario_id,
            "title": scenario["title"],
            "status": result["status"],
            "confidence_score": result["ccb"].get("confidence_score") if result.get("ccb") else None,
            "triage_urgency": result["triage"]["urgency"] if result.get("triage") else None,
        })

        if i < len(scenario_files) - 1:
            print(f"\nWaiting {INTER_SCENARIO_DELAY_SECONDS}s before next scenario (rate limit safety)...")
            time.sleep(INTER_SCENARIO_DELAY_SECONDS)

    # Print final summary table
    print(f"\n\n{'='*70}")
    print("SUMMARY — ALL SCENARIOS")
    print(f"{'='*70}")
    for s in summary:
        print(f"  {s['scenario_id']:30s} status={s['status']:20s} "
              f"urgency={s['triage_urgency']:15s} confidence={s['confidence_score']}")

    summary_path = os.path.join(RESULTS_DIR, "_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSummary saved to: {summary_path}")


if __name__ == "__main__":
    main()