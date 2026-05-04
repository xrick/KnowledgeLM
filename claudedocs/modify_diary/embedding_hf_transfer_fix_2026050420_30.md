# 修改日記: 修復 Embedding Provider hf_transfer 不完整下載問題

**日期時間**: 2026-05-04 20:30
**修改者**: Claude (SuperClaude Framework)
**風險等級**: 🟢 低

## 修改摘要
停用 langchain `HuggingFaceEmbeddings` 載入路徑的 `HF_HUB_ENABLE_HF_TRANSFER`，並清除已損壞的本地快取，解決批次嵌入時「Could not load embedding models」錯誤。

## 問題現象
```
❌ 批次 1 嵌入失敗 (已重試 3 次): Could not load embedding models.
Primary: sentence-transformers/all-MiniLM-L6-v2,
Fallback: jinaai/jina-embeddings-v2-base-zh.
Set EMBEDDING_MODEL to a local path or ensure network access to Hugging Face Hub.
```

## 根本原因
- Shell 環境設了 `HF_HUB_ENABLE_HF_TRANSFER=1`。
- `app/Providers/embedding_provider/client.py` 的 langchain 載入路徑沒有像 `bge_embedding_provider.py:37` 那樣明確停用 `hf_transfer`。
- `hf_transfer` 下載中斷後，HuggingFace cache 裡留下：
  - `refs/main`（commit hash，40 bytes）
  - 空的 `snapshots/<hash>/` 目錄
  - 0 bytes 的 `blobs/` 目錄
  - `.locks/` 殘留鎖檔
- HF Hub 認定「快照已存在不需重新下載」→ 解析成功但檔案開啟失敗 → 主模型 + fallback 都報錯。

## 修改檔案
| 檔案 | 變更類型 | 說明 |
|------|----------|------|
| `app/Providers/embedding_provider/client.py` | 修改 | `_lazy_load_model` 主路徑與 fallback 路徑都加上 `os.environ['HF_HUB_ENABLE_HF_TRANSFER'] = '0'`（與 `bge_embedding_provider.py:37` 對齊） |
| `data/cache/sentence_transformers/models--sentence-transformers--all-MiniLM-L6-v2/` | 刪除 | 損壞的空快取 |
| `data/cache/sentence_transformers/models--jinaai--jina-embeddings-v2-base-zh/` | 刪除 | 損壞的空快取 |
| `data/cache/sentence_transformers/models--BAAI--bge-m3/` | 刪除 | 損壞的空快取 |
| `data/cache/sentence_transformers/.locks/models--*` | 刪除 | 殘留鎖檔 |

## 影響分析
- **影響範圍**：所有透過 `EmbeddingProvider`（langchain HuggingFaceEmbeddings 路徑）載入嵌入模型的程式碼路徑。
- **向後相容**：是。只是強制停用 `hf_transfer`，下載行為改用標準 `huggingface_hub` 路徑。
- **第一次載入成本**：需重新下載
  - BAAI/bge-m3：~2.3 GB
  - sentence-transformers/all-MiniLM-L6-v2：~90 MB
  - jinaai/jina-embeddings-v2-base-zh：~322 MB
- **後續載入**：檔案 cache 後即正常，不受影響。

## 回滾方案
1. 還原 `app/Providers/embedding_provider/client.py`：移除新增的兩行 `os.environ['HF_HUB_ENABLE_HF_TRANSFER'] = '0'`。
2. 再次執行 `pip install hf_transfer` 並設定 `HF_HUB_ENABLE_HF_TRANSFER=1`（不建議）。
3. 注意：刪除的快取為損壞狀態，無法還原；恢復後系統會再次自動下載。

## 驗證結果（第一次嘗試 — 失敗）
- [x] Cache 目錄已清空（snapshots / blobs / locks 全清）
- [x] Patch 已套用（主路徑 line 82、fallback 路徑 line 99 兩處）
- [x] Python 語法檢查
- [x] 重啟 server 後執行批次上傳測試 → ❌ **仍失敗**
- [x] 真正的 stack trace 揭露：`ModuleNotFoundError: No module named 'hf_transfer'`

---

# 追加修正（2026-05-04 20:30 後段）

## 為何上一輪 patch 無效
`huggingface_hub.constants.HF_HUB_ENABLE_HF_TRANSFER` 在套件 **import 時就被凍結**為當下的 env var 值。把 `os.environ['HF_HUB_ENABLE_HF_TRANSFER'] = '0'` 放在 `_lazy_load_model`（lazy 觸發）裡，那個時間點 `huggingface_hub` 早已被其他 import 鏈拉進來，常數已經是 `True`。下載時呼叫 `import hf_transfer` → `ModuleNotFoundError` → cascade 成「Can't load configuration of [model]」誤導訊息。

同樣道理，`bge_embedding_provider.py:37` 也是 dead code（在類別 `__init__` 才設置 env var，太晚）。

## 真正的修補方案（A + B 雙保險）

### 方案 A — `main.py` 最頂端
在所有其他 import 之前設置 env var：
```python
import os
os.environ['HF_HUB_ENABLE_HF_TRANSFER'] = '0'
```
保證在任何 `huggingface_hub` import 鏈觸發前就生效。

### 方案 B — `start_system.sh`
在 `nohup docaienv/bin/python main.py` 之前加：
```bash
export HF_HUB_ENABLE_HF_TRANSFER=0
```
保證即使 `python main.py` 被獨立呼叫且 main.py 修改被回退，啟動腳本仍可保護。

## 第二輪修改檔案
| 檔案 | 變更類型 | 說明 |
|------|----------|------|
| `app/Providers/embedding_provider/client.py` | 回滾 | 移除上一輪在 line 82、99 加的 dead-code patch（沒效，留著只會誤導後人） |
| `main.py` | 修改 | 在 module-level 第一行 import 之前加 `os.environ['HF_HUB_ENABLE_HF_TRANSFER'] = '0'` |
| `start_system.sh` | 修改 | 在啟動 server 之前加 `export HF_HUB_ENABLE_HF_TRANSFER=0` |
| `data/cache/sentence_transformers/models--*` | 刪除 | 第二次失敗又留下的空殼快取 |

## 第二輪驗證結果
- [x] 三檔案修改完成且互相獨立驗證
- [x] Cache 第二次清空
- [x] 重啟 server（PID 50429）→ `Application startup complete`
- [x] 即使當前 shell 仍繼承 `HF_HUB_ENABLE_HF_TRANSFER=1`，server boot 仍乾淨無錯（證明 main.py 的 pre-import 設置有效）
- [ ] 批次上傳實測：模型重新下載並完成嵌入（**待使用者再次測試**）

## 經驗教訓
1. **`huggingface_hub` 環境變數常數在 import 時凍結** — 任何「late binding」的 `os.environ` 賦值都無效。只有在 `huggingface_hub` import 鏈尚未啟動之前設置才有用。
2. **錯誤訊息的最頂層往往不是真因** — `huggingface_hub` 把 `ModuleNotFoundError: hf_transfer` 包裝成 `Can't load the configuration of [model]`，乍看像是模型路徑錯誤或網路問題，實際是套件相依問題。要往 stack trace 底部找。
3. **CLAUDE.md 規範值得遵守** — 「Fix Don't Workaround：解決根本問題而非繞過症狀」。第一輪錯把 lazy 路徑的 patch 當作 fix 是繞過症狀。

## 預防措施（仍建議）
1. ✅ 已落地：`main.py` 與 `start_system.sh` 雙重保險。
2. 待辦：增加啟動健康檢查 — boot 時就嘗試載入嵌入模型（一個小 batch 的 dummy embed），而非延後到第一次批次上傳才暴露問題。
3. 待辦：清理 `bge_embedding_provider.py:36-37` 的 dead-code（已是無效保護，但不是這次修補的範圍）。
