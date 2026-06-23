"""
test_critical_bypass.py

Standalone test for the Critical-alert escalation guardrail (spec 6.5).
This does NOT use one of the 5 main scenarios -- none of them are Critical --
so this synthetic alert exists specifically to prove the bypass path works
before we move into full scenario evaluation. A safety guardrail that has
never actually been exercised is not a verified guardrail.
"""
import json
from orchestrator.orchestrator import process_alert

# Synthetic Critical-range alert: hypertensive crisis territory (>180/120),
# which should trigger Critical classification and bypass synthesis entirely.
critical_test_alert = {
    "alert_id": "ALT-TEST-CRITICAL-001",
    "patient_id": "P001",
    "timestamp": "2026-06-15T05:00:00",
    "device_type": "home BP cuff",
    "alert_category": "sustained_elevated_blood_pressure",
    "measured_values": {"systolic": 205, "diastolic": 128},
    "baseline_threshold": {"systolic": 140, "diastolic": 90},
}

if __name__ == "__main__":
    print("Testing Critical alert escalation path...\n")
    result = process_alert(critical_test_alert)

    print(f"Status: {result['status']}")
    assert result["status"] == "escalated_critical", \
        f"FAIL: expected 'escalated_critical', got '{result['status']}'"
    assert result["ccb"] is None, "FAIL: CCB should be None on Critical bypass"

    print(f"Triage urgency: {result['triage']['urgency']}")
    assert result["triage"]["urgency"] == "Critical", \
        f"FAIL: expected Critical, got {result['triage']['urgency']}"

    print(f"\nEscalation message:\n{result['escalation_message']}")
    print(f"\nSession log ({len(result['session_log'])} events):")
    for event in result["session_log"]:
        print(f"  {event['agent']}: {event['event']}")

    print("\n✅ PASS: Critical bypass guardrail works correctly.")