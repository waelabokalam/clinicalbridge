"""
anamnesis_agent.py

Purpose (per spec 6.3): Retrieve and interpret the patient's self-reported
history -- symptom logs, lifestyle factors, medication adherence, family
history -- relevant to the current alert.

Temperature: 0.15 -- slightly higher than EHR Agent's 0.1. The EHR agent's job
is closer to pure extraction (structured fields, exact values). This agent has
a genuine interpretation task baked into the spec itself: translating colloquial
patient language into clinical terminology (e.g., "stopped taking it because it
was giving her a cough" -> medication non-adherence due to adverse effect). That
interpretation step benefits from slightly more flexibility than rigid extraction,
but still needs to stay low enough to be consistent and not invent detail beyond
what the patient actually said.

Sensitivity guardrail (per spec 6.3): if mental health or substance use content
appears in retrieved excerpts, it must be reported factually and neutrally, with
no judgmental framing -- this matters even though our current 5 scenarios don't
exercise it, since the agent will eventually run against unseen alerts too.
"""
import json
import os
from orchestrator.observability import trace_operation
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from agents.llm_client import get_llm

PERSIST_DIR = os.path.join(os.path.dirname(__file__), "..", "chroma_db", "anamnesis")

SYSTEM_PROMPT = """You are a clinical anamnesis interpreter. You read a patient's \
own self-reported history -- intake forms, symptom diaries, medication adherence \
logs -- and translate their everyday language into clinically useful, structured \
findings relevant to a specific clinical question.

CRITICAL RULES:
1. You may ONLY report what appears in the retrieved excerpts below. Do not invent \
symptoms, timelines, or details the patient did not actually report.
2. Translate colloquial language into clinical terms WITHOUT changing the substance. \
For example, if a patient says "stopped taking it because of an annoying cough," you \
may report this as "self-discontinued medication due to reported cough side effect" -- \
that is faithful translation, not invention. But do NOT add clinical conclusions the \
patient didn't state (e.g., do not say the cough "was caused by" the medication unless \
the patient or record explicitly says so -- attribute it as patient-reported belief if \
that's what it is).
3. If mental health, substance use, or other sensitive topics appear in the excerpts, \
report them factually and neutrally, exactly as significant as the patient made them \
and no more -- never with judgmental, alarmist, or dismissive language.
4. If retrieved excerpts don't address part of the clinical question, say so explicitly \
rather than omitting it silently.
5. Distinguish clearly between what the patient self-reports as fact (e.g., "adherence \
100%") versus what is otherwise documented -- you are reporting the patient's account, \
not verifying it against other sources (that cross-check is the Synthesis Agent's job).

OUTPUT FORMAT: Respond with ONLY a single valid JSON object, no markdown fences, no \
commentary, matching exactly this schema:

{{
  "patient_id": "<string>",
  "reported_symptoms_and_timeline": ["<symptom + when it was reported/started, or empty list>"],
  "medication_adherence_status": ["<medication: adherence finding, in patient's own reported terms>"],
  "relevant_lifestyle_factors": ["<diet, exercise, stress, occupation changes etc. if relevant, or empty list>"],
  "family_history_highlights": ["<relevant family history if applicable, or empty list>"],
  "patient_expressed_concerns": "<any concerns, frustrations, or questions the patient \
expressed, in neutral language, or 'None expressed' if none>",
  "interpretation_confidence": "<high | medium | low -- how directly the excerpts answer \
the clinical question vs. requiring inference>",
  "flagged_gaps": "<what the clinical question asks about that the anamnesis record does \
NOT address. Use 'None identified' only if genuinely complete.>"
}}

FEW-SHOT EXAMPLES:

Example 1 (clear self-reported causal story):
Question: "Check for any self-reported medication non-adherence, side effects, or \
lifestyle changes that could explain a rising blood pressure trend."
Retrieved excerpts show: patient mentions stopping a BP pill ~3 weeks ago due to a \
persistent cough, symptom diary confirms cough timeline, adherence log shows 40% \
adherence to Lisinopril with note about self-discontinuation.
Output:
{{
  "patient_id": "P001",
  "reported_symptoms_and_timeline": ["Persistent dry cough, patient-reported onset ~25 days \
ago, mostly at night initially", "Cough reported as improving ~10 days ago, after stopping \
the medication"],
  "medication_adherence_status": ["Lisinopril: patient self-reports stopping the medication \
approximately 3 weeks ago, attributing this to the cough; did not inform the clinic before \
doing so. Adherence log estimates 40% adherence over the recent period.", "Atorvastatin: \
patient reports taking as prescribed, adherence log estimates 95%."],
  "relevant_lifestyle_factors": ["Patient lives alone, reports daily walking, non-smoker"],
  "family_history_highlights": ["Mother had hypertension, father had MI at age 70"],
  "patient_expressed_concerns": "None expressed regarding the medication change itself -- \
patient did not view stopping the pill as a significant event ('didn't think it was a big \
deal').",
  "interpretation_confidence": "high",
  "flagged_gaps": "None identified -- the anamnesis record directly and clearly addresses \
the question asked."
}}

Example 2 (EDGE CASE -- conflicting self-report vs. what clinician should know is contested):
Question: "Check self-reported medication adherence given lab evidence suggests sub-therapeutic \
drug levels."
Retrieved excerpts show: patient insists on 100% adherence to both medications, expresses \
frustration that BP remains high despite this, also mentions new stressful job.
Output:
{{
  "patient_id": "P005",
  "reported_symptoms_and_timeline": [],
  "medication_adherence_status": ["Amlodipine: patient self-reports 100% adherence, taking \
every day.", "Losartan: patient self-reports 100% adherence, taking every day. Patient is \
adamant about this and frustrated that BP numbers remain high despite consistent reported use."],
  "relevant_lifestyle_factors": ["Patient recently started a physically demanding new job, \
reports high associated stress."],
  "family_history_highlights": ["Father had chronic kidney disease."],
  "patient_expressed_concerns": "Patient expresses frustration that blood pressure remains \
elevated despite what they report as consistent medication use.",
  "interpretation_confidence": "high",
  "flagged_gaps": "The anamnesis record reflects the patient's self-report only and cannot, \
by itself, resolve why this self-report conflicts with objective lab evidence elsewhere in \
the record -- that reconciliation is outside what anamnesis data alone can determine."
}}
"""

