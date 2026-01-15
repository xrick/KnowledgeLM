<!-- refData/todo/確保overview一定產生.md -->
💡 問題 1: 如何確保 Overview 一定產生？
方案 A: 修改 upload.py 的錯誤處理
目標：即使 LLM 失敗，也要存入 fallback overview
# 建議修改 upload.py
if overview_service:
    try:
        overview = await overview_service.generate_overview(
            file_id=file_id,
            chunks=chunk_texts,
            filename=filename
        )
    except Exception as e:
        logger.warning(f"Overview generation failed: {e}")
        # ★ 關鍵: 生成 fallback overview
        overview = f"文檔: {filename}\n\n[概述生成失敗，請查看原文檔]"
    
    # ★ 無論成功或失敗都存入
    try:
        await overview_service.store_overview(
            file_metadata_provider=file_metadata_provider,
            file_id=file_id,
            overview=overview
        )
    except Exception as store_error:
        logger.error(f"Failed to store overview: {store_error}")
方案 B: 修改 generate_overview() 內部
現狀：內部 try-catch 已經有 fallback
except Exception as e:
    logger.error(f"Failed to generate overview for {file_id}: {str(e)}")
    # Return a basic overview on error
    return f"文檔: {filename}\n\n[概述生成失敗，請查看原文檔]"
問題：這個 fallback 只在內部異常時觸發，外部呼叫方的 try-catch 會在傳輸/網路錯誤時攔截
方案 C: 雙重保險（推薦）
# 在 upload.py 中
overview = None
if overview_service:
    try:
        overview = await overview_service.generate_overview(...)
    except Exception as e:
        logger.warning(f"Overview generation failed: {e}")

# 如果沒有 overview，使用簡單 fallback
if not overview or not overview.strip():
    overview = f"文檔: {filename}\n\n" + "\n".join(chunk_texts[:3])[:500]
    logger.info(f"Using simple fallback overview for {file_id}")

# 一定要存入
await overview_service.store_overview(
    file_metadata_provider=file_metadata_provider,
    file_id=file_id,
    overview=overview
)