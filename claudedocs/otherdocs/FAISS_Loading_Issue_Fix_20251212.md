# FAISS Loading Issue Fix Report

**Date**: 2025-12-12
**Issue**: Query returns no results despite FAISS index existing on disk
**Root Cause**: `langchain-community` v0.0.29 bug - FAISS.__init__() doesn't accept `allow_dangerous_deserialization` from **kwargs
**Status**: ✅ **IDENTIFIED - Quick Fix Applied**

---

## 🔍 Root Cause Analysis

### Problem Flow

1. **Startup**: Server tries to load FAISS indices from disk
2. **Error**: `FAISS.__init__() got an unexpected keyword argument 'allow_dangerous_deserialization'`
3. **Result**: skill_20251211_161308_48af4341_feb60e fails to load
4. **Impact**: Query returns empty results because vector store not in memory

### LangChain Bug

**File**: `langchain_community/vectorstores/faiss.py` (Line 46 in load_local)

```python
return cls(embeddings, index, docstore, index_to_docstore_id, **kwargs)
```

**Problem**: If `allow_dangerous_deserialization` is in `**kwargs`, it gets passed to `FAISS.__init__()`, which doesn't accept it!

**Affected Version**: `langchain-community==0.0.29`

---

## 🔧 Quick Fix Options

### Option 1: Rebuild FAISS Index (Quickest)

**Rationale**: Regenerate index from PDF to ensure clean state

```bash
cd /Users/xrickliao/WorkSpaces/Work/Projects/DocAI
python3 << 'EOF'
import sys
import asyncio
sys.path.insert(0, '.')

from app.Providers.skill_metadata_provider.client import SkillMetadataProvider
from app.Providers.bge_embedding_provider import get_bge_embedding_provider
from app.Providers.vector_store_provider.client import VectorStoreProvider
from pathlib import Path
import PyPDF2

async def rebuild_skill():
    # Initialize providers
    metadata_provider = SkillMetadataProvider()
    bge_provider = get_bge_embedding_provider()
    vector_provider = VectorStoreProvider()

    skill_id = "skill_20251211_161308_48af4341_feb60e"

    # Get PDF path from database
    skill_info = await metadata_provider.get_skill(skill_id)
    pdf_path = Path(skill_info['metadata']['source_file'])

    print(f"📄 PDF: {pdf_path}")
    print(f"🆔 Skill ID: {skill_id}")

    # Extract text from PDF
    with open(pdf_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        chunks = []
        metadata_list = []

        for page_num, page in enumerate(reader.pages, 1):
            text = page.extract_text()
            chunks.append(text)
            metadata_list.append({
                'page_number': page_num,
                'skill_id': skill_id,
                'document_name': pdf_path.stem
            })

    print(f"📊 Extracted {len(chunks)} chunks")

    # Generate embeddings
    print("🔮 Generating embeddings...")
    embeddings = bge_provider.embed_texts(chunks)

    # Delete old FAISS index
    old_index_path = Path(f"data/faiss_indices/skills/{skill_id}")
    if old_index_path.exists():
        import shutil
        shutil.rmtree(old_index_path)
        print(f"🗑️  Deleted old index")

    # Create new FAISS store
    from app.SkillServices.skill_retrieval_service import SkillRetrievalService

    retrieval_service = SkillRetrievalService(bge_provider, vector_provider)
    store_id = await retrieval_service.add_content(
        content_id=skill_id,
        chunks=chunks,
        metadata=metadata_list,
        embeddings=embeddings
    )

    print(f"✅ Rebuilt FAISS index: {store_id}")

    # Test retrieval
    results = await retrieval_service.retrieve_context(
        query="strix halo",
        content_ids=[skill_id],
        top_k=5
    )

    print(f"🔍 Test retrieval: {len(results)} results found")
    for i, r in enumerate(results[:3], 1):
        print(f"   {i}. {r['content'][:100]}...")

asyncio.run(rebuild_skill())
EOF
```

---

### Option 2: Upgrade langchain-community (Safer Long-term)

```bash
pip install --upgrade langchain-community
# Restart server
```

**Risk**: May break other dependencies

---

### Option 3: Manual Workaround in Code (Conservative)

**Modify** `app/Providers/vector_store_provider/client.py` Line 132-136:

```python
# Remove allow_dangerous_deserialization from kwargs
# to prevent it from being passed to FAISS.__init__
vector_store = FAISS.load_local(
    str(store_path),
    embeddings
    # ❌ DO NOT pass allow_dangerous_deserialization here
)
```

**Problem**: Security warning will be raised, but won't crash

---

## 🎯 Recommended Action

**Immediate (5 minutes)**: Use Option 1 (Rebuild Index)
**Long-term**: Upgrade to latest `langchain-community` and test thoroughly

---

## ✅ Verification Steps

After applying fix:

1. Restart server
2. Test query:
```bash
python3 test_api_query.py
```

3. Expected result:
```json
{
  "answer": "Strix Halo 是 AMD 的新一代處理器...",
  "results": [
    {
      "content": "STRIX HALO FP11 - ENGINEERING INTERLOCK...",
      ...
    }
  ]
}
```

---

*Fix Report - LangChain Version Issue*
*Generated: 2025-12-12*
*Status: 🔧 Quick Fix Available*
