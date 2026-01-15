# Chunk Size & Stability Analysis

**Date**: 2025-12-11
**Issue**: 用戶詢問改變 chunk size 是否能減少 FAISS index 錯誤
**Status**: Analysis Complete - Root Cause Identified

---

## 問題重述

**用戶問題**：
> 如果把一次要chunk的頁數由12改成6，會減小生成faiss index的錯誤嗎？同時能增加穩定性嗎？

---

## 核心發現

### ❌ **錯誤假設**
用戶假設系統使用「12頁一個chunk」的策略。

### ✅ **實際實作**
當前系統使用 **page-based chunking**：
```python
# app/api/v1/endpoints/skills.py Lines 860-882
for page_num, page_text in enumerate(pages, 1):
    chunk_id = f"{skill_id}_{doc_id}_p{page_num}"
    # ... create chunk metadata ...

    # ⚠️ 1 page = 1 chunk = 1 embedding
    embedding = embedding_provider.embed_single(page_text)
    all_embeddings.append(embedding)
```

**結論**：系統已經是「1頁 = 1 chunk」，不存在「12頁一個chunk」的設定。

---

## 根本問題分析

### Gorgon Point 案例回顧

| 階段 | 預期 | 實際 | 完成率 |
|------|------|------|--------|
| PDF 提取 | 65 pages | 65 pages ✅ | 100% |
| Chunk 創建 | 65 chunks | 65 chunks ✅ | 100% |
| **Embedding 生成** | 65 embeddings | **5 embeddings ❌** | **7.7%** |
| FAISS 儲存 | 65 vectors | 5 vectors ❌ | 7.7% |

### 失敗位置

**檔案**：`app/api/v1/endpoints/skills.py`
**行數**：Lines 880-882

```python
# ❌ 問題代碼：沒有錯誤處理！
for page_num, page_text in enumerate(pages, 1):
    embedding = embedding_provider.embed_single(page_text)  # 可能 timeout/fail
    all_embeddings.append(embedding)  # 失敗後不會執行到這裡
```

### 推測失敗原因

1. **BGE-M3 Timeout**
   - Model inference 超時（尤其是長文本）
   - GPU memory exhaustion
   - Network issues (如果是遠端 API)

2. **Silent Failure**
   - 沒有 try-except 捕獲異常
   - Loop 中途崩潰，已生成的 embeddings 可能未儲存

3. **Memory Pressure**
   - 65 個 1024-dim embeddings = ~260KB raw data
   - 加上原文 chunks，可能導致記憶體壓力

4. **No Retry Mechanism**
   - 單次失敗即放棄
   - 沒有 exponential backoff 或重試邏輯

---

## 💡 改進方案

### 方案 1：Batch Embedding with Retry (推薦)

**優點**：
- 批次處理提升效率
- 自動重試機制增強穩定性
- 詳細錯誤日誌便於追蹤

**實作**：

```python
async def process_pdf_for_skill_with_retry(
    pdf_path: Path,
    skill_name: str,
    batch_size: int = 10,  # 每批處理 10 頁
    max_retries: int = 3
) -> Dict[str, Any]:
    """
    Process PDF with batch embedding and retry logic

    Args:
        batch_size: Number of pages to embed in one batch
        max_retries: Maximum retry attempts per batch
    """

    # ... (前面的 PDF extraction 保持不變) ...

    # ========== PHASE 4: Batch Embedding with Retry ==========
    all_embeddings = []

    for i in range(0, len(all_chunks), batch_size):
        batch_chunks = all_chunks[i:i+batch_size]
        batch_texts = [chunk['content'] for chunk in batch_chunks]

        retry_count = 0
        batch_embeddings = None

        while retry_count < max_retries:
            try:
                logger.info(
                    f"Processing batch {i//batch_size + 1}/{(len(all_chunks) + batch_size - 1)//batch_size}: "
                    f"chunks {i}-{min(i+batch_size, len(all_chunks))}"
                )

                # Batch embedding generation
                batch_embeddings = await embedding_provider.embed_batch(batch_texts)

                logger.info(f"✅ Batch embedding successful: {len(batch_embeddings)} embeddings generated")
                break  # Success, exit retry loop

            except Exception as e:
                retry_count += 1
                logger.error(
                    f"❌ Batch embedding failed (attempt {retry_count}/{max_retries}): {str(e)}"
                )

                if retry_count >= max_retries:
                    # Final retry failed - mark as failed and raise
                    await metadata_provider.update_processing_status(
                        skill_id=skill_id,
                        status="failed",
                        indexed_chunks=len(all_embeddings),  # Chunks successfully embedded so far
                        error=f"Embedding generation failed at chunk {i}: {str(e)}"
                    )
                    raise HTTPException(
                        status_code=500,
                        detail=f"Embedding generation failed after {max_retries} retries: {str(e)}"
                    )

                # Wait before retry (exponential backoff)
                await asyncio.sleep(2 ** retry_count)

        all_embeddings.extend(batch_embeddings)

        # Update progress
        await metadata_provider.update_processing_status(
            skill_id=skill_id,
            status="processing",
            indexed_chunks=len(all_embeddings)
        )

    logger.info(f"✅ All embeddings generated: {len(all_embeddings)} total")

    # ... (後續 FAISS 儲存保持不變) ...
```

