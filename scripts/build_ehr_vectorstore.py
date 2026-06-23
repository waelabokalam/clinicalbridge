"""
build_ehr_vectorstore.py

Chunks and embeds all patient EHR records into a persistent ChromaDB vector store.
This is a one-time (or re-run-when-data-changes) indexing step, separate from the
EHR Retrieval Agent itself -- the agent just queries the already-built store.

Chunking strategy: one chunk per logical EHR section per patient (problem list,
medications, labs, each visit note, allergies) rather than one giant chunk per
patient. This keeps retrieval precise -- a query about "recent BP readings" should
surface the labs/visit-note chunks, not get diluted by an entire patient's medication
history bundled into the same vector.

Run from project root: python3 -m scripts.build_ehr_vectorstore
"""
import json
import os
import shutil
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_core.documents import Document
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "ehr")
PERSIST_DIR = os.path.join(os.path.dirname(__file__), "..", "chroma_db", "ehr")


def patient_ehr_to_documents(ehr: dict) -> list[Document]:
    """Converts one patient's EHR JSON into a list of chunked Documents."""
    pid = ehr["patient_id"]
    demo = ehr["demographics"]
    docs = []

    # Problem list -- one chunk for the whole list (it's usually short and related)
    if ehr["problem_list"]:
        problems_text = f"Patient {pid} ({demo['name']}, age {demo['age']}, {demo['sex']}) " \
            f"problem list:\n" + "\n".join(
                f"- {p['description']} (ICD-10: {p['icd10']}, status: {p['status']}, "
                f"onset: {p['onset_date']})"
                for p in ehr["problem_list"]
            )
        docs.append(Document(
            page_content=problems_text,
            metadata={"patient_id": pid, "section": "problem_list"},
        ))

    # Medications -- one chunk for the whole med list
    if ehr["medications"]:
        med_lines = []
        for m in ehr["medications"]:
            line = f"- {m['name']} {m.get('dose', '')} {m.get('frequency', '')} " \
                   f"(status: {m.get('status', 'unknown')})"
            if m.get("note"):
                line += f" -- note: {m['note']}"
            if m.get("source"):
                line += f" [source: {m['source']}]"
            med_lines.append(line)
        meds_text = f"Patient {pid} medications:\n" + "\n".join(med_lines)
        docs.append(Document(
            page_content=meds_text,
            metadata={"patient_id": pid, "section": "medications"},
        ))

    # Labs -- one chunk for all labs
    if ehr["labs"]:
        lab_lines = [
            f"- {l['test']}: {l['value']} {l.get('unit', '')} on {l['date']} (flag: {l.get('flag', 'n/a')})"
            for l in ehr["labs"]
        ]
        labs_text = f"Patient {pid} lab results:\n" + "\n".join(lab_lines)
        docs.append(Document(
            page_content=labs_text,
            metadata={"patient_id": pid, "section": "labs"},
        ))

    # Visit notes -- ONE chunk PER note (these are the richest, most distinct content)
    for i, note in enumerate(ehr["visit_notes"]):
        note_text = f"Patient {pid} visit note ({note['type']}, {note['date']}):\n{note['note']}"
        docs.append(Document(
            page_content=note_text,
            metadata={"patient_id": pid, "section": "visit_note", "note_index": i},
        ))

    # Allergies -- small but worth its own chunk
    if ehr.get("allergies"):
        allergy_text = f"Patient {pid} allergies: {', '.join(ehr['allergies'])}"
        docs.append(Document(
            page_content=allergy_text,
            metadata={"patient_id": pid, "section": "allergies"},
        ))

    return docs


def main():
    # Wipe any existing index so re-runs are clean, not additive/duplicated.
    if os.path.exists(PERSIST_DIR):
        shutil.rmtree(PERSIST_DIR)
    os.makedirs(PERSIST_DIR, exist_ok=True)

    all_docs = []
    for fname in sorted(os.listdir(DATA_DIR)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(DATA_DIR, fname)) as f:
            ehr = json.load(f)
        docs = patient_ehr_to_documents(ehr)
        all_docs.extend(docs)
        print(f"  {ehr['patient_id']}: {len(docs)} chunks")

    print(f"\nTotal chunks to embed: {len(all_docs)}")

    embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")

    vectorstore = Chroma.from_documents(
        documents=all_docs,
        embedding=embeddings,
        persist_directory=PERSIST_DIR,
        collection_name="ehr_records",
    )

    print(f"Vector store built and persisted to: {PERSIST_DIR}")


if __name__ == "__main__":
    main()