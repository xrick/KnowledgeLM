# DocAI 環境安裝手冊：MongoDB 與 Redis

> **版本**: 1.0  
> **最後更新**: 2026-01-14  
> **適用範圍**: Linux 新機器部署

---

## 目錄

1. [概述](#概述)
2. [系統需求](#系統需求)
3. [腳本清單](#腳本清單)
4. [完整安裝指南](#完整安裝指南)
5. [獨立初始化指南](#獨立初始化指南)
6. [資料結構說明](#資料結構說明)
7. [驗證與測試](#驗證與測試)
8. [故障排除](#故障排除)
9. [附錄：環境變數配置](#附錄環境變數配置)

---

## 概述

本手冊說明如何在新的 Linux 機器上安裝並配置 DocAI 所需的 MongoDB 和 Redis 服務。

DocAI 使用這兩個服務的用途：

| 服務 | 用途 | Database |
|------|------|----------|
| **MongoDB** | 聊天歷史記錄持久化儲存 | `docai.chat_sessions` |
| **Redis** | 高效能快取層（Embedding、查詢擴展、搜尋結果） | DB 0 |

---

## 系統需求

### 支援的 Linux 發行版

| 發行版 | 版本 | 套件管理器 |
|--------|------|------------|
| Ubuntu | 20.04, 22.04, 24.04 | apt |
| Debian | 11, 12 | apt |
| CentOS | 8, 9 | dnf/yum |
| RHEL | 8, 9 | dnf/yum |
| Rocky Linux | 8, 9 | dnf |
| AlmaLinux | 8, 9 | dnf |

### 硬體需求

| 項目 | 最低需求 | 建議配置 |
|------|----------|----------|
| RAM | 4 GB | 8 GB+ |
| 磁碟空間 | 10 GB | 50 GB+ (含向量索引) |
| CPU | 2 cores | 4 cores+ |

### 軟體需求

- Root 權限 (sudo)
- 網路連線（下載套件）
- curl, gnupg（腳本會自動安裝）

---

## 腳本清單

所有腳本位於 `scripts/` 目錄下：

| 腳本名稱 | 用途 | 執行方式 |
|----------|------|----------|
| `install_docai_deps.sh` | **主安裝腳本** - 安裝 MongoDB + Redis 並初始化所有結構 | `sudo ./scripts/install_docai_deps.sh` |
| `init_docai_mongodb.js` | MongoDB 獨立初始化腳本（已安裝 MongoDB 時使用） | `mongosh --file scripts/init_docai_mongodb.js` |
| `init_docai_redis.sh` | Redis 獨立初始化腳本（已安裝 Redis 時使用） | `./scripts/init_docai_redis.sh` |

---

## 完整安裝指南

### 情境：新機器，尚未安裝 MongoDB 和 Redis

#### Step 1: 進入專案目錄

```bash
cd /path/to/DocAI
```

#### Step 2: 確認腳本有執行權限

```bash
chmod +x scripts/install_docai_deps.sh
```

#### Step 3: 執行主安裝腳本

```bash
sudo ./scripts/install_docai_deps.sh
```

#### 執行過程說明

腳本會依序執行以下步驟：

```
╔═══════════════════════════════════════════════════════════════════╗
║                DocAI 依賴安裝腳本                                  ║
╚═══════════════════════════════════════════════════════════════════╝

1. 檢測 Linux 發行版
2. 安裝 MongoDB 7.0
   - 添加官方 GPG key
   - 添加官方倉庫
   - 安裝 mongodb-org 套件
   - 啟動服務並設定開機啟動
3. 安裝 Redis Server
   - 添加官方倉庫
   - 安裝 redis 套件
   - 啟動服務並設定開機啟動
4. 驗證安裝
   - 測試 MongoDB 連接
   - 測試 Redis 連接
5. 初始化 DocAI 資料結構
   - 創建 MongoDB database 和 collection
   - 創建索引
   - 設置 Redis 初始化標記
6. 智能合併 .env 環境變數 ⭐ NEW
   - 檢查現有 .env 文件
   - 只補充缺少的變數
   - 保留用戶已設定的值
7. 顯示配置摘要
```

#### 預期輸出

```
✅ MongoDB 7.0 安裝完成
✅ Redis Server 安裝完成
✅ MongoDB 服務正在運行
✅ Redis 服務正在運行
✅ MongoDB 資料結構初始化完成
✅ Redis 初始化完成

═══════════════════════════════════════════════════════════════════
  智能合併 .env 環境變數
═══════════════════════════════════════════════════════════════════

ℹ️  專案目錄: /path/to/DocAI
ℹ️  .env 路徑: /path/to/DocAI/.env

ℹ️  檢查環境變數...

  ✅ MONGODB_URI=mongodb://localhost:27017
  ✅ MONGODB_DATABASE=docai
  ⏭️  REDIS_HOST (已存在: 192.168.1.100)    # 保留用戶設定
  ✅ REDIS_PORT=6379
  ...

═══════════════════════════════════════════════════════════════════

✅ 已添加 10 個環境變數到 .env
ℹ️  跳過 3 個已存在的變數

✅ .env 智能合併完成

📋 DocAI 依賴安裝完成！

=== MongoDB 配置 ===
  Host:       localhost
  Port:       27017
  Database:   docai
  Collection: chat_sessions
  URI:        mongodb://localhost:27017

=== Redis 配置 ===
  Host:       localhost
  Port:       6379
  Database:   0
  URI:        redis://localhost:6379/0
```

---

## 獨立初始化指南

### 情境 A：已安裝 MongoDB，只需初始化 DocAI 結構

#### 方法 1：使用 mongosh

```bash
mongosh --file scripts/init_docai_mongodb.js
```

#### 方法 2：連接到遠端 MongoDB

```bash
mongosh mongodb://your-mongodb-host:27017 --file scripts/init_docai_mongodb.js
```

#### 方法 3：使用帳號密碼認證

```bash
mongosh "mongodb://username:password@host:27017" --file scripts/init_docai_mongodb.js
```

#### 預期輸出

```
╔═══════════════════════════════════════════════════════════════════╗
║           DocAI MongoDB Schema Initialization                     ║
╚═══════════════════════════════════════════════════════════════════╝

📂 Using database: docai

🔧 Step 1: Creating chat_sessions collection...
   ✅ Created collection: chat_sessions

🔧 Step 2: Creating indexes...
   ✅ Index: idx_session_id_unique (session_id, unique)
   ✅ Index: idx_user_id (user_id)
   ✅ Index: idx_created_at (created_at DESC)
   ✅ Index: idx_updated_at (updated_at DESC)
   ✅ Index: idx_file_ids (file_ids)
   ✅ Index: idx_user_recent (user_id + updated_at DESC)

🔧 Step 3: Inserting initialization test document...
   ✅ Inserted test document (session_id: docai_init_test)

═══════════════════════════════════════════════════════════════════
📊 Collection Summary
═══════════════════════════════════════════════════════════════════

📁 Database: docai
📁 Collection: chat_sessions

📋 Indexes:
   • _id_: {"_id":1}
   • idx_session_id_unique: {"session_id":1} (unique)
   • idx_user_id: {"user_id":1}
   • idx_created_at: {"created_at":-1}
   • idx_updated_at: {"updated_at":-1}
   • idx_file_ids: {"file_ids":1}
   • idx_user_recent: {"user_id":1,"updated_at":-1}

🎉 DocAI MongoDB initialization complete!
```

---

### 情境 B：已安裝 Redis，只需初始化 DocAI 配置

#### 方法 1：本地 Redis

```bash
chmod +x scripts/init_docai_redis.sh
./scripts/init_docai_redis.sh
```

#### 方法 2：指定主機和埠號

```bash
./scripts/init_docai_redis.sh 192.168.1.100 6379
```

#### 預期輸出

```
═══════════════════════════════════════════════════════════════════
  DocAI Redis Initialization
═══════════════════════════════════════════════════════════════════

Redis 連接配置:
  Host: localhost
  Port: 6379

ℹ️  測試 Redis 連接...
✅ Redis 連接成功

═══════════════════════════════════════════════════════════════════
  初始化 DocAI 配置
═══════════════════════════════════════════════════════════════════

✅ 設置初始化時間: 2026-01-14T15:30:00+08:00
✅ 設置版本: 1.0.0
✅ 設置 TTL 配置

═══════════════════════════════════════════════════════════════════
  DocAI Redis Key 模式
═══════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────┐
│ Key Pattern            │ TTL      │ Description               │
├─────────────────────────────────────────────────────────────────┤
│ emb:{text_hash}        │ 24h      │ Embedding 向量快取        │
│ qexp:{query_hash}      │ 1h       │ 查詢擴展結果快取          │
│ search:{hash}          │ 30min    │ 搜尋結果快取              │
│ file:{file_id}         │ 6h       │ 文件元數據快取            │
│ docai:init             │ -        │ 初始化時間戳              │
│ docai:version          │ -        │ 系統版本                  │
│ docai:config           │ -        │ TTL 配置 (Hash)           │
└─────────────────────────────────────────────────────────────────┘

✅ DocAI Redis 初始化完成！
```

---

## 智能合併 .env 功能說明

### 功能概述

`install_docai_deps.sh` 腳本內建智能合併功能，會自動檢查專案根目錄的 `.env` 文件，**只補充缺少的環境變數，不會覆蓋已存在的設定**。

### 支援的環境變數

| 變數名稱 | 預設值 | 說明 |
|----------|--------|------|
| `MONGODB_URI` | `mongodb://localhost:27017` | MongoDB 連接 URI |
| `MONGODB_DATABASE` | `docai` | 資料庫名稱 |
| `MONGODB_CHAT_COLLECTION` | `chat_sessions` | 聊天記錄集合名稱 |
| `MONGODB_MIN_POOL_SIZE` | `10` | 連接池最小連接數 |
| `MONGODB_MAX_POOL_SIZE` | `100` | 連接池最大連接數 |
| `REDIS_HOST` | `localhost` | Redis 主機位址 |
| `REDIS_PORT` | `6379` | Redis 連接埠 |
| `REDIS_DB` | `0` | Redis 資料庫編號 |
| `REDIS_PASSWORD` | *(空)* | Redis 密碼（如有設定） |
| `REDIS_CACHE_TTL` | `3600` | 一般快取 TTL（秒） |
| `REDIS_EMBEDDING_TTL` | `86400` | Embedding 快取 TTL（24小時） |
| `REDIS_QUERY_EXPANSION_TTL` | `3600` | 查詢擴展快取 TTL（1小時） |
| `REDIS_SEARCH_RESULTS_TTL` | `1800` | 搜尋結果快取 TTL（30分鐘） |

### 行為說明

1. **變數不存在** → 自動添加預設值
2. **變數已存在** → 保留現有值，顯示 `⏭️` 跳過提示
3. **.env 不存在** → 自動創建新文件

### 使用情境

#### 情境 1：全新安裝
```
.env 不存在
  ↓
創建 .env 並寫入所有 13 個變數
```

#### 情境 2：部分配置
```
.env 已有 REDIS_HOST=192.168.1.100
  ↓
保留 REDIS_HOST=192.168.1.100
補充其他 12 個變數
```

#### 情境 3：已完整配置
```
.env 已有所有 13 個變數
  ↓
顯示「所有環境變數已存在，無需添加」
不做任何修改
```

---

## 資料結構說明

### MongoDB 結構

#### Database: `docai`

#### Collection: `chat_sessions`

```javascript
{
    "_id": ObjectId,                    // MongoDB 自動生成
    "session_id": String,               // 唯一會話識別碼 (必填)
    "user_id": String | null,           // 用戶識別碼 (選填)
    "file_ids": [String],               // 關聯的文件 ID 列表
    "created_at": Date,                 // 建立時間 (必填)
    "updated_at": Date,                 // 最後更新時間 (必填)
    "messages": [                       // 訊息陣列 (必填)
        {
            "role": "user" | "assistant" | "system",  // 角色
            "content": String,                        // 訊息內容
            "timestamp": Date,                        // 訊息時間
            "metadata": Object                        // 額外元數據
        }
    ],
    "metadata": Object                  // 會話級別元數據 (選填)
}
```

#### 索引清單

| 索引名稱 | 欄位 | 類型 | 用途 |
|----------|------|------|------|
| `idx_session_id_unique` | `session_id` | Unique | 主鍵查詢 |
| `idx_user_id` | `user_id` | Normal | 按用戶查詢 |
| `idx_created_at` | `created_at` DESC | Normal | 按建立時間排序 |
| `idx_updated_at` | `updated_at` DESC | Normal | 按更新時間排序 |
| `idx_file_ids` | `file_ids` | Multikey | 按文件查詢 |
| `idx_user_recent` | `user_id`, `updated_at` DESC | Compound | 用戶最近對話 |

---

### Redis 結構

#### Key Pattern 說明

| Key Pattern | TTL | 資料類型 | 說明 |
|-------------|-----|----------|------|
| `emb:{text_hash}` | 86400s (24h) | String (JSON) | Embedding 向量快取，避免重複計算 |
| `qexp:{query_hash}` | 3600s (1h) | String (JSON) | 查詢擴展結果，包含擴展後的子問題 |
| `search:{hash}` | 1800s (30min) | String (JSON) | 搜尋結果快取，包含 chunks 和分數 |
| `file:{file_id}` | 21600s (6h) | String (JSON) | 文件元數據快取 |
| `docai:init` | - | String | 初始化時間戳 |
| `docai:version` | - | String | 系統版本號 |
| `docai:config` | - | Hash | TTL 配置值 |

#### Hash 說明

`docai:config` 內容：

```
embedding_ttl: "86400"
query_expansion_ttl: "3600"
search_results_ttl: "1800"
file_metadata_ttl: "21600"
```

---

## 驗證與測試

### 驗證 MongoDB

```bash
# 檢查服務狀態
sudo systemctl status mongod

# 測試連接
mongosh --eval "db.runCommand({ ping: 1 })"

# 檢查 DocAI 資料庫
mongosh --eval "use docai; db.chat_sessions.countDocuments()"

# 檢查索引
mongosh --eval "use docai; db.chat_sessions.getIndexes()"
```

### 驗證 Redis

```bash
# 檢查服務狀態 (Ubuntu/Debian)
sudo systemctl status redis-server

# 檢查服務狀態 (RHEL/CentOS)
sudo systemctl status redis

# 測試連接
redis-cli ping
# 預期輸出: PONG

# 檢查 DocAI keys
redis-cli KEYS "docai:*"

# 檢查配置
redis-cli HGETALL "docai:config"
```

---

## 故障排除

### MongoDB 問題

#### 問題：服務無法啟動

```bash
# 檢查日誌
sudo journalctl -u mongod -f

# 常見原因：
# 1. 端口被佔用
sudo lsof -i :27017

# 2. 權限問題
sudo chown -R mongodb:mongodb /var/lib/mongodb
sudo chown -R mongodb:mongodb /var/log/mongodb

# 3. 配置文件錯誤
sudo mongod --config /etc/mongod.conf --fork
```

#### 問題：無法連接

```bash
# 檢查 bindIp 設定
sudo grep bindIp /etc/mongod.conf
# 確保包含 127.0.0.1 或 0.0.0.0

# 重啟服務
sudo systemctl restart mongod
```

---

### Redis 問題

#### 問題：服務無法啟動

```bash
# 檢查日誌
sudo journalctl -u redis-server -f

# 常見原因：
# 1. 端口被佔用
sudo lsof -i :6379

# 2. 記憶體不足
free -h
```

#### 問題：無法連接

```bash
# 檢查 bind 設定
sudo grep bind /etc/redis/redis.conf

# 檢查防火牆
sudo ufw status
sudo ufw allow 6379/tcp
```

---

## 附錄：環境變數配置

安裝完成後，請確保 DocAI 的 `.env` 文件包含以下配置：

```bash
# =============================================================================
# MongoDB Settings (Chat History)
# =============================================================================
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=docai
MONGODB_CHAT_COLLECTION=chat_sessions
MONGODB_MIN_POOL_SIZE=10
MONGODB_MAX_POOL_SIZE=100

# =============================================================================
# Redis Settings (Cache)
# =============================================================================
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
REDIS_CACHE_TTL=3600
REDIS_EMBEDDING_TTL=86400
REDIS_QUERY_EXPANSION_TTL=3600
REDIS_SEARCH_RESULTS_TTL=1800
```

### 遠端連接配置範例

如果 MongoDB 或 Redis 在其他主機：

```bash
# MongoDB 遠端連接
MONGODB_URI=mongodb://username:password@192.168.1.100:27017

# Redis 遠端連接
REDIS_HOST=192.168.1.101
REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password
```

---

## 服務管理命令速查

### MongoDB

```bash
# 啟動
sudo systemctl start mongod

# 停止
sudo systemctl stop mongod

# 重啟
sudo systemctl restart mongod

# 查看狀態
sudo systemctl status mongod

# 設定開機啟動
sudo systemctl enable mongod

# 取消開機啟動
sudo systemctl disable mongod
```

### Redis

```bash
# Ubuntu/Debian
sudo systemctl start redis-server
sudo systemctl stop redis-server
sudo systemctl restart redis-server
sudo systemctl status redis-server

# RHEL/CentOS
sudo systemctl start redis
sudo systemctl stop redis
sudo systemctl restart redis
sudo systemctl status redis
```

---

## 下一步

安裝完成後，您可以：

1. **配置 .env 文件** - 確保連接參數正確
2. **啟動 DocAI** - 執行 `./start_system.sh`
3. **驗證系統** - 訪問 Web 介面確認功能正常

---

*文檔版本: 1.0 | 最後更新: 2026-01-14*
