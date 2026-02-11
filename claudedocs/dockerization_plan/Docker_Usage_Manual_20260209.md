# DocAI Docker 使用手冊

**文件日期**: 2026-02-09
**版本**: v1.0

---

## 目錄

1. [前置需求](#1-前置需求)
2. [檔案說明](#2-檔案說明)
3. [首次部署步驟](#3-首次部署步驟)
4. [資料遷移](#4-資料遷移)
5. [日常操作](#5-日常操作)
6. [故障排除](#6-故障排除)
7. [備份與還原](#7-備份與還原)

---

## 1. 前置需求

### 1.1 安裝 Docker

**Ubuntu/Debian:**
```bash
# 安裝 Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 將當前使用者加入 docker 群組（需重新登入）
sudo usermod -aG docker $USER

# 安裝 Docker Compose (v2)
sudo apt-get update
sudo apt-get install docker-compose-plugin
```

**macOS:**
```bash
# 使用 Homebrew 安裝
brew install --cask docker

# 或從 Docker Desktop 官網下載安裝
# https://www.docker.com/products/docker-desktop
```

### 1.2 驗證安裝

```bash
# 檢查 Docker 版本
docker --version
# 預期輸出: Docker version 24.x.x 或更高

# 檢查 Docker Compose 版本
docker compose version
# 預期輸出: Docker Compose version v2.x.x

# 測試 Docker 運行
docker run hello-world
```

### 1.3 確認 Ollama 運行中

DocAI 需要連接到 Ollama LLM 服務：

```bash
# 檢查 Ollama 是否運行
curl http://localhost:11434/api/version

# 如果未運行，啟動 Ollama
ollama serve
```

---

## 2. 檔案說明

容器化相關檔案位於專案根目錄：

| 檔案 | 說明 |
|------|------|
| `Dockerfile` | 定義如何建立 DocAI 應用映像 |
| `docker-compose.yml` | 定義多容器服務編排 |
| `.env.docker` | 容器環境變數配置 |
| `.dockerignore` | 排除不需要的檔案 |

---

## 3. 首次部署步驟

### Step 1: 進入專案目錄

```bash
cd /home/mapleleaf/LCJRepos/gitprjs/DocAI
```

### Step 2: 建立必要目錄

```bash
# 建立 logs 和 uploadfiles 目錄（如果不存在）
mkdir -p logs
mkdir -p uploadfiles/pdf uploadfiles/docx uploadfiles/pptx uploadfiles/txt uploadfiles/md
```

### Step 3: 建立 Docker 映像

```bash
# 建立所有服務的映像
docker compose build

# 或只建立應用映像
docker compose build docai-app
```

**預期輸出：**
```
[+] Building 120.5s (15/15) FINISHED
 => [docai-app internal] load build definition from Dockerfile
 => [docai-app stage-1 builder] FROM python:3.11-slim
 => ...
 => [docai-app] exporting to image
 => => naming to docker.io/library/docai-docai-app
```

### Step 4: 啟動所有服務

```bash
# 啟動服務（背景運行）
docker compose up -d

# 查看啟動日誌
docker compose logs -f
```

**預期輸出：**
```
[+] Running 4/4
 ✔ Network docai_docai-network  Created
 ✔ Volume "docai_mongodb_data"  Created
 ✔ Volume "docai_redis_data"    Created
 ✔ Volume "docai_docai_data"    Created
 ✔ Container docai-redis        Started
 ✔ Container docai-mongodb      Started
 ✔ Container docai-app          Started
```

### Step 5: 驗證服務狀態

```bash
# 查看所有容器狀態
docker compose ps
```

**預期輸出：**
```
NAME            IMAGE              STATUS                   PORTS
docai-app       docai-docai-app    Up 30 seconds (healthy)  0.0.0.0:8082->8082/tcp
docai-mongodb   mongo:7.0          Up 45 seconds (healthy)  0.0.0.0:27017->27017/tcp
docai-redis     redis:7-alpine     Up 45 seconds (healthy)  0.0.0.0:6379->6379/tcp
```

### Step 6: 測試應用

```bash
# 測試健康檢查
curl http://localhost:8082/

# 開啟瀏覽器訪問
# Web UI: http://localhost:8082
# API 文檔: http://localhost:8082/docs
```

---

## 4. 資料遷移

如果您有現有的資料需要遷移到容器中：

### 4.1 遷移 SQLite 資料庫

```bash
# 複製現有資料庫到 Volume
docker compose cp ./data/skill_metadata.db docai-app:/app/data/
docker compose cp ./data/docai.db docai-app:/app/data/
```

### 4.2 遷移 FAISS 索引

```bash
# 複製 FAISS 索引目錄
docker compose cp ./data/faiss_indices/. docai-app:/app/data/faiss_indices/
```

### 4.3 驗證遷移

```bash
# 進入容器檢查
docker compose exec docai-app ls -la /app/data/

# 檢查 FAISS 索引
docker compose exec docai-app ls -la /app/data/faiss_indices/
```

---

## 5. 日常操作

### 5.1 查看日誌

```bash
# 查看所有服務日誌
docker compose logs -f

# 只查看應用日誌
docker compose logs -f docai-app

# 查看最近 100 行
docker compose logs --tail=100 docai-app

# 查看 MongoDB 日誌
docker compose logs -f mongodb
```

### 5.2 停止服務

```bash
# 停止所有服務（保留資料）
docker compose stop

# 停止並移除容器（保留 Volumes）
docker compose down

# 停止並移除所有內容（包括 Volumes）- 危險！
docker compose down -v
```

### 5.3 重啟服務

```bash
# 重啟所有服務
docker compose restart

# 只重啟應用
docker compose restart docai-app
```

### 5.4 更新應用

```bash
# 1. 拉取最新程式碼
git pull

# 2. 重新建立映像
docker compose build docai-app

# 3. 重新啟動（不影響資料庫）
docker compose up -d --no-deps docai-app

# 4. 清理舊映像
docker image prune -f
```

### 5.5 進入容器

```bash
# 進入應用容器
docker compose exec docai-app bash

# 進入 MongoDB
docker compose exec mongodb mongosh

# 進入 Redis
docker compose exec redis redis-cli
```

### 5.6 查看資源使用

```bash
# 即時資源監控
docker stats

# 查看磁碟使用
docker system df
```

---

## 6. 故障排除

### 6.1 容器無法啟動

```bash
# 查看詳細日誌
docker compose logs docai-app

# 常見問題：端口被佔用
# 解決方案：停止佔用端口的服務
sudo lsof -i :8082
sudo kill <PID>
```

### 6.2 無法連接 MongoDB

```bash
# 檢查 MongoDB 容器狀態
docker compose ps mongodb

# 進入容器測試連接
docker compose exec docai-app python -c "
from motor.motor_asyncio import AsyncIOMotorClient
client = AsyncIOMotorClient('mongodb://mongodb:27017')
print('MongoDB connected!')
"
```

### 6.3 無法連接 Ollama

```bash
# 確認 Ollama 在主機運行
curl http://localhost:11434/api/version

# Linux 特別處理：需要添加 host-gateway
# 修改 docker-compose.yml，在 docai-app 服務添加：
#   extra_hosts:
#     - "host.docker.internal:host-gateway"
```

### 6.4 健康檢查失敗

```bash
# 查看健康檢查日誌
docker inspect docai-app | grep -A 20 "Health"

# 手動執行健康檢查
docker compose exec docai-app curl -f http://localhost:8082/
```

### 6.5 重置所有資料

```bash
# 危險操作：將刪除所有資料！
docker compose down -v
docker compose up -d
```

---

## 7. 備份與還原

### 7.1 備份腳本

建立備份腳本 `backup.sh`：

```bash
#!/bin/bash
# backup.sh - DocAI 備份腳本

BACKUP_DIR="./backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "開始備份..."

# 備份 MongoDB
echo "備份 MongoDB..."
docker compose exec -T mongodb mongodump --archive > "$BACKUP_DIR/mongodb.archive"

# 備份 Redis
echo "備份 Redis..."
docker compose exec -T redis redis-cli BGSAVE
sleep 2
docker compose cp redis:/data/dump.rdb "$BACKUP_DIR/redis.rdb"

# 備份 SQLite 和 FAISS
echo "備份 SQLite 和 FAISS..."
docker compose cp docai-app:/app/data/. "$BACKUP_DIR/data/"

# 備份上傳檔案
echo "備份上傳檔案..."
cp -r ./uploadfiles "$BACKUP_DIR/uploadfiles"

echo "備份完成: $BACKUP_DIR"
ls -la "$BACKUP_DIR"
```

```bash
# 賦予執行權限
chmod +x backup.sh

# 執行備份
./backup.sh
```

### 7.2 還原腳本

建立還原腳本 `restore.sh`：

```bash
#!/bin/bash
# restore.sh - DocAI 還原腳本

if [ -z "$1" ]; then
    echo "用法: ./restore.sh <備份目錄>"
    echo "例如: ./restore.sh ./backups/20260209_120000"
    exit 1
fi

BACKUP_DIR="$1"

if [ ! -d "$BACKUP_DIR" ]; then
    echo "錯誤: 找不到備份目錄 $BACKUP_DIR"
    exit 1
fi

echo "從 $BACKUP_DIR 還原..."

# 還原 MongoDB
echo "還原 MongoDB..."
docker compose exec -T mongodb mongorestore --archive < "$BACKUP_DIR/mongodb.archive"

# 還原 SQLite 和 FAISS
echo "還原 SQLite 和 FAISS..."
docker compose cp "$BACKUP_DIR/data/." docai-app:/app/data/

# 還原上傳檔案
echo "還原上傳檔案..."
cp -r "$BACKUP_DIR/uploadfiles/." ./uploadfiles/

echo "還原完成！"
echo "請重啟服務: docker compose restart"
```

```bash
# 賦予執行權限
chmod +x restore.sh

# 執行還原
./restore.sh ./backups/20260209_120000
```

---

## 快速參考

### 常用命令速查表

| 操作 | 命令 |
|------|------|
| 啟動所有服務 | `docker compose up -d` |
| 停止所有服務 | `docker compose down` |
| 查看服務狀態 | `docker compose ps` |
| 查看日誌 | `docker compose logs -f` |
| 重啟服務 | `docker compose restart` |
| 重建映像 | `docker compose build` |
| 進入容器 | `docker compose exec docai-app bash` |
| 資源監控 | `docker stats` |

### 服務端口

| 服務 | 端口 | 說明 |
|------|------|------|
| DocAI Web UI | 8082 | http://localhost:8082 |
| DocAI API 文檔 | 8082 | http://localhost:8082/docs |
| MongoDB | 27017 | 內部服務名: mongodb |
| Redis | 6379 | 內部服務名: redis |

### 重要目錄

| 路徑 | 說明 |
|------|------|
| `./uploadfiles/` | 用戶上傳檔案（Bind Mount） |
| `./logs/` | 應用日誌（Bind Mount） |
| `docai_data` Volume | SQLite + FAISS（Named Volume） |
| `mongodb_data` Volume | MongoDB 資料（Named Volume） |
| `redis_data` Volume | Redis 資料（Named Volume） |

---

*文件結束 - DocAI Docker 使用手冊 v1.0*
