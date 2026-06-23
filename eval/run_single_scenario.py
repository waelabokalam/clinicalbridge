"""
run_single_scenario.py

Runs ONE scenario through the orchestrator, by scenario_id. Useful for
re-testing a specific scenario during prompt iteration without burning
API quota re-running all 5 every time.

Usage: python3 -m eval.run_single_scenario S5_conflicting_data
"""
import json
import os
import sys
from orchestrator.orchestrator import process_alert

SCENARIOS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "scenarios")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 -m eval.run_single_scenario <scenario_id>")
        print("Example: python3 -m eval.run_single_scenario S5_conflicting_data")
        sys.exit(1)

    scenario_id = sys.argv[1]
    scenario_path = os.path.join(SCENARIOS_DIR, f"{scenario_id}.json")

    if not os.path.exists(scenario_path):
        print(f"Scenario file not found: {scenario_path}")
        sys.exit(1)

    scenario = json.load(open(scenario_path))
    alert = scenario["input_alert"]

    print(f"Running scenario: {scenario['title']} ({scenario_id})\n")
    result = process_alert(alert)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    output_path = os.path.join(RESULTS_DIR, f"{scenario_id}_result.json")
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\nStatus: {result['status']}")
    if result.get("ccb"):
        print(f"Confidence: {result['ccb'].get('confidence_score')}")
        print(f"\n--- Contextual Analysis ---\n{result['ccb']['contextual_analysis']}")
    print(f"\nSaved to: {output_path}")


if __name__ == "__main__":
    main()