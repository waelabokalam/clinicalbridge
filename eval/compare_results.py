"""
compare_results.py

Loads each scenario's gold-standard CCB alongside the actual orchestrator
result, and prints them side by side for systematic comparison. Also runs
a few automated checks against each scenario's "tests_for_failure_modes"
field (written on Day 1) where that's mechanically checkable.

This generates the raw material for:
  - The Iteration Log (what v1 actually did vs. gold standard)
  - The Failure Mode Analysis
  - The Evaluation Report's scenario-by-scenario section

Run from project root: python3 -m eval.compare_results
"""
import json
import os

SCENARIOS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "scenarios")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")


def load_pair(scenario_id):
    scenario = json.load(open(os.path.join(SCENARIOS_DIR, f"{scenario_id}.json")))
    result = json.load(open(os.path.join(RESULTS_DIR, f"{scenario_id}_result.json")))
    return scenario, result


def print_comparison(scenario_id):
    scenario, result = load_pair(scenario_id)
    gold = scenario["gold_standard_ccb"]
    ccb = result.get("ccb")

    print(f"\n{'='*80}")
    print(f"{scenario_id}: {scenario['title']}")
    print(f"{'='*80}")
    print(f"Status: {result['status']}  |  Triage urgency: {result['triage']['urgency']}")
    print(f"Confidence -- gold (implied): high-ish  |  actual: {ccb.get('confidence_score') if ccb else 'N/A'}")

    if not ccb:
        print(f"\n*** NO CCB PRODUCED (status={result['status']}) -- cannot compare. ***")
        return

    print(f"\n--- GOLD STANDARD: contextual_analysis ---\n{gold['contextual_analysis']}")
    print(f"\n--- ACTUAL: contextual_analysis ---\n{ccb['contextual_analysis']}")

    print(f"\n--- GOLD STANDARD: recommended_actions ---\n{gold['recommended_actions']}")
    print(f"\n--- ACTUAL: recommended_actions ---\n{ccb['recommended_actions']}")

    print(f"\n--- FAILURE MODE CHECKS (from Day 1 design) ---")
    for check in scenario["tests_for_failure_modes"]:
        print(f"  [ ] {check}")
    print(f"  (manual review needed for these -- see actual contextual_analysis above)")


def main():
    scenario_files = sorted([
        f.replace(".json", "") for f in os.listdir(SCENARIOS_DIR) if f.endswith(".json")
    ])
    for sid in scenario_files:
        print_comparison(sid)


if __name__ == "__main__":
    main()