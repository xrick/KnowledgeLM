# refData/Codes/process_more_than_two_files.py
# 在 rag_engine.py 中新增

def multi_file_summarize(self, query, target_files):
    """
    target_files: list of strings, e.g. ["A.pdf", "B.pdf", "C.pdf"]
    query: 使用者的問題，例如 "比較理賠上限"
    """
    print(f"正在進行多文件綜合摘要，目標文件數: {len(target_files)}")
    
    aggregated_chunks = []

    # --- 階段一：分進 (Map) ---
    # 強制讓每一份文件都有機會被檢索到
    for file_name in target_files:
        print(f" -> 正在檢索文件: {file_name} ...")
        
        # 1. Milvus 搜尋 (帶有 filter)
        # 使用 expr 鎖定特定檔名
        search_params = {"metric_type": "COSINE", "params": {"nprobe": 10}}
        
        # 注意：這裡假設 Milvus 裡有存 'file_name' 這個 scalar field
        filter_expr = f'file_name == "{file_name}"'
        
        query_vector = self.embed_model.encode([query])[0].tolist()
        
        results = self.db.milvus_col.search(
            data=[query_vector], 
            anns_field="embedding", 
            param=search_params, 
            limit=3, # 每份文件只取最精華的 3 個片段
            expr=filter_expr, # ★關鍵：只搜這份文件
            output_fields=["chunk_text", "page_number"]
        )

        # 2. 收集結果
        for hits in results:
            for hit in hits:
                aggregated_chunks.append({
                    "text": hit.entity.get("chunk_text"),
                    "file_name": file_name,
                    "page": hit.entity.get("page_number"),
                    "score": hit.score
                })

    # --- 階段二：過濾與重排序 (Rerank) ---
    # 現在 aggregated_chunks 裡面可能有 3份文件 * 3片段 = 9 個片段
    # 我們把它們全部丟進 BGE-Rerank 再洗牌一次，確保最準的排前面
    print(f" -> 彙整共 {len(aggregated_chunks)} 個片段，進行 Rerank...")
    
    pairs = [[query, doc['text']] for doc in aggregated_chunks]
    scores = self.reranker.predict(pairs)
    
    # 更新分數並排序
    for i, score in enumerate(scores):
        aggregated_chunks[i]['rerank_score'] = score
        
    # 取出前 Top K (例如總共取 5~6 個片段，避免 Context 太長)
    final_docs = sorted(aggregated_chunks, key=lambda x: x['rerank_score'], reverse=True)[:6]

    # --- 階段三：合擊 (Reduce / Synthesis) ---
    # 組裝特殊的 Prompt
    context_str = ""
    for doc in final_docs:
        context_str += f"【文件：{doc['file_name']} (第{doc['page']}頁)】\n{doc['text']}\n\n"

    final_prompt = f"""
你是一個專業的分析師。請根據以下來自多份文件的資料，針對問題進行「綜合比較與摘要」。

【重要規則】：
1. 請不要分別摘要每一份文件，請嘗試將它們的資訊「融合」在一起。
2. 如果可以，請使用「表格」或「條列式」呈現不同文件之間的差異。
3. 清楚標示資訊來源。

【參考資料集】：
{context_str}

【使用者問題】：
{query}
"""
    
    # 呼叫 Ollama
    response = self.ollama_client.chat(model=OLLAMA_MODEL, messages=[
        {'role': 'user', 'content': final_prompt},
    ])
    
    return response['message']['content']
    