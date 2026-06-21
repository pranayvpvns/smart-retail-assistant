import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

PROJECT_ROOT = os.path.abspath(
    os.path.join(CURRENT_DIR, "..", "..", "..")
)

BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")

sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, BACKEND_DIR)

from langchain_chroma import Chroma
from langchain_openai import AzureOpenAIEmbeddings
from langchain_core.documents import Document
from pymongo.database import Database
from app.config import get_settings

settings = get_settings()

# ── Embeddings client ─────────────────────────────────────────────────────────

def get_embeddings() -> AzureOpenAIEmbeddings:
    return AzureOpenAIEmbeddings(
        azure_deployment=settings.azure_openai_embedding_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
    )


# ── Vector store ──────────────────────────────────────────────────────────────

def get_vector_store(store_id: str) -> Chroma:
    """
    Returns a ChromaDB collection scoped to this store.
    Each store gets its own isolated collection.
    """
    return Chroma(
        collection_name=f"sales_{store_id}",
        embedding_function=get_embeddings(),
        persist_directory=settings.vector_db_path,
    )


# ── Ingestion ─────────────────────────────────────────────────────────────────

def _record_to_text(record: dict) -> str:
    """
    Converts a sales record dict into a human-readable text chunk
    that the embedding model can meaningfully encode.
    """
    parts = [
        f"Date: {record.get('date', 'unknown')}",
        f"Product: {record.get('product_name', record.get('product_id', 'unknown'))}",
        f"Product ID: {record.get('product_id', 'unknown')}",
        f"Category: {record.get('category', 'N/A')}",
        f"Quantity Sold: {record.get('quantity_sold', 0)} units",
        f"Revenue: ₹{record.get('revenue', 0)}",
        f"Stock Level: {record.get('stock_level', 'N/A')} units remaining",
        f"Cost: ₹{record.get('cost', 'N/A')} per unit",
    ]
    return " | ".join(parts)


def embed_sales_records(store_id: str, db: Database) -> dict:
    """
    Pulls all sales records from MongoDB, converts them to text chunks,
    embeds them and stores in ChromaDB.

    Safe to call multiple times — clears and rebuilds the collection.
    """
    records = list(
        db["sales_records"].find({"store_id": store_id}, {"_id": 0})
    )

    if not records:
        return {"success": False, "error": "No sales records found to embed"}

    # Build LangChain Document objects
    documents = []
    for record in records:
        text = _record_to_text(record)
        doc = Document(
            page_content=text,
            metadata={
                "date": str(record.get("date", "")),
                "product_id": str(record.get("product_id", "")),
                "store_id": store_id,
            },
        )
        documents.append(doc)

    # Clear existing collection and re-embed
    vector_store = get_vector_store(store_id)
    vector_store.reset_collection()
    vector_store.add_documents(documents)

    return {
        "success": True,
        "records_embedded": len(documents),
    }


def similarity_search(store_id: str, query: str, k: int = 5) -> list[str]:
    """
    Returns the top-k most relevant sales record chunks for a query.
    Used by agents to ground their responses in real data.
    """
    vector_store = get_vector_store(store_id)
    results = vector_store.similarity_search(query, k=k)
    return [doc.page_content for doc in results]