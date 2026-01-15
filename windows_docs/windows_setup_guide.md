# DocAI Windows 環境設置指南

**版本**: 1.0  
**日期**: 2026-01-14  
**適用平台**: Windows 10/11, Python 3.9+

---

## 📋 目錄

1. [先決條件](#1-先決條件)
2. [安裝 MongoDB](#2-安裝-mongodb)
3. [安裝 Redis](#3-安裝-redis)
4. [初始化 DocAI 資料](#4-初始化-docai-資料)
5. [環境變數設置](#5-環境變數設置)
6. [驗證安裝](#6-驗證安裝)
7. [故障排除](#7-故障排除)

---

## 1. 先決條件

### 必要軟體

| 軟體 | 最低版本 | 用途 |
|------|----------|------|
| Python | 3.9+ | 主程式運行 |
| MongoDB | 7.0+ | 聊天歷史儲存 |
| Redis | 7.0+ | 快取服務 |

### Python 套件

```bash
pip install pymongo redis
```

---

## 2. 安裝 MongoDB

### 方法 A: 使用 MSI 安裝程式（推薦）

1. **下載安裝程式**
   - 前往 [MongoDB Download Center](https://www.mongodb.com/try/download/community)
   - 選擇 **Windows** → **msi**

2. **執行安裝**
   - 執行下載的 MSI 檔案
   - 選擇 **Complete** 安裝
   - ✅ 勾選 "Install MongoDB as a Service"
   - ✅ 勾選 "Install MongoDB Compass" (可選，圖形化管理工具)

3. **驗證安裝**
   ```cmd
   mongosh --version
   mongosh --eval "db.serverStatus().version"
   ```

### 方法 B: 使用 Docker Desktop

```cmd
docker pull mongo:7.0
docker run -d --name docai-mongodb -p 27017:27017 mongo:7.0
```

### 防火牆設置

如需遠端訪問，開放端口 27017：
```powershell
# 以管理員身份執行
New-NetFirewallRule -DisplayName "MongoDB" -Direction Inbound -LocalPort 27017 -Protocol TCP -Action Allow
```

---

## 3. 安裝 Redis

### 方法 A: 使用 Windows 版本（推薦）

由於 Redis 官方不支援 Windows，推薦使用以下替代方案：

#### 選項 1: Memurai（Redis for Windows）

1. 下載 [Memurai](https://www.memurai.com/get-memurai)
2. 執行安裝程式
3. Memurai 會自動作為 Windows 服務運行

#### 選項 2: Redis 官方 Windows 分支

```powershell
# 使用 Chocolatey 安裝
choco install redis-64
```

### 方法 B: 使用 Docker Desktop

```cmd
docker pull redis:7-alpine
docker run -d --name docai-redis -p 6379:6379 redis:7-alpine
```

### 方法 C: 使用 WSL2

```bash
# 在 WSL2 Ubuntu 中
sudo apt update
sudo apt install redis-server
sudo service redis-server start
```

### 驗證安裝

```cmd
redis-cli ping
# 應該回傳: PONG
```

---

## 4. 初始化 DocAI 資料

### 使用初始化腳本

DocAI 提供了 Python 初始化腳本，可自動建立所有必要的資料結構：

```cmd
cd DocAI
python scripts/init_docai_windows.py
```

### 腳本功能

| 組件 | 功能 |
|------|------|
| **SQLite** | 創建 `skill_metadata.db` 及 6 個表格、13 個索引 |
| **FAISS** | 創建向量索引目錄結構 |
| **MongoDB** | 創建 `docai` 資料庫和 `chat_sessions` 集合 |
| **Redis** | 初始化配置 keys 和 TTL 設定 |

### 命令列參數

```cmd
# 初始化所有組件（預設）
python scripts/init_docai_windows.py

# 只初始化特定組件
python scripts/init_docai_windows.py --sqlite
python scripts/init_docai_windows.py --mongodb --redis

# 強制重建（覆蓋現有資料）
python scripts/init_docai_windows.py --force

# 顯示詳細輸出
python scripts/init_docai_windows.py --verbose

# 自訂配置
python scripts/init_docai_windows.py --data-dir "D:\DocAI\data"
python scripts/init_docai_windows.py --mongodb-uri "mongodb://192.168.1.100:27017"
python scripts/init_docai_windows.py --redis-host "192.168.1.100" --redis-port 6380
```

### 預期輸出

```
╔═══════════════════════════════════════════════════════════════════╗
║          DocAI Windows 環境初始化工具 v1.0                        ║
╚═══════════════════════════════════════════════════════════════════╝

══════════════════════════════════════════════════════════════════════
  SQLite skill_metadata.db 初始化
══════════════════════════════════════════════════════════════════════

ℹ️  創建資料庫: .\data\skill_metadata.db
✅ 完整性檢查: 通過
✅ skill_metadata.db 初始化成功

ℹ️  已創建的表格:
  📋 skill_heads
  📋 skill_metadata
  📋 skill_overviews
  📋 skill_document_mapping
  📋 skill_chunk_metadata
  📋 processing_jobs

══════════════════════════════════════════════════════════════════════
  初始化結果總結
══════════════════════════════════════════════════════════════════════

✅ SQLite: 成功
✅ FAISS: 成功
✅ MongoDB: 成功
✅ Redis: 成功

✅ 所有組件初始化完成！
```

---

## 5. 環境變數設置

### .env 檔案範例

在專案根目錄創建 `.env` 檔案：

```ini
# =============================================================================
# DocAI Environment Configuration (Windows)
# =============================================================================

# Application
APP_ENV=development
DEBUG=true

# MongoDB
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=docai
MONGODB_CHAT_COLLECTION=chat_sessions

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_EMBEDDING_TTL=86400
REDIS_QUERY_EXPANSION_TTL=3600
REDIS_SEARCH_RESULTS_TTL=1800

# SQLite (Skill Metadata)
SKILL_METADATA_DB_PATH=./data/skill_metadata.db

# FAISS
VECTOR_STORE_PATH=./data/faiss_indices

# LLM Configuration
OPENAI_API_KEY=your_api_key_here
LLM_MODEL=gpt-4o-mini
EMBEDDING_MODEL=BAAI/bge-m3

# Server
HOST=0.0.0.0
PORT=8000
```

### Windows 系統環境變數

如需設為系統環境變數：

```powershell
# 以管理員身份執行
[System.Environment]::SetEnvironmentVariable("MONGODB_URI", "mongodb://localhost:27017", "Machine")
[System.Environment]::SetEnvironmentVariable("REDIS_HOST", "localhost", "Machine")
```

---

## 6. 驗證安裝

### 快速驗證腳本

```python
# scripts/verify_installation.py
import sys

def check_mongodb():
    try:
        from pymongo import MongoClient
        client = MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=3000)
        client.admin.command('ping')
        print("✅ MongoDB: OK")
        return True
    except Exception as e:
        print(f"❌ MongoDB: {e}")
        return False

def check_redis():
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, socket_connect_timeout=3)
        r.ping()
        print("✅ Redis: OK")
        return True
    except Exception as e:
        print(f"❌ Redis: {e}")
        return False

def check_sqlite():
    import sqlite3
    from pathlib import Path
    db_path = Path("./data/skill_metadata.db")
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        conn.close()
        if result == "ok":
            print("✅ SQLite: OK")
            return True
    print("❌ SQLite: Database not found or corrupted")
    return False

if __name__ == "__main__":
    results = [check_mongodb(), check_redis(), check_sqlite()]
    sys.exit(0 if all(results) else 1)
```

執行驗證：
```cmd
python scripts/verify_installation.py
```

---

## 7. 故障排除

### MongoDB 連接失敗

**症狀**: `ServerSelectionTimeoutError`

**解決方案**:
1. 確認服務正在運行
   ```cmd
   sc query MongoDB
   # 或
   net start MongoDB
   ```

2. 檢查防火牆設定

3. 確認端口 27017 未被占用
   ```cmd
   netstat -ano | findstr 27017
   ```

### Redis 連接失敗

**症狀**: `ConnectionError: Error 10061`

**解決方案**:
1. 確認 Redis/Memurai 服務正在運行
   ```cmd
   sc query Memurai
   # 或
   redis-cli ping
   ```

2. 若使用 Docker，確認容器正在運行
   ```cmd
   docker ps | findstr redis
   ```

### SQLite 資料庫損壞

**症狀**: `database disk image is malformed`

**解決方案**:
1. 使用修復腳本（Linux/Mac）
   ```bash
   ./scripts/repair_sqlite.sh
   ```

2. 或重建資料庫
   ```cmd
   python scripts/init_docai_windows.py --sqlite --force
   ```

### Python 套件缺失

**症狀**: `ModuleNotFoundError`

**解決方案**:
```cmd
pip install -r requirements.txt
# 或單獨安裝
pip install pymongo redis faiss-cpu
```

---

## 📚 相關文檔

- [MongoDB/Redis 安裝手冊（Linux）](installation_mongodb_redis.md)
- [SQLite 修復指南](sqlite_repair_guide.md)
- [CLAUDE.md 專案說明](../../CLAUDE.md)

---

## 📝 修改記錄

| 日期 | 版本 | 說明 |
|------|------|------|
| 2026-01-14 | 1.0 | 初版發布 |
