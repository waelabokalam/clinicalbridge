"""
ehr_agent.py

Purpose (per spec 6.2): Search the patient's longitudinal EHR using RAG to
extract diagnoses, medications, labs, and visit notes relevant to the
current alert.

Temperature: 0.1 -- same rationale as Triage. This agent's job is to report
what's IN the record accurately, not to creatively interpret it. Low temp
reduces the chance of the model "filling in" plausible-sounding details.

Critical design choice: retrieval is filtered by patient_id metadata, not
just semantic similarity across the whole store. Without this filter, a
query like "recent BP readings" could retrieve another patient's chunks if
they're semantically closer -- a serious safety bug in a multi-patient
vector store. This is the kind of failure that belongs in the failure-mode
log: it's exactly the sort of thing that looks fine on a single-patient demo
and breaks the moment the store has more than one patient in it.
"""
import json
import os
from orchestrator.observability import trace_operation
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from agents.llm_client import get_llm

PERSIST_DIR = os.path.join(os.path.dirname(__file__), "..", "chroma_db", "ehr")

SYSTEM_PROMPT = """You are a clinical data analyst, NOT a diagnostician. Your job \
is to read retrieved excerpts from a patient's electronic health record and extract \
exactly what is relevant to a specific clinical question -- nothing more, nothing \
invented.

CRITICAL RULES:
1. You may ONLY state facts that appear in the retrieved EHR excerpts provided to \
you below. If the excerpts do not contain information relevant to part of the \
question, you MUST say so explicitly (e.g., "No documented history of X in the \
available record") rather than omitting it silently or guessing.
2. Do NOT infer a diagnosis, do NOT speculate about causes, and do NOT connect EHR \
facts to anything you might know from outside this record (e.g., do not say a \
medication "is known to cause" a side effect unless that side effect is itself \
documented in these excerpts -- that kind of clinical inference belongs to the \
Synthesis Agent, not you).
3. If excerpts are contradictory or incomplete, report that plainly rather than \
silently picking one version.
4. Every claim you make must be traceable to a specific excerpt. Include enough \
detail (dates, exact values) that someone could verify it against the source. \
CRITICAL: only state a specific calendar date if that exact date string appears \
verbatim in the retrieved excerpt text below. If an excerpt only gives a relative \
time reference (e.g., "90 days ago") rather than an absolute date, report it using \
that same relative phrasing -- do NOT calculate, infer, or invent an absolute \
calendar date that does not literally appear in the excerpt. Inventing a plausible-\
looking date that isn't in the source is a hallucination, even if the surrounding \
clinical facts are accurate.
OUTPUT FORMAT: Respond with ONLY a single valid JSON object, no markdown fences, \
no commentary, matching exactly this schema:

{{
  "patient_id": "<string>",
  "relevant_problem_list": ["<diagnosis strings found in excerpts, or empty list>"],
  "relevant_medications": ["<medication strings with dose/status found in excerpts, or empty list>"],
  "relevant_labs": ["<lab result strings with dates/values found in excerpts, or empty list>"],
  "relevant_visit_notes": ["<brief visit note excerpts relevant to the question, or empty list>"],
  "retrieval_confidence": "<high | medium | low -- your assessment of whether the \
retrieved excerpts adequately cover the clinical question asked>",
  "flagged_gaps": "<explicit statement of what relevant information is MISSING from \
the available record, given the question asked. Use 'None identified' only if you \
are confident the record is genuinely complete for this question.>"
}}
CRITICAL FORMATTING RULE: Every key in the schema above MUST be present in your \
output, even when the answer is that nothing relevant was found. Use an empty list \
[] for that category -- do NOT omit the key entirely. Omitting a key is a formatting \
error that breaks downstream processing, even if your clinical reasoning about "nothing \
relevant found" was correct.

FEW-SHOT EXAMPLES:

Example 1 (complete record, clear answer):
Question: "Retrieve current antihypertensive medications, any recent medication \
changes, and recent BP readings or visit notes for this patient."
Retrieved excerpts show: Lisinopril 20mg daily (active), Atorvastatin 10mg daily \
(active), visit note from 60 days ago noting BP 132/84 well controlled.
Output:
{{
  "patient_id": "P001",
  "relevant_problem_list": ["Essential Hypertension (active)", "Hyperlipidemia (active)"],
  "relevant_medications": ["Lisinopril 20mg once daily (active, prescribed 400 days ago)", \
"Atorvastatin 10mg once daily (active, prescribed 400 days ago)"],
  "relevant_labs": [],
  "relevant_visit_notes": ["60 days ago (Primary Care Visit): BP 132/84 in clinic, well \
controlled, continue current regimen. No cough reported at that visit."],
  "retrieval_confidence": "high",
  "flagged_gaps": "No documentation found of any medication discontinuation, side effects, \
or change to the antihypertensive regimen since the last visit note. The record does not \
explain the cause of any subsequent BP changes after that visit."
}}

Example 2 (EDGE CASE -- sparse record, must flag gaps prominently):
Question: "Retrieve any available antihypertensive medications, diagnoses, and prior BP \
readings, and explicitly note what is missing or unconfirmed in the record."
Retrieved excerpts show: Metformin listed as patient-reported/unverified, no labs, one \
intake note mentioning suspected diabetes and hypertension history with no confirmed details.
Output:
{{
  "patient_id": "P004",
  "relevant_problem_list": [],
  "relevant_medications": ["Metformin, dose and frequency listed as 'unknown - per patient \
report', status active, explicitly marked as patient-reported and unverified"],
  "relevant_labs": [],
  "relevant_visit_notes": ["5 days ago (New Patient Intake - Transfer): patient reports \
history of diabetes and hypertension, prior records requested but not yet received, treating \
on patient-reported history pending records."],
  "retrieval_confidence": "low",
  "flagged_gaps": "No confirmed diagnoses are in the problem list despite a self-reported \
8-year history of diabetes and hypertension -- the EHR does not contain a verified problem \
list entry for either condition. No antihypertensive medication is documented at all. No labs \
are on file. No prior BP readings exist in the EHR. This record cannot confirm whether this \
patient is being treated for hypertension currently."
}}
Example 3 (EDGE CASE -- query asks about something the EHR has NO data on at all, \
but other excerpt categories were still retrieved):
Question: "Has this patient reported any recent international travel or unusual \
dietary exposures?"
Retrieved excerpts show: problem list, medications, and visit notes for an unrelated \
hypertension/hyperlipidemia history -- nothing about travel or diet anywhere.
Output:
{{
  "patient_id": "P001",
  "relevant_problem_list": ["Essential Hypertension (active)", "Hyperlipidemia (active)"],
  "relevant_medications": ["Lisinopril 20mg once daily (active)", "Atorvastatin 10mg once \
daily (active)"],
  "relevant_labs": [],
  "relevant_visit_notes": ["Visit notes reviewed but contain no mention of travel or dietary \
exposures."],
  "retrieval_confidence": "low",
  "flagged_gaps": "No documentation of recent international travel or unusual dietary \
exposures exists anywhere in the available record. The retrieved excerpts relate only to \
this patient's hypertension and hyperlipidemia management and do not address the question asked."
}}
-- Note relevant_labs is an empty list [], NOT omitted, even though no labs were relevant here.
"""

