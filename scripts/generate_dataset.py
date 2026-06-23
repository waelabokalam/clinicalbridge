"""
generate_dataset.py
Generates the simulated EHR, RPM, and Anamnesis datasets for ClinicalBridge.

All data is entirely fabricated. No real patient information is used.

Output layout:
  data/ehr/{patient_id}.json          -- problem list, meds, labs, visit notes, allergies
  data/rpm/{patient_id}.json          -- time-series vitals + the triggering alert
  data/anamnesis/{patient_id}.json    -- intake form, symptom diary, adherence log

Run: python3 scripts/generate_dataset.py
"""
import json
import os
from datetime import datetime, timedelta
from patient_cohort import PATIENTS

OUT_ROOT = os.path.join(os.path.dirname(__file__), "..", "data")
NOW = datetime(2026, 6, 15, 9, 0, 0)  # fixed "current time" so dataset is reproducible


def dt(days_ago=0, hours_ago=0):
    return (NOW - timedelta(days=days_ago, hours=hours_ago)).isoformat()


# ---------------------------------------------------------------------------
# EHR generation
# ---------------------------------------------------------------------------

def base_ehr(p):
    """Generic plausible EHR shell before scenario-specific overrides."""
    return {
        "patient_id": p["patient_id"],
        "demographics": {
            "name": p["name"],
            "age": p["age"],
            "sex": p["sex"],
        },
        "problem_list": [
            {"icd10": cond_to_icd10(c), "description": c, "status": "active",
             "onset_date": dt(days_ago=900)}
            for c in p["conditions"]
        ],
        "medications": [],
        "labs": [],
        "visit_notes": [],
        "allergies": ["No known drug allergies"],
    }


def cond_to_icd10(cond):
    mapping = {
        "Essential Hypertension": "I10",
        "Hyperlipidemia": "E78.5",
        "Type 2 Diabetes Mellitus": "E11.9",
        "Congestive Heart Failure (HFrEF)": "I50.22",
        "Congestive Heart Failure (HFpEF)": "I50.32",
        "Chronic Kidney Disease Stage 2": "N18.2",
    }
    return mapping.get(cond, "R69")  # R69 = illness unspecified, fallback


