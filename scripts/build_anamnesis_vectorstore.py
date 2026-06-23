"""
build_anamnesis_vectorstore.py

Chunks and embeds all patient anamnesis records into a persistent ChromaDB store.

Chunking strategy differs from EHR: anamnesis intake forms are narrative and
semi-structured (chief complaint, HPI, ROS, social/family history all in one
coherent patient story), so we chunk the intake form as ONE unit per patient
rather than splitting every field -- splitting "patient stopped her pill because
of a cough" across three disconnected chunks would destroy the very narrative
thread the Anamnesis Agent needs to interpret. Symptom diary entries and the
adherence log each get their own chunks since those are naturally separate,
timestamped, atomic facts.

Run from project root: python3 -m scripts.build_anamnesis_vectorstore
"""
import json
import os
import shutil
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_core.documents import Document
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "anamnesis")
PERSIST_DIR = os.path.join(os.path.dirname(__file__), "..", "chroma_db", "anamnesis")


def patient_anamnesis_to_documents(anamnesis: dict) -> list[Document]:
    pid = anamnesis["patient_id"]
    docs = []

    # Intake form -- ONE chunk, kept as a coherent narrative.
    intake = anamnesis["intake_form"]
    intake_text = (
        f"Patient {pid} intake form:\n"
        f"Chief complaint: {intake['chief_complaint']}\n"
        f"History of present illness: {intake['history_of_present_illness']}\n"
        f"Review of systems: {intake['review_of_systems']}\n"
        f"Social history: {intake['social_history']}\n"
        f"Family history: {intake['family_history']}"
    )
    docs.append(Document(
        page_content=intake_text,
        metadata={"patient_id": pid, "section": "intake_form"},
    ))

    # Symptom diary -- one chunk per entry (these are timestamped, atomic)
    for i, entry in enumerate(anamnesis.get("symptom_diary", [])):
        diary_text = f"Patient {pid} symptom diary entry ({entry['date']}): {entry['entry']}"
        docs.append(Document(
            page_content=diary_text,
            metadata={"patient_id": pid, "section": "symptom_diary", "entry_index": i},
        ))

    # Medication adherence log -- one chunk for the whole log (usually short,
    # and adherence across meds is often read together)
    adherence = anamnesis.get("medication_adherence_log", [])
    if adherence:
        adherence_lines = []
        for a in adherence:
            pct = a.get("adherence_pct")
            pct_str = f"{pct}%" if pct is not None else "unknown/unconfirmed"
            line = f"- {a['medication']}: adherence {pct_str}"
            if a.get("note"):
                line += f" -- {a['note']}"
            adherence_lines.append(line)
        adherence_text = f"Patient {pid} medication adherence log:\n" + "\n".join(adherence_lines)
        docs.append(Document(
            page_content=adherence_text,
            metadata={"patient_id": pid, "section": "adherence_log"},
        ))

    return docs


def main():
    if os.path.exists(PERSIST_DIR):
        shutil.rmtree(PERSIST_DIR)
    os.makedirs(PERSIST_DIR, exist_ok=True)

    all_docs = []
    for fname in sorted(os.listdir(DATA_DIR)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(DATA_DIR, fname)) as f:
            anamnesis = json.load(f)
        docs = patient_anamnesis_to_documents(anamnesis)
        all_docs.extend(docs)
        print(f"  {anamnesis['patient_id']}: {len(docs)} chunks")

    print(f"\nTotal chunks to embed: {len(all_docs)}")

    embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001")

    vectorstore = Chroma.from_documents(
        documents=all_docs,
        embedding=embeddings,
        persist_directory=PERSIST_DIR,
        collection_name="anamnesis_records",
    )

    print(f"Vector store built and persisted to: {PERSIST_DIR}")


if __name__ == "__main__":
    main()