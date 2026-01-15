# FAISS + NumPy 版本衝突修復報告

## 問題日期：2024-11-23

---

## 1. 問題描述

### 錯誤訊息

**前端**：
```
上傳失敗：Failed to process file: Could not import faiss python package.
Please install it with `pip install faiss-gpu` (for CUDA supported GPU)
or `pip install faiss-cpu` (depending on Python version).
```

**後端 Log**：
```
AttributeError: _ARRAY_API not found
app.Services.retrieval_service - ERROR - Error adding document chunks:
Could not import faiss python package...
```

---

## 2. 根本原因分析

### 直接原因：NumPy 版本不相容

```
faiss-cpu 1.12.0 編譯於 NumPy 1.x
但環境載入了 NumPy 2.3.5
```

錯誤訊息明確指出：
```
A module that was compiled using NumPy 1.x cannot be run in
NumPy 2.3.5 as it may crash.
```

### 深層原因：虛擬環境配置混亂

檢查環境時發現：
```bash
$ which pip
/Users/xrickliao/miniconda3/miniconda3/bin/pip  # ← 指向 miniconda3

$ which python
/Users/xrickliao/WorkSpaces/Work/Projects/DocAI/docaienv/bin/python  # ← 指向 docaienv
```

**問題**：
- `pip` 和 `python` 指向不同環境
- miniconda3 有 numpy 2.3.5
- docaienv 的 pip 未正確安裝
- 導致安裝套件時版本混亂

---

## 3. 修復步驟

### Step 1：確認問題

```bash
# 測試 FAISS 導入
$ python -c "import faiss"
# 輸出：AttributeError: _ARRAY_API not found

# 檢查 numpy 版本
$ python -c "import numpy; print(numpy.__version__)"
# 輸出：2.3.5（錯誤版本）
```

### Step 2：檢查環境配置

```bash
$ which pip
/Users/xrickliao/miniconda3/miniconda3/bin/pip

$ which python
/Users/xrickliao/WorkSpaces/Work/Projects/DocAI/docaienv/bin/python
```

發現 pip 和 python 不在同一環境。

### Step 3：在 docaienv 安裝 pip

```bash
$ python -m ensurepip --upgrade
# Successfully installed pip-23.2.1
```

### Step 4：使用正確的 pip 安裝套件

```bash
$ docaienv/bin/pip3 install "numpy==1.26.4" faiss-cpu --force-reinstall
# Successfully installed faiss-cpu-1.13.0 numpy-1.26.4
```

### Step 5：驗證修復

```bash
$ docaienv/bin/python -c "import numpy; print(f'NumPy: {numpy.__version__}'); import faiss; print('FAISS OK')"
# NumPy: 1.26.4
# FAISS OK
```

### Step 6：重啟伺服器

```bash
$ lsof -ti:8000 | xargs kill -9
$ docaienv/bin/python main.py > logs/server.log 2>&1 &
```

---

## 4. 版本相容性參考

### 相容組合

| faiss-cpu | NumPy | 狀態 |
|-----------|-------|------|
| 1.13.0 | 1.26.4 | ✅ 正常 |
| 1.12.0 | 1.26.4 | ✅ 正常 |
| 1.12.0 | 2.x | ❌ 不相容 |
| 1.7.4 | 1.26.4 | ✅ 正常 |

### NumPy 2.x 相容性

NumPy 2.0 於 2024 年發布，引入了重大 API 變更。許多使用 C 擴展的套件（如 faiss-cpu）需要重新編譯才能支援 NumPy 2.x。

**建議**：在 faiss-cpu 官方支援 NumPy 2.x 之前，固定使用 `numpy<2`

---

## 5. 預防措施

### 5.1 固定 requirements.txt 版本

```txt
numpy==1.26.4
faiss-cpu==1.13.0
```

### 5.2 使用正確的 pip

始終使用虛擬環境內的 pip：
```bash
# 正確方式
docaienv/bin/pip3 install package_name

# 或
python -m pip install package_name

# 避免使用
pip install package_name  # 可能指向錯誤環境
```

### 5.3 驗證環境

在安裝前檢查：
```bash
which pip
which python
# 確保都指向同一個虛擬環境
```

---

## 6. 相關檔案

| 檔案 | 說明 |
|------|------|
| `requirements.txt` | 應固定 numpy 版本 |
| `start_system.sh` | 啟動腳本，應使用正確的 python |
| `docaienv/` | Python 虛擬環境目錄 |

---

## 7. 總結

| 項目 | 內容 |
|------|------|
| **問題** | FAISS 無法導入，NumPy 版本衝突 |
| **根因** | pip 指向 miniconda3，numpy 2.3.5 與 faiss 不相容 |
| **解決** | 在 docaienv 安裝 pip，使用正確路徑安裝 numpy 1.26.4 |
| **狀態** | ✅ 已修復 |

---

*文件建立日期：2024-11-23*
*狀態：已修復*