def build_ehr(p):
    e = base_ehr(p)
    pid = p["patient_id"]

    if pid == "P001":  # Missed Medication scenario
        e["medications"] = [
            {"name": "Lisinopril", "dose": "20mg", "frequency": "once daily",
             "prescribed_date": dt(days_ago=400), "status": "active"},
            {"name": "Atorvastatin", "dose": "10mg", "frequency": "once daily",
             "prescribed_date": dt(days_ago=400), "status": "active"},
        ]
        e["labs"] = [
            {"test": "Potassium", "value": 4.2, "unit": "mEq/L", "date": dt(days_ago=180), "flag": "normal"},
            {"test": "Creatinine", "value": 0.9, "unit": "mg/dL", "date": dt(days_ago=180), "flag": "normal"},
        ]
        e["visit_notes"] = [
            {"date": dt(days_ago=400), "type": "Primary Care Visit",
             "note": "Patient started on Lisinopril 20mg daily for BP control. "
                     "Tolerating well at this visit. No cough reported today."},
            {"date": dt(days_ago=60), "type": "Primary Care Visit",
             "note": "Routine follow-up. BP 132/84 in clinic, well controlled. "
                     "Continue current regimen."},
        ]
        # Deliberately NOT documented: the cough side effect that led to self-discontinuation.
        # This is the gap the Anamnesis Agent must surface and the EHR agent must NOT fabricate.

    elif pid == "P002":  # False Alarm scenario
        e["medications"] = [
            {"name": "Metformin", "dose": "1000mg", "frequency": "twice daily",
             "prescribed_date": dt(days_ago=600), "status": "active"},
            {"name": "Metformin", "dose": "500mg", "frequency": "twice daily",
             "prescribed_date": dt(days_ago=600), "status": "discontinued",
             "discontinued_date": dt(days_ago=10),
             "note": "Dose increased from 500mg BID to 1000mg BID due to suboptimal control."},
        ]
        e["labs"] = [
            {"test": "HbA1c", "value": 8.1, "unit": "%", "date": dt(days_ago=14), "flag": "high"},
            {"test": "HbA1c", "value": 7.4, "unit": "%", "date": dt(days_ago=190), "flag": "high"},
        ]
        e["visit_notes"] = [
            {"date": dt(days_ago=10), "type": "Endocrinology Follow-up",
             "note": "HbA1c remains above goal at 8.1%. Increasing Metformin to 1000mg BID. "
                     "Discussed dietary modification, recommended reducing refined carbohydrate "
                     "intake. Patient agreeable to trial of stricter carb counting."},
        ]

    elif pid == "P003":  # Silent Deterioration scenario
        e["medications"] = [
            {"name": "Furosemide", "dose": "40mg", "frequency": "once daily",
             "prescribed_date": dt(days_ago=500), "status": "active"},
            {"name": "Carvedilol", "dose": "12.5mg", "frequency": "twice daily",
             "prescribed_date": dt(days_ago=500), "status": "active"},
            {"name": "Lisinopril", "dose": "10mg", "frequency": "once daily",
             "prescribed_date": dt(days_ago=500), "status": "active"},
        ]
        e["labs"] = [
            {"test": "BNP", "value": 410, "unit": "pg/mL", "date": dt(days_ago=90), "flag": "high"},
            {"test": "Creatinine", "value": 1.1, "unit": "mg/dL", "date": dt(days_ago=90), "flag": "normal"},
        ]
        e["visit_notes"] = [
            {"date": dt(days_ago=90), "type": "Cardiology Follow-up",
             "note": "HFrEF, EF 35% on last echo. Stable on current GDMT. Weight stable at "
                     "168 lbs in clinic. No peripheral edema noted on exam. Continue current regimen."},
        ]

    elif pid == "P004":  # Incomplete Record scenario - sparse, recently transferred
        e["medications"] = [
            {"name": "Metformin", "dose": "unknown - per patient report", "frequency": "unknown",
             "prescribed_date": "unknown", "status": "active", "source": "patient-reported, unverified"},
        ]
        e["labs"] = []  # no labs transferred yet
        e["visit_notes"] = [
            {"date": dt(days_ago=5), "type": "New Patient Intake (Transfer)",
             "note": "Patient transferring care from out-of-state. Reports history of Type 2 "
                     "Diabetes and hypertension. Prior records requested from previous provider "
                     "but not yet received. Treating on patient-reported history pending records."},
        ]
        e["allergies"] = ["Unknown - pending records transfer"]

    elif pid == "P005":  # Conflicting Data scenario
        e["medications"] = [
            {"name": "Amlodipine", "dose": "10mg", "frequency": "once daily",
             "prescribed_date": dt(days_ago=300), "status": "active"},
            {"name": "Losartan", "dose": "100mg", "frequency": "once daily",
             "prescribed_date": dt(days_ago=300), "status": "active"},
        ]
        e["labs"] = [
            {"test": "Losartan level (urine drug screen, qualitative)", "value": "sub-therapeutic",
             "unit": "n/a", "date": dt(days_ago=20), "flag": "abnormal"},
            {"test": "eGFR", "value": 72, "unit": "mL/min/1.73m2", "date": dt(days_ago=20), "flag": "normal"},
        ]
        e["visit_notes"] = [
            {"date": dt(days_ago=20), "type": "Nephrology Follow-up",
             "note": "BP remains elevated despite reported adherence to dual agent regimen. "
                     "Urine drug screen suggests sub-therapeutic Losartan levels. Adherence "
                     "discussed with patient; patient reports taking medications as prescribed. "
                     "Discrepancy noted, will monitor."},
        ]

    else:  # background cohort - generic plausible records
        e["medications"] = [
            {"name": generic_med_for(p["conditions"][0]), "dose": "standard dose",
             "frequency": "once daily", "prescribed_date": dt(days_ago=500), "status": "active"}
        ]
        e["labs"] = [
            {"test": "Basic Metabolic Panel", "value": "within normal limits", "unit": "n/a",
             "date": dt(days_ago=60), "flag": "normal"}
        ]
        e["visit_notes"] = [
            {"date": dt(days_ago=60), "type": "Routine Follow-up",
             "note": f"Stable. Continue current management of {', '.join(p['conditions'])}."}
        ]

    return e


def generic_med_for(condition):
    return {
        "Essential Hypertension": "Lisinopril",
        "Type 2 Diabetes Mellitus": "Metformin",
        "Congestive Heart Failure (HFpEF)": "Furosemide",
        "Congestive Heart Failure (HFrEF)": "Furosemide",
        "Hyperlipidemia": "Atorvastatin",
    }.get(condition, "Standard therapy")


# ---------------------------------------------------------------------------
# RPM generation
# ---------------------------------------------------------------------------