**關鍵改進**：

| Feature | Before | After |
|---------|--------|-------|
| **處理方式** | 逐頁處理 | 批次處理 (10頁/batch) |
| **錯誤處理** | ❌ 無 | ✅ try-except with retry |
| **重試機制** | ❌ 無 | ✅ Exponential backoff (3 retries) |
| **進度追蹤** | ❌ 無 | ✅ 每批更新 database |
| **錯誤日誌** | ❌ Silent failure | ✅ 詳細記錄失敗位置 |

---

### 方案 2：Parallel Embedding (高階)

**適用場景**：大量 PDF 處理，需要極致效能

**實作**：

```python
import asyncio

async def embed_with_semaphore(text: str, semaphore: asyncio.Semaphore):
    """Embed with concurrency control"""
    async with semaphore:
        return await embedding_provider.embed_single(text)

async def process_pdf_parallel(pdf_path: Path, max_concurrent: int = 5):
    """Process PDF with parallel embedding generation"""

    # ... (extraction phase) ...

    # Create semaphore to limit concurrency
    semaphore = asyncio.Semaphore(max_concurrent)

    # Parallel embedding generation
    tasks = [
        embed_with_semaphore(chunk['content'], semaphore)
        for chunk in all_chunks
    ]

    all_embeddings = await asyncio.gather(*tasks, return_exceptions=True)

    # Check for failures
    failed_indices = [
        i for i, emb in enumerate(all_embeddings)
        if isinstance(emb, Exception)
    ]

    if failed_indices:
        logger.error(f"❌ Failed to embed chunks: {failed_indices}")
        # Retry failed chunks...
```

---

### 方案 3：Progressive Saving (最保險)

**概念**：每生成一批 embeddings 就立即儲存到 FAISS

**好處**：
- 即使中途失敗，已處理的部分仍然保留
- 可以從失敗點續傳

**實作**：

```python
async def process_pdf_progressive(pdf_path: Path, checkpoint_interval: int = 20):
    """Process PDF with progressive FAISS saving"""

    # ... (extraction phase) ...

    for i in range(0, len(all_chunks), checkpoint_interval):
        batch = all_chunks[i:i+checkpoint_interval]

        # Generate embeddings for this batch
        batch_embeddings = await embed_batch(batch)

        # ✅ Immediately save to FAISS (incremental)
        await skill_ingestion_service.add_content_incremental(
            content_id=skill_id,
            chunks=batch,
            embeddings=batch_embeddings
        )

        logger.info(f"✅ Checkpoint saved: {i+len(batch)}/{len(all_chunks)} chunks")

        # Update database progress
        await metadata_provider.update_processing_status(
            skill_id=skill_id,
            status="processing",
            indexed_chunks=i+len(batch)
        )
```

---

## 📊 效能對比

| 方案 | 速度 | 穩定性 | 記憶體 | 實作難度 |
|------|------|--------|--------|----------|
| **Current (逐頁)** | ⭐⭐ | ⭐ | ⭐⭐⭐ | ⭐ |
| **Batch + Retry** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ |
| **Parallel** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |
| **Progressive** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |

---

## 🎯 推薦方案

**For Demo (短期)**：
- 使用 **方案 1 (Batch + Retry)**
- Batch size = 10
- Max retries = 3
- Exponential backoff

**For Production (長期)**：
- 結合 **方案 1 + 方案 3**
- Batch embedding with retry
- Progressive FAISS saving (每 20 chunks checkpoint)
- 完整錯誤追蹤與恢復機制

---

## 🔗 Related Files

**需要修改**：
- `app/api/v1/endpoints/skills.py` (Lines 860-890)
- `app/Providers/embedding_provider/client.py` (新增 `embed_batch()` method)
- `app/SkillServices/skill_ingestion_service.py` (新增 incremental save support)

**已完成**：
- ✅ Index integrity verification system
- ✅ Background integrity checker
- ✅ Progress tracking in database

---

## 結論

**回答用戶問題**：

1. **改變 chunk 大小不會減少錯誤**
   - 當前系統已經是 1 page = 1 chunk（最小粒度）
   - 問題不在 chunking，而在 **embedding 生成循環的錯誤處理**

2. **如何增加穩定性**：
   - ✅ 實作 **Batch Embedding with Retry**
   - ✅ 添加 **Exponential Backoff**
   - ✅ 實作 **Progressive Saving** (checkpoint 機制)
   - ✅ 已有 **Index Integrity Verification** 系統

**優先級**：
- 🔴 HIGH: Batch embedding with retry (防止 silent failure)
- 🟡 MEDIUM: Progressive saving (防止資料遺失)
- 🟢 LOW: Parallel embedding (效能優化)

---

*Last Updated: 2025-12-11*
*Status: Analysis Complete - Implementation Ready*