USER_TEMPLATE = """Clinical question to investigate: {clinical_question}

EHR retrieval query: {ehr_query}

Retrieved EHR excerpts for patient {patient_id}:
---
{retrieved_excerpts}
---

Extract and structure the relevant information now, following all rules above."""


def get_vectorstore():
    embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")
    return Chroma(
        persist_directory=PERSIST_DIR,
        embedding_function=embeddings,
        collection_name="ehr_records",
    )


@trace_operation("ehr_retrieval")
def retrieve_chunks(patient_id: str, query: str, k: int = 6) -> list[str]:
    """
    Retrieves the top-k EHR chunks for a SPECIFIC patient only.
    The patient_id filter is a hard metadata filter, not a soft semantic
    preference -- this is the safety-critical line in this whole agent.
    """
    vectorstore = get_vectorstore()
    results = vectorstore.similarity_search(
        query,
        k=k,
        filter={"patient_id": patient_id},
    )
    return [doc.page_content for doc in results]


def build_ehr_chain():
    llm = get_llm(temperature=0.1, agent_name="EHRAgent")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("user", USER_TEMPLATE),
    ])
    return prompt | llm


def run_ehr_agent(patient_id: str, clinical_question: str, ehr_query: str) -> dict:
    """
    Full EHR Retrieval Agent pipeline: retrieve chunks for this patient,
    then have the LLM synthesize them into the structured EHR context object.
    """
    chunks = retrieve_chunks(patient_id, ehr_query, k=6)

    if not chunks:
        # No chunks at all for this patient -- don't even call the LLM with
        # empty context, just return an honest empty result.
        return {
            "patient_id": patient_id,
            "relevant_problem_list": [],
            "relevant_medications": [],
            "relevant_labs": [],
            "relevant_visit_notes": [],
            "retrieval_confidence": "low",
            "flagged_gaps": "No EHR records found at all for this patient ID in the vector store.",
        }

    excerpts_text = "\n\n".join(chunks)

    chain = build_ehr_chain()
    response = chain.invoke({
        "clinical_question": clinical_question,
        "ehr_query": ehr_query,
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
        raise ValueError(f"EHRAgent returned non-JSON output: {raw_text[:500]}") from e

    # Defensive normalization: the LLM sometimes omits a list-type key entirely when
    # that category has no relevant findings, instead of returning an empty list as
    # instructed (a real, documented finding from stress testing -- see iteration log).
    # Rather than keep iterating on the prompt for a case the model has already shown
    # it can fail despite an explicit instruction and worked example, we enforce the
    # schema guarantee here in code, which is the more reliable fix.
    list_keys = ["relevant_problem_list", "relevant_medications", "relevant_labs", "relevant_visit_notes"]
    for key in list_keys:
        if key not in result:
            result[key] = []
    required_keys = {"patient_id", "relevant_problem_list", "relevant_medications",
                      "relevant_labs", "relevant_visit_notes", "retrieval_confidence",
                      "flagged_gaps"}
    missing = required_keys - result.keys()
    if missing:
        raise ValueError(
            f"EHRAgent output missing required keys: {missing}\n"
            f"Full raw output was:\n{raw_text}"
        )
    return result


if __name__ == "__main__":
    # Smoke test against scenario 1
    scenario = json.load(open(os.path.join(
        os.path.dirname(__file__), "..", "data", "scenarios", "S1_missed_medication.json"
    )))
    patient_id = scenario["patient_id"]
    clinical_question = "Why has this patient's blood pressure risen sharply over two weeks?"
    ehr_query = "Retrieve current antihypertensive medications, any recent medication " \
                "changes, and recent BP readings or visit notes for this patient."

    print(f"Running EHR agent for {patient_id}...\n")
    result = run_ehr_agent(patient_id, clinical_question, ehr_query)
    print(json.dumps(result, indent=2))