def build_rpm(p):
    pid = p["patient_id"]

    if pid == "P001":  # Missed Medication - BP spike
        readings = [
            {"timestamp": dt(days_ago=14), "metric": "blood_pressure", "systolic": 134, "diastolic": 86},
            {"timestamp": dt(days_ago=10), "metric": "blood_pressure", "systolic": 138, "diastolic": 88},
            {"timestamp": dt(days_ago=6), "metric": "blood_pressure", "systolic": 151, "diastolic": 94},
            {"timestamp": dt(days_ago=2), "metric": "blood_pressure", "systolic": 162, "diastolic": 98},
            {"timestamp": dt(hours_ago=4), "metric": "blood_pressure", "systolic": 178, "diastolic": 104},
        ]
        alert = {
            "alert_id": "ALT-P001-001",
            "patient_id": pid,
            "timestamp": dt(hours_ago=4),
            "device_type": "home BP cuff",
            "alert_category": "sustained_elevated_blood_pressure",
            "measured_values": {"systolic": 178, "diastolic": 104},
            "baseline_threshold": {"systolic": 140, "diastolic": 90},
        }

    elif pid == "P002":  # False Alarm - glucose spike, contextually benign
        readings = [
            {"timestamp": dt(days_ago=7), "metric": "blood_glucose", "value": 145, "unit": "mg/dL", "context": "fasting"},
            {"timestamp": dt(days_ago=5), "metric": "blood_glucose", "value": 152, "unit": "mg/dL", "context": "fasting"},
            {"timestamp": dt(days_ago=3), "metric": "blood_glucose", "value": 168, "unit": "mg/dL", "context": "fasting"},
            {"timestamp": dt(hours_ago=6), "metric": "blood_glucose", "value": 195, "unit": "mg/dL", "context": "fasting"},
        ]
        alert = {
            "alert_id": "ALT-P002-001",
            "patient_id": pid,
            "timestamp": dt(hours_ago=6),
            "device_type": "CGM",
            "alert_category": "elevated_fasting_glucose",
            "measured_values": {"value": 195, "unit": "mg/dL", "context": "fasting"},
            "baseline_threshold": {"value": 130, "unit": "mg/dL", "context": "fasting"},
        }

    elif pid == "P003":  # Silent Deterioration - gradual weight gain
        readings = [
            {"timestamp": dt(days_ago=14), "metric": "weight", "value": 168.0, "unit": "lbs"},
            {"timestamp": dt(days_ago=11), "metric": "weight", "value": 169.5, "unit": "lbs"},
            {"timestamp": dt(days_ago=8), "metric": "weight", "value": 171.0, "unit": "lbs"},
            {"timestamp": dt(days_ago=5), "metric": "weight", "value": 172.5, "unit": "lbs"},
            {"timestamp": dt(days_ago=2), "metric": "weight", "value": 174.0, "unit": "lbs"},
            {"timestamp": dt(hours_ago=8), "metric": "weight", "value": 175.0, "unit": "lbs"},
        ]
        alert = {
            "alert_id": "ALT-P003-001",
            "patient_id": pid,
            "timestamp": dt(hours_ago=8),
            "device_type": "smart scale",
            "alert_category": "weight_trend",
            "measured_values": {"value": 175.0, "unit": "lbs", "change_from_baseline": "+7.0 lbs over 14 days"},
            "baseline_threshold": {"single_day_change_lbs": 3.0},
            "note": "Each individual day-over-day delta was within single-reading threshold; "
                    "alert triggered by cumulative 14-day trend rule.",
        }

    elif pid == "P004":  # Incomplete Record - moderate BP elevation, sparse history
        readings = [
            {"timestamp": dt(days_ago=4), "metric": "blood_pressure", "systolic": 148, "diastolic": 92},
            {"timestamp": dt(hours_ago=10), "metric": "blood_pressure", "systolic": 156, "diastolic": 96},
        ]
        alert = {
            "alert_id": "ALT-P004-001",
            "patient_id": pid,
            "timestamp": dt(hours_ago=10),
            "device_type": "home BP cuff",
            "alert_category": "elevated_blood_pressure",
            "measured_values": {"systolic": 156, "diastolic": 96},
            "baseline_threshold": {"systolic": 140, "diastolic": 90, "note": "baseline estimated, not confirmed in record"},
        }

    elif pid == "P005":  # Conflicting Data - persistent elevated BP despite reported adherence
        readings = [
            {"timestamp": dt(days_ago=10), "metric": "blood_pressure", "systolic": 152, "diastolic": 92},
            {"timestamp": dt(days_ago=6), "metric": "blood_pressure", "systolic": 158, "diastolic": 95},
            {"timestamp": dt(days_ago=2), "metric": "blood_pressure", "systolic": 160, "diastolic": 97},
            {"timestamp": dt(hours_ago=3), "metric": "blood_pressure", "systolic": 163, "diastolic": 98},
        ]
        alert = {
            "alert_id": "ALT-P005-001",
            "patient_id": pid,
            "timestamp": dt(hours_ago=3),
            "device_type": "home BP cuff",
            "alert_category": "sustained_elevated_blood_pressure",
            "measured_values": {"systolic": 163, "diastolic": 98},
            "baseline_threshold": {"systolic": 140, "diastolic": 90},
        }

    else:  # background cohort - generic stable readings, no alert needed
        readings = [
            {"timestamp": dt(days_ago=5), "metric": "blood_pressure", "systolic": 128, "diastolic": 80},
            {"timestamp": dt(days_ago=1), "metric": "blood_pressure", "systolic": 124, "diastolic": 78},
        ]
        alert = None

    return {"patient_id": pid, "readings": readings, "triggering_alert": alert}


# ---------------------------------------------------------------------------
# Anamnesis generation
# ---------------------------------------------------------------------------

def build_anamnesis(p):
    pid = p["patient_id"]

    if pid == "P001":
        return {
            "patient_id": pid,
            "intake_form": {
                "chief_complaint": "Here for routine check-in, no specific complaints today.",
                "history_of_present_illness": "Patient mentions in passing that she stopped one of "
                    "her blood pressure pills about three weeks ago because it was giving her an "
                    "annoying dry cough that wouldn't go away. Didn't think it was a big deal.",
                "review_of_systems": "Denies chest pain, shortness of breath. Endorses persistent "
                    "dry cough over the past month, now resolving since stopping the medication.",
                "social_history": "Lives alone, walks daily, non-smoker.",
                "family_history": "Mother had hypertension, father had MI at age 70.",
            },
            "symptom_diary": [
                {"date": dt(days_ago=25), "entry": "Cough started, mild, mostly at night."},
                {"date": dt(days_ago=21), "entry": "Cough still there, getting annoying. Stopped taking "
                    "the lisinopril to see if it helps."},
                {"date": dt(days_ago=10), "entry": "Cough much better now. Haven't restarted the pill."},
            ],
            "medication_adherence_log": [
                {"medication": "Lisinopril", "adherence_pct": 40,
                 "note": "Self-discontinued ~3 weeks ago due to cough side effect, did not inform clinic"},
                {"medication": "Atorvastatin", "adherence_pct": 95, "note": "Taking as prescribed"},
            ],
        }

    elif pid == "P002":
        return {
            "patient_id": pid,
            "intake_form": {
                "chief_complaint": "No new complaints.",
                "history_of_present_illness": "Patient started a new lower-carbohydrate eating plan "
                    "about a week ago on recommendation from his endocrinologist. Mentions he's been "
                    "testing his blood sugar more often than usual to see how the new diet affects it.",
                "review_of_systems": "Denies polyuria, polydipsia, blurred vision, fatigue.",
                "social_history": "Works a desk job, moderate exercise 2x/week.",
                "family_history": "Father had Type 2 Diabetes.",
            },
            "symptom_diary": [
                {"date": dt(days_ago=7), "entry": "Started the stricter carb counting my doctor recommended."},
                {"date": dt(days_ago=2), "entry": "Numbers have been a bit higher than I expected this week, "
                    "but I think it's because I'm checking more often now and at different times of day."},
            ],
            "medication_adherence_log": [
                {"medication": "Metformin", "adherence_pct": 100, "note": "Taking new 1000mg BID dose as prescribed"},
            ],
        }

    elif pid == "P003":
        return {
            "patient_id": pid,
            "intake_form": {
                "chief_complaint": "Feeling a bit more tired than usual, ankles look puffier.",
                "history_of_present_illness": "Patient reports increasing ankle swelling over the past "
                    "1-2 weeks, worse by end of day. Also reports mild increase in shortness of breath "
                    "when climbing the stairs to her apartment, which she previously could do without issue.",
                "review_of_systems": "Endorses bilateral ankle edema, mild exertional dyspnea. Denies "
                    "chest pain, orthopnea, paroxysmal nocturnal dyspnea at this time.",
                "social_history": "Lives in a third-floor apartment, no elevator.",
                "family_history": "Non-contributory.",
            },
            "symptom_diary": [
                {"date": dt(days_ago=12), "entry": "Ankles a little swollen by evening, nothing major."},
                {"date": dt(days_ago=6), "entry": "Swelling is more noticeable now, socks leaving marks."},
                {"date": dt(days_ago=1), "entry": "Got a bit winded going up the stairs today, had to stop halfway."},
            ],
            "medication_adherence_log": [
                {"medication": "Furosemide", "adherence_pct": 90, "note": "Occasionally forgets evening dose"},
                {"medication": "Carvedilol", "adherence_pct": 100, "note": "Taking as prescribed"},
            ],
        }

    elif pid == "P004":
        return {
            "patient_id": pid,
            "intake_form": {
                "chief_complaint": "New patient, here to establish care after moving.",
                "history_of_present_illness": "Patient reports a history of 'sugar problems' and 'high "
                    "blood pressure' for about 8 years, previously managed by a doctor in another state. "
                    "Could not recall exact medication names or doses with confidence. Reports occasional "
                    "headaches recently.",
                "review_of_systems": "Endorses occasional headaches. Denies chest pain, vision changes.",
                "social_history": "Recently relocated for work. No regular exercise currently.",
                "family_history": "Reports 'diabetes runs in the family' but no further detail available.",
            },
            "symptom_diary": [
                {"date": dt(days_ago=4), "entry": "Had a headache yesterday, took some ibuprofen, helped a bit."},
            ],
            "medication_adherence_log": [
                {"medication": "Metformin (unconfirmed dose)", "adherence_pct": None,
                 "note": "Patient reports taking 'a diabetes pill' most days but unsure of name/dose accuracy"},
            ],
        }

    elif pid == "P005":
        return {
            "patient_id": pid,
            "intake_form": {
                "chief_complaint": "Following up on blood pressure, says he's doing everything right.",
                "history_of_present_illness": "Patient is adamant that he takes both blood pressure "
                    "medications every single day without missing doses, and is frustrated that his "
                    "numbers are still high despite this.",
                "review_of_systems": "Denies chest pain, vision changes, headache.",
                "social_history": "Recently started a physically demanding new job, reports high stress.",
                "family_history": "Father had chronic kidney disease.",
            },
            "symptom_diary": [
                {"date": dt(days_ago=15), "entry": "Numbers still high even though I take my pills every morning."},
                {"date": dt(days_ago=3), "entry": "Work has been really stressful lately, new job is a lot."},
            ],
            "medication_adherence_log": [
                {"medication": "Amlodipine", "adherence_pct": 100, "note": "Patient self-reports full adherence"},
                {"medication": "Losartan", "adherence_pct": 100, "note": "Patient self-reports full adherence; "
                    "conflicts with sub-therapeutic urine drug screen result in EHR"},
            ],
        }

    else:
        return {
            "patient_id": pid,
            "intake_form": {
                "chief_complaint": "Routine follow-up, no new complaints.",
                "history_of_present_illness": "Stable, no changes reported.",
                "review_of_systems": "Negative review of systems.",
                "social_history": "No significant changes.",
                "family_history": "Non-contributory.",
            },
            "symptom_diary": [
                {"date": dt(days_ago=5), "entry": "Feeling fine, no issues to report."},
            ],
            "medication_adherence_log": [
                {"medication": generic_med_for(p["conditions"][0]), "adherence_pct": 95, "note": "Taking as prescribed"},
            ],
        }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    for sub in ("ehr", "rpm", "anamnesis"):
        os.makedirs(os.path.join(OUT_ROOT, sub), exist_ok=True)

    for p in PATIENTS:
        pid = p["patient_id"]

        ehr = build_ehr(p)
        with open(os.path.join(OUT_ROOT, "ehr", f"{pid}.json"), "w") as f:
            json.dump(ehr, f, indent=2)

        rpm = build_rpm(p)
        with open(os.path.join(OUT_ROOT, "rpm", f"{pid}.json"), "w") as f:
            json.dump(rpm, f, indent=2)

        anamnesis = build_anamnesis(p)
        with open(os.path.join(OUT_ROOT, "anamnesis", f"{pid}.json"), "w") as f:
            json.dump(anamnesis, f, indent=2)

        print(f"Generated {pid}: {p['name']} ({', '.join(p['conditions'])})")

    print(f"\nDone. {len(PATIENTS)} patients generated in {OUT_ROOT}")


if __name__ == "__main__":
    main()
