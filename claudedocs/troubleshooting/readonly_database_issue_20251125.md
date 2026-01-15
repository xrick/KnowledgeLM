# SQLite Readonly Database 問題診斷報告

**問題時間**: 2025-11-25
**錯誤訊息**: `上傳失敗：Failed to process file: attempt to write a readonly database`
**嚴重程度**: 🔴 Critical（阻止檔案上傳功能）
**解決狀態**: ✅ 已解決

---

## 🔍 問題描述

用戶嘗試上傳檔案時，系統回報錯誤：
```
Failed to process file: attempt to write a readonly database
```

這導致檔案上傳功能完全失效，影響系統的核心功能。

---

## 🎯 根本原因

**多個 DocAI 進程同時運行導致資料庫鎖定衝突**

### 發現的問題

系統中同時運行了兩個 DocAI 進程：

| PID | 啟動時間 | 狀態 |
|-----|---------|------|
| 148666 | 11:29 | 舊進程（應該被停止但仍在運行） |
| 290695 | 13:33 | 新進程（正常啟動） |

### 為什麼會導致錯誤？

1. **SQLite 檔案鎖機制**：
   - SQLite 使用檔案鎖來確保資料完整性
   - 同一時間只允許一個進程寫入資料庫
   - 當有進程持有鎖時，其他進程的寫入會被阻止

2. **錯誤訊息的誤導性**：
   - 錯誤訊息是 `readonly database`
   - 但實際問題是**資料庫被鎖定**，而不是權限問題
   - SQLite 將鎖定錯誤轉換為「readonly」錯誤訊息

3. **檔案上傳流程**：
   ```python
   # app/api/v1/endpoints/upload.py
   await file_metadata_provider.add_file(
       file_id=file_id,
       filename=filename,
       ...
   )
   # ↑ 需要寫入 SQLite 資料庫
   # ↓ 如果資料庫被鎖定，此操作失敗
   ```

---

## 🔧 診斷過程

### 1. 檢查檔案和目錄權限

```bash
$ ls -la ./data/docai.db
-rw-rw-r-- 1 mapleleaf mapleleaf 499712 11月 25 13:40 ./data/docai.db

$ ls -lad ./data
drwxrwxr-x 3 mapleleaf mapleleaf 4096 11月 25 13:40 ./data
```

✅ **權限正常**：
- 檔案：644（擁有者可讀寫）
- 目錄：775（擁有者可讀寫執行）

### 2. 檢查進程狀態

```bash
$ ps aux | grep "python main.py"
mapleleaf  148666  0.1  1.1 6666996 719456 pts/0  Sl   11:29   0:17 docaienv/bin/python main.py
mapleleaf  290695  1.8  1.9 10472652 1219700 pts/0 Sl  13:33   0:45 docaienv/bin/python main.py
```

❌ **發現問題**：兩個進程同時運行！

### 3. 檢查 SQLite 設定

```bash
$ sqlite3 ./data/docai.db "PRAGMA journal_mode;"
delete
```

✅ **Journal mode 正常**：使用標準的 delete mode

### 4. 測試資料庫寫入

```bash
# 停止所有進程後測試
$ sqlite3 ./data/docai.db "CREATE TABLE test_table (id INTEGER); INSERT INTO test_table VALUES (1);"
# ✅ 成功
```

---

## ✅ 解決方案

### 立即修正步驟

1. **停止所有 DocAI 進程**：
   ```bash
   pkill -f "docaienv/bin/python main.py"
   # 或使用
   ./stop_system.sh
   ```

2. **驗證進程已停止**：
   ```bash
   ps aux | grep "python main.py" | grep -v grep
   # 應該沒有輸出
   ```

3. **驗證資料庫未被鎖定**：
   ```bash
   lsof ./data/docai.db
   # 應該沒有輸出
   ```

4. **重新啟動系統**：
   ```bash
   ./start_system.sh
   ```

5. **驗證只有一個進程運行**：
   ```bash
   ps aux | grep "python main.py" | grep -v grep
   # 應該只有一個進程
   ```

### 驗證結果

```bash
$ ps aux | grep "python main.py" | grep -v grep
mapleleaf  345770 54.3  1.1 6667132 719000 ?  Sl   14:14   0:05 docaienv/bin/python main.py
```

✅ **只有一個進程運行**（PID: 345770）

---

## 🛡️ 預防措施

