"""
llm_client.py
Shared Gemini client configuration used by every agent.

Centralizing this means: (1) temperature/model choices are documented in one
place with rationale, (2) swapping models later only touches this file.
"""
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


def get_llm(temperature: float, agent_name: str = "unnamed") -> ChatGoogleGenerativeAI:
    """
    Returns a configured Gemini chat model.

    Temperature is passed explicitly per-agent rather than defaulted, because
    the right temperature differs meaningfully by role:
      - Triage / EHR / Anamnesis (extraction-heavy, need consistency): low temp (0.0-0.2)
      - Synthesis (reasoning over multiple sources, more language variation): slightly higher (0.2-0.3)

    Documented rationale per-agent lives in each agent's own module, not here --
    this function just enforces that every agent must consciously pick a value.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key or api_key == "your-gemini-api-key-here":
        raise RuntimeError(
            f"[{agent_name}] GOOGLE_API_KEY is not set. Copy .env.example to .env "
            f"and add your real Gemini API key before running agents."
        )

    return ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        temperature=temperature,
        google_api_key=api_key,
    )