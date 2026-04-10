# KnowledgeLM
KnowledgeLM is an enterprise AI knowledge system that transforms internal company data into an intelligent, queryable assistant.

## 🚀 What it does
- Convert internal documents (PDF, Word, DB) into AI knowledge
- Enable natural language querying
- Generate reports and answers automatically
- Reduce onboarding and operational costs

## 💼 Use Cases
- Internal knowledge base (SOP, documentation)
- Customer support automation
- Employee training assistant
- Report generation

## 🧠 Tech Stack
- LLM (Ollama / OpenAI-compatible)
- RAG architecture
- Vector database (Milvus / FAISS)
- Backend (FastAPI)

## 🎯 Value
Turn your company's data into a usable AI asset.

## 📖 Overview

KnowledgeLM implements a **Dual RAG Architecture**, running two parallel systems to support different use cases:

1.  **Skill-Based RAG (New Architecture):**
    * Focuses on curated "Skills" (Knowledge Domains) combining multiple source files.
    * Uses **FAISS** for lightweight, physically isolated vector indices.
    * Managed via **SQLite** with a "Single Source of Truth" design (`skill_heads`).
    * optimized for precise, domain-specific Q&A.

2.  **File-Based RAG (Legacy System):**
    * Focuses on individual, searchable PDF files.
    * Uses **Milvus** for high-performance vector storage.
    * Features a complex 5-Phase OPMP pipeline with SSE streaming.

## 🚀 Key Features

* **Local Processing:** Powered by local LLMs (Ollama) and OpenAI integration.
* **Dual Vector Stores:** Leverages both **Milvus** (Global/File) and **FAISS** (Local/Skill) for optimal performance.
* **Smart Ingestion Pipeline:**
    * Automatic PDF text extraction (PyPDF2).
    * Smart chunking (~1000 chars with overlap).
    * High-dimensional embeddings using `BAAI/bge-m3` (1024-dim).
* **Architecture Patterns:**
    * **Layered Architecture:** Clear separation between API, Services, and Providers.
    * **Single Source of Truth:** `skill_heads` table eliminates sync issues between JSON configs and DB.
    * **Hybrid Data Models:** Uses `TypedDict` for high-performance internal data transfer and `Pydantic` for robust API validation.

## 🛠️ Technology Stack

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Backend** | Python 3.11, FastAPI | API server & Async processing |
| **Vector DB (Skill)** | FAISS | Lightweight, file-based indices |
| **Vector DB (File)** | Milvus | Legacy high-performance search |
| **Metadata DB** | SQLite | Skill definitions & relationships |
| **Embeddings** | BAAI/bge-m3 | Multilingual 1024-dim embeddings |
| **LLM** | Ollama / OpenAI | Response generation |
| **Frontend** | Vanilla JS + Jinja2 | User Interface |

## 📂 Project Structure

```text
DOCAI/
├── app/
│   ├── api/v1/endpoints/    # FastAPI route handlers
│   ├── models/              # Pydantic & TypedDict definitions
│   ├── Providers/           # Infrastructure layer (DB, Vector, LLM)
│   ├── Services/            # Business logic (File-based RAG)
│   └── SkillServices/       # Business logic (Skill-based RAG)
├── data/
│   ├── faiss_indices/       # Physical FAISS vector stores
│   ├── files/               # Raw PDF sources
│   ├── skills/              # Skill-specific data
│   ├── docai.db             # Legacy file metadata
│   └── skill_metadata.db    # New SQLite skill architecture
└── template/                # HTML/Jinja2 templates
