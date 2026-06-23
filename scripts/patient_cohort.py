"""
Patient cohort definition for ClinicalBridge.
10 fictional patients with chronic conditions (hypertension, diabetes, heart failure).
Each patient is fully fabricated -- no real patient data used anywhere.

Patients 1-5 are the ones used in the 5 required gold-standard scenarios.
Patients 6-10 exist to give the EHR vector store more volume/noise to retrieve
against, so retrieval precision/recall are meaningfully testable (not just "the
only patient in the DB").
"""

PATIENTS = [
    {
        "patient_id": "P001",
        "name": "Margaret Holloway",
        "age": 67,
        "sex": "F",
        "conditions": ["Essential Hypertension", "Hyperlipidemia"],
        "scenario_role": "S1_missed_medication",
    },
    {
        "patient_id": "P002",
        "name": "David Chen",
        "age": 54,
        "sex": "M",
        "conditions": ["Type 2 Diabetes Mellitus"],
        "scenario_role": "S2_false_alarm",
    },
    {
        "patient_id": "P003",
        "name": "Rosa Fernandez",
        "age": 71,
        "sex": "F",
        "conditions": ["Congestive Heart Failure (HFrEF)", "Essential Hypertension"],
        "scenario_role": "S3_silent_deterioration",
    },
    {
        "patient_id": "P004",
        "name": "Samuel Okafor",
        "age": 59,
        "sex": "M",
        "conditions": ["Type 2 Diabetes Mellitus", "Essential Hypertension"],
        "scenario_role": "S4_incomplete_record",
    },
    {
        "patient_id": "P005",
        "name": "Elena Petrova",
        "age": 63,
        "sex": "F",
        "conditions": ["Essential Hypertension", "Chronic Kidney Disease Stage 2"],
        "scenario_role": "S5_conflicting_data",
    },
    # Background cohort - adds realistic noise/volume to the vector store
    {
        "patient_id": "P006",
        "name": "James Whitfield",
        "age": 72,
        "sex": "M",
        "conditions": ["Congestive Heart Failure (HFpEF)"],
        "scenario_role": None,
    },
    {
        "patient_id": "P007",
        "name": "Aisha Rahman",
        "age": 48,
        "sex": "F",
        "conditions": ["Type 2 Diabetes Mellitus", "Hyperlipidemia"],
        "scenario_role": None,
    },
    {
        "patient_id": "P008",
        "name": "Robert Kowalski",
        "age": 66,
        "sex": "M",
        "conditions": ["Essential Hypertension"],
        "scenario_role": None,
    },
    {
        "patient_id": "P009",
        "name": "Linda Marsh",
        "age": 58,
        "sex": "F",
        "conditions": ["Type 2 Diabetes Mellitus", "Essential Hypertension"],
        "scenario_role": None,
    },
    {
        "patient_id": "P010",
        "name": "Tomasz Nowak",
        "age": 75,
        "sex": "M",
        "conditions": ["Congestive Heart Failure (HFrEF)", "Type 2 Diabetes Mellitus"],
        "scenario_role": None,
    },
]