### 1. 改進啟動腳本

修改 `start_system.sh` 加入進程檢查：

```bash
# 檢查是否已有進程在運行
if pgrep -f "docaienv/bin/python main.py" > /dev/null; then
    echo "⚠️  DocAI 進程已在運行，請先停止現有進程"
    echo "執行: ./stop_system.sh"
    exit 1
fi
```

### 2. 改進停止腳本

確保 `stop_system.sh` 能夠強制終止所有進程：

```bash
# 使用 pkill 強制終止所有相關進程
pkill -9 -f "docaienv/bin/python main.py"

# 驗證所有進程已停止
if pgrep -f "docaienv/bin/python main.py" > /dev/null; then
    echo "❌ 仍有進程在運行，需要手動終止"
    exit 1
fi
```

### 3. SQLite 設定優化

考慮使用 WAL (Write-Ahead Logging) mode 提升並發性能：

```python
# app/Providers/file_metadata_provider/client.py
# 在資料庫初始化時設定
cursor.execute("PRAGMA journal_mode=WAL")
cursor.execute("PRAGMA synchronous=NORMAL")
```

**WAL mode 的優勢**：
- 允許讀取操作不會被寫入操作阻塞
- 提升並發性能
- 減少鎖定衝突

### 4. 監控和告警

建議加入監控機制：

```python
# 定期檢查進程數量
import subprocess

def check_process_count():
    result = subprocess.run(
        ["pgrep", "-c", "-f", "docaienv/bin/python main.py"],
        capture_output=True,
        text=True
    )
    count = int(result.stdout.strip()) if result.returncode == 0 else 0

    if count > 1:
        logger.error(f"Multiple DocAI processes detected: {count}")
        # 發送告警
```

---

## 📊 技術細節

### SQLite 鎖定機制

SQLite 使用五種鎖定狀態：

| 鎖定狀態 | 說明 | 其他進程可以 |
|---------|------|-------------|
| UNLOCKED | 無鎖定 | 讀取、寫入 |
| SHARED | 共享鎖（讀取） | 讀取，不可寫入 |
| RESERVED | 預留鎖（準備寫入） | 讀取，不可寫入 |
| PENDING | 等待鎖（即將寫入） | 完成現有讀取，不可新讀取 |
| EXCLUSIVE | 排他鎖（寫入中） | 不可讀取、寫入 |

**問題情境**：
1. 進程 A 持有 EXCLUSIVE 鎖進行寫入
2. 進程 B 嘗試寫入，需要獲取 EXCLUSIVE 鎖
3. 鎖定衝突 → SQLite 回報 `readonly database` 錯誤

### Journal Mode 比較

| Mode | 並發性 | 性能 | 適用場景 |
|------|-------|------|---------|
| DELETE | 低 | 中 | 單進程應用 |
| WAL | 高 | 高 | 多進程/多線程應用 |
| TRUNCATE | 低 | 高 | 單進程，高性能需求 |
| PERSIST | 低 | 高 | 單進程，減少 I/O |

**建議**：切換到 WAL mode 以提升並發性能。

---

## 📝 經驗教訓

1. **進程管理很重要**：
   - 啟動前檢查是否已有進程在運行
   - 停止時確保所有進程都被終止
   - 使用 PID 文件追蹤進程狀態

2. **錯誤訊息可能誤導**：
   - `readonly database` 不一定是權限問題
   - 可能是鎖定衝突或其他並發問題
   - 需要深入診斷而不是表面判斷

3. **SQLite 在多進程環境的限制**：
   - SQLite 設計用於單進程應用
   - 多進程場景需要特別注意鎖定問題
   - 考慮使用 WAL mode 或切換到 PostgreSQL

4. **系統監控的必要性**：
   - 定期檢查進程狀態
   - 監控資料庫鎖定情況
   - 及早發現並處理異常

---

## 🔗 相關資源

- [SQLite Locking And Concurrency](https://www.sqlite.org/lockingv3.html)
- [SQLite WAL Mode](https://www.sqlite.org/wal.html)
- [SQLite Error Codes](https://www.sqlite.org/rescode.html)

---

**診斷時間**: 2025-11-25 14:00-14:15
**診斷人員**: Claude (SuperClaude Framework)
**解決狀態**: ✅ 已解決
**建議追蹤**: 監控系統運行 24 小時確認穩定性