USER_TEMPLATE = """Clinical question to investigate: {clinical_question}

Anamnesis retrieval query: {anamnesis_query}

Retrieved anamnesis excerpts for patient {patient_id}:
---
{retrieved_excerpts}
---

Extract and structure the relevant information now, following all rules above."""


def get_vectorstore():
    embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")
    return Chroma(
        persist_directory=PERSIST_DIR,
        embedding_function=embeddings,
        collection_name="anamnesis_records",
    )


@trace_operation("anamnesis_retrieval")
def retrieve_chunks(patient_id: str, query: str, k: int = 6) -> list[str]:
    """Same hard patient_id metadata filter as the EHR agent -- non-negotiable
    for a multi-patient store."""
    vectorstore = get_vectorstore()
    results = vectorstore.similarity_search(
        query,
        k=k,
        filter={"patient_id": patient_id},
    )
    return [doc.page_content for doc in results]


def build_anamnesis_chain():
    llm = get_llm(temperature=0.15, agent_name="AnamnesisAgent")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("user", USER_TEMPLATE),
    ])
    return prompt | llm


def run_anamnesis_agent(patient_id: str, clinical_question: str, anamnesis_query: str) -> dict:
    chunks = retrieve_chunks(patient_id, anamnesis_query, k=6)

    if not chunks:
        return {
            "patient_id": patient_id,
            "reported_symptoms_and_timeline": [],
            "medication_adherence_status": [],
            "relevant_lifestyle_factors": [],
            "family_history_highlights": [],
            "patient_expressed_concerns": "None expressed",
            "interpretation_confidence": "low",
            "flagged_gaps": "No anamnesis records found at all for this patient ID in the vector store.",
        }

    excerpts_text = "\n\n".join(chunks)

    chain = build_anamnesis_chain()
    response = chain.invoke({
        "clinical_question": clinical_question,
        "anamnesis_query": anamnesis_query,
        "patient_id": patient_id,
        "retrieved_excerpts": excerpts_text,
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
        raise ValueError(f"AnamnesisAgent returned non-JSON output: {raw_text[:500]}") from e

    required_keys = {"patient_id", "reported_symptoms_and_timeline", "medication_adherence_status",
                      "relevant_lifestyle_factors", "family_history_highlights",
                      "patient_expressed_concerns", "interpretation_confidence", "flagged_gaps"}
    missing = required_keys - result.keys()
    if missing:
        raise ValueError(f"AnamnesisAgent output missing required keys: {missing}")

    return result


if __name__ == "__main__":
    scenario = json.load(open(os.path.join(
        os.path.dirname(__file__), "..", "data", "scenarios", "S1_missed_medication.json"
    )))
    patient_id = scenario["patient_id"]
    clinical_question = "Why has this patient's blood pressure risen sharply over two weeks?"
    anamnesis_query = "Check for any self-reported medication non-adherence, side effects, " \
                      "or lifestyle changes that could explain a rising blood pressure trend."

    print(f"Running Anamnesis agent for {patient_id}...\n")
    result = run_anamnesis_agent(patient_id, clinical_question, anamnesis_query)
    print(json.dumps(result, indent=2))
