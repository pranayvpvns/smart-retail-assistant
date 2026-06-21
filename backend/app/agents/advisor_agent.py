import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

PROJECT_ROOT = os.path.abspath(
    os.path.join(CURRENT_DIR, "..", "..", "..")
)

BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")

sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, BACKEND_DIR)

from langchain_openai import AzureChatOpenAI
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    AIMessage,
)
from app.config import get_settings
from app.agents.data_agent import run_data_agent
from app.agents.ml_agent import run_ml_agent
from pymongo.database import Database

settings = get_settings()


def get_llm() -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_deployment=settings.azure_openai_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        temperature=0.4,     # slightly higher — creative synthesis
        max_tokens=600,
    )


def run_advisor_agent(
    query: str,
    store_id: str,
    db: Database,
    data_insight: str,
    ml_insight: str,
) -> str:
    """
    Business Advisor Agent — synthesizes data + ML insights into
    one clear, actionable recommendation for the store owner.

    data_insight and ml_insight are pre-computed by the orchestrator
    to avoid double API calls.
    """
    llm = get_llm()

    system_prompt = """You are a Business Advisor Agent for a retail store owner.
You receive insights from two specialist agents — a Data Analyst and an ML expert.
Your job is to synthesize their outputs into ONE clear business recommendation.

Rules:
- Write for a non-technical store owner. No jargon.
- Give a concrete action: what to order, what to watch, what to promote.
- Keep it to 3-4 sentences maximum.
- Start with the most urgent action first.
- Use ₹ for currency figures.
"""

    user_prompt = f"""Original Question: {query}

Data Analyst says:
{data_insight}

ML Insight Agent says:
{ml_insight}

Synthesize both into one actionable recommendation for the store owner:"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    response = llm.invoke(messages)
    return response.content.strip()