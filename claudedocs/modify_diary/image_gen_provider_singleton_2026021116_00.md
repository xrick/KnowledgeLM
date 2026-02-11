# 修改日記: Image Generation Provider Singleton 實作

**日期時間**: 2026-02-11 16:00
**修改者**: Claude (SuperClaude Framework)
**風險等級**: 🟢 低

## 修改摘要
新增 `image_gen_provider` 模組，以 Singleton 模式管理 SSD-1B (StableDiffusionXL) pipeline，遵循現有 `llm_provider` 架構模式。

## 修改檔案
| 檔案 | 變更類型 | 說明 |
|------|----------|------|
| app/Providers/image_gen_provider/__init__.py | 新增 | 模組匯出定義 |
| app/Providers/image_gen_provider/client.py | 新增 | ImageGenClient - pipeline wrapper，處理模型載入與推理 |
| app/Providers/image_gen_provider/manager.py | 新增 | ImageGenManager - Singleton manager，threading.Lock thread-safe |

## 為什麼需要新建檔案
現有 10 個 Provider 全為 NLP/文本相關（LLM、embedding、rerank、ASR、cache、vector_store 等），圖像生成是完全不同的 domain，無法擴展任何現有 Provider。

## 架構對照
| 元素 | LLMManager | ImageGenManager |
|------|------------|-----------------|
| Singleton 機制 | `__new__` + `_initialized` | 相同 |
| Lock 類型 | `asyncio.Lock` (async HTTP) | `threading.Lock` (sync torch) |
| Lazy loading | `get_client()` | `get_client()` |
| 資源釋放 | `shutdown()` | `shutdown()` / `release()` |
| DI factory | `get_llm_manager()` | `get_image_gen_manager()` |

## 影響分析
- 影響範圍: 無 - 純新增模組，不影響現有功能
- 向後相容: 是
- 需要測試: 需安裝 `diffusers` 和 CUDA 環境

## 回滾方案
```bash
rm -rf app/Providers/image_gen_provider/
```

## 驗證結果
- [x] 遵循 LLMManager Singleton 模式
- [x] Thread-safe (double-checked locking)
- [x] Lazy loading (首次 generate 時才載入模型)
- [x] 提供 release/shutdown 釋放 VRAM
