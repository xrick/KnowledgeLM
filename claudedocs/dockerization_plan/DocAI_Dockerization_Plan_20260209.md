# DocAI 系統容器化計劃

**文件日期**: 2026-02-09
**版本**: v1.0
**作者**: Claude (SuperClaude Framework)

---

## 1. 執行摘要

本文件詳述 DocAI RAG 系統的完整容器化策略。目標是將系統打包成 Docker 映像，實現：

- **MongoDB** 和 **Redis** 在容器內運行
- **uploadfiles** 作為外部 Volume 掛載
- 完整的服務隔離與可移植性

---

## 2. 現有系統架構分析

### 2.1 服務組件清單

| 服務 | 埠號 | 類型 | 容器化策略 |
|------|------|------|-----------|
| **FastAPI (DocAI)** | 8082 | 主應用 | Docker 容器 |
| **MongoDB** | 27017 | 資料庫 | Docker 容器 |
| **Redis** | 6379 | 快取 | Docker 容器 |
| **Ollama LLM** | 11434 | 外部服務 | 獨立容器或主機 |
| **SQLite** | - | 嵌入式 | 包含在主應用容器 |
| **FAISS** | - | 嵌入式 | 包含在主應用容器 |

### 2.2 資料流架構

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Docker Compose                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │   docai-app  │    │   mongodb    │    │    redis     │          │
│  │   (Python)   │───→│   (27017)    │    │   (6379)     │          │
│  │   Port 8082  │    └──────────────┘    └──────────────┘          │
│  └──────────────┘           ↑                   ↑                  │
│         │                   │                   │                  │
│         ▼                   │                   │                  │
│  ┌──────────────┐           │                   │                  │
│  │   Volumes    │───────────┴───────────────────┘                  │
│  │ uploadfiles/ │                                                   │
│  │ data/        │                                                   │
│  │ logs/        │                                                   │
│  └──────────────┘                                                   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                          ┌──────────────┐
                          │   Ollama     │ ← 可選：主機或獨立容器
                          │   (11434)    │
                          └──────────────┘
```

### 2.3 資料庫用途分析

| 資料庫 | 用途 | 資料類型 | 資料量預估 |
|--------|------|----------|-----------|
| **MongoDB** | 聊天歷史 | chat_sessions 集合 | 中等 (MB~GB) |
| **Redis** | 快取層 | embeddings, queries, results | 低~中 (MB) |
| **SQLite** | 檔案/技能元資料 | skill_metadata, file_metadata | 低 (~20MB) |
| **FAISS** | 向量索引 | 嵌入向量 | 中~高 (數百MB) |

### 2.4 檔案儲存分析

```
DocAI/
├── uploadfiles/          ← 【Volume】用戶上傳的原始檔案
│   ├── pdf/              (PDF 文件)
│   ├── docx/             (Word 文件)
│   ├── pptx/             (PowerPoint)
│   ├── txt/              (純文字)
│   └── md/               (Markdown)
│
├── data/                 ← 【Volume 或 Image 內】資料庫與索引
│   ├── skill_metadata.db (SQLite - 技能元資料)
│   ├── docai.db          (SQLite - 檔案元資料)
│   └── faiss_indices/    (FAISS 向量索引)
│       ├── files/
│       └── skills/
│
└── logs/                 ← 【Volume】日誌檔案
    └── server.log
```

---

## 3. 容器化策略

### 3.1 推薦方案：Docker Compose 多容器架構

**優點**：
- 服務隔離，易於維護
- 獨立擴展能力
- 符合微服務架構模式
- 便於開發與生產環境切換

**架構決策**：

| 決策點 | 選擇 | 理由 |
|--------|------|------|
| MongoDB/Redis | 容器內運行 | 完整隔離、可移植 |
| SQLite | 主應用容器內 | 嵌入式資料庫，無需獨立服務 |
| FAISS | 主應用容器內 | 嵌入式向量庫，無需獨立服務 |
| uploadfiles | 外部 Volume | 用戶資料持久化、便於備份 |
| data/ | Named Volume | 資料庫持久化 |
| Ollama | 外部服務 | GPU 依賴、已有獨立部署 |

### 3.2 Volume 配置策略

```yaml
volumes:
  # 持久化資料 Volumes
  mongodb_data:         # MongoDB 資料持久化
  redis_data:           # Redis 資料持久化（可選 RDB/AOF）
  docai_data:           # SQLite + FAISS 索引

  # 綁定掛載 (Bind Mounts)
  ./uploadfiles:/app/uploadfiles   # 用戶上傳檔案
  ./logs:/app/logs                 # 日誌輸出
```

---

## 4. Docker 映像設計

### 4.1 Dockerfile 結構

```dockerfile
# ============================================
# Stage 1: Builder
# ============================================
FROM python:3.11-slim AS builder

WORKDIR /build

# 安裝編譯依賴
RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# 複製依賴清單
COPY requirements.txt .

# 建立虛擬環境並安裝依賴
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ============================================
# Stage 2: Runtime
# ============================================
FROM python:3.11-slim AS runtime

# 設定工作目錄
WORKDIR /app

# 安裝執行時依賴
RUN apt-get update && apt-get install -y \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 從 builder 複製虛擬環境
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 複製應用程式碼
COPY app/ ./app/
COPY main.py .
COPY template/ ./template/
COPY static/ ./static/

# 建立必要目錄
RUN mkdir -p /app/uploadfiles/pdf \
             /app/uploadfiles/docx \
             /app/uploadfiles/pptx \
             /app/uploadfiles/txt \
             /app/uploadfiles/md \
             /app/data \
             /app/logs

# 設定環境變數
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 暴露埠號
EXPOSE 8082

# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8082/ || exit 1

# 啟動命令
CMD ["python", "main.py"]
```

### 4.2 映像層結構

```
┌─────────────────────────────────────────┐
│ Layer 7: CMD / Entrypoint               │
├─────────────────────────────────────────┤
│ Layer 6: 應用程式碼 (app/, main.py)      │
├─────────────────────────────────────────┤
│ Layer 5: 目錄結構 (data/, logs/)         │
├─────────────────────────────────────────┤
│ Layer 4: Python 虛擬環境 (/opt/venv)     │
├─────────────────────────────────────────┤
│ Layer 3: 系統執行時依賴 (libgomp1)       │
├─────────────────────────────────────────┤
│ Layer 2: Python 3.11 Slim               │
├─────────────────────────────────────────┤
│ Layer 1: Debian Base                    │
└─────────────────────────────────────────┘
```

---

## 5. Docker Compose 配置

### 5.1 完整 docker-compose.yml

```yaml
version: '3.8'

services:
  # ==========================================
  # DocAI 主應用
  # ==========================================
  docai-app:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: docai-app
    ports:
      - "8082:8082"
    environment:
      # MongoDB
      - MONGODB_URI=mongodb://mongodb:27017
      - MONGODB_DATABASE=docai
      - MONGODB_CHAT_COLLECTION=chat_sessions
      # Redis
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_DB=0
      # LLM (外部 Ollama)
      - LLM_PROVIDER_BASE_URL=http://host.docker.internal:11434/v1
      - DEFAULT_LLM_MODEL=gpt-oss:20b
      # 應用設定
      - APP_NAME=DocAI
      - DEBUG=False
      - LOG_LEVEL=INFO
      # 路徑設定
      - UPLOAD_DIR=/app/uploadfiles
      - PDF_UPLOAD_DIR=/app/uploadfiles/pdf
      - SQLITE_DB_PATH=/app/data/skill_metadata.db
    volumes:
      # 用戶上傳檔案 - 外部 Volume
      - ./uploadfiles:/app/uploadfiles
      # 資料庫與索引 - Named Volume
      - docai_data:/app/data
      # 日誌 - 外部 Volume
      - ./logs:/app/logs
    depends_on:
      mongodb:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - docai-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8082/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  # ==========================================
  # MongoDB 容器
  # ==========================================
  mongodb:
    image: mongo:7.0
    container_name: docai-mongodb
    ports:
      - "27017:27017"
    environment:
      # 可選：設定認證
      # - MONGO_INITDB_ROOT_USERNAME=admin
      # - MONGO_INITDB_ROOT_PASSWORD=password
      - MONGO_INITDB_DATABASE=docai
    volumes:
      - mongodb_data:/data/db
      - mongodb_config:/data/configdb
    networks:
      - docai-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 20s

  # ==========================================
  # Redis 容器
  # ==========================================
  redis:
    image: redis:7-alpine
    container_name: docai-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    networks:
      - docai-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s

# ==========================================
# Volumes 定義
# ==========================================
volumes:
  mongodb_data:
    driver: local
  mongodb_config:
    driver: local
  redis_data:
    driver: local
  docai_data:
    driver: local

# ==========================================
# Networks 定義
# ==========================================
networks:
  docai-network:
    driver: bridge
```

### 5.2 生產環境增強版 (docker-compose.prod.yml)

```yaml
version: '3.8'

services:
  docai-app:
    extends:
      file: docker-compose.yml
      service: docai-app
    environment:
      - DEBUG=False
      - LOG_LEVEL=WARNING
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '2'
          memory: 4G

  mongodb:
    extends:
      file: docker-compose.yml
      service: mongodb
    environment:
      - MONGO_INITDB_ROOT_USERNAME=${MONGO_USER}
      - MONGO_INITDB_ROOT_PASSWORD=${MONGO_PASSWORD}
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G

  redis:
    extends:
      file: docker-compose.yml
      service: redis
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 1G
```

---

## 6. 環境變數配置

### 6.1 容器化專用 .env.docker

```bash
# ============================================
# DocAI Docker Environment Configuration
# ============================================

# Application
APP_NAME=DocAI
APP_VERSION=1.0.0
DEBUG=False

# LLM Provider (外部 Ollama)
LLM_PROVIDER_BASE_URL=http://host.docker.internal:11434/v1
DEFAULT_LLM_MODEL=gpt-oss:20b
LLM_TEMPERATURE=0.0
LLM_MAX_TOKENS=2048

# Embedding
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIMENSION=1024

# MongoDB (容器內)
MONGODB_URI=mongodb://mongodb:27017
MONGODB_DATABASE=docai
MONGODB_CHAT_COLLECTION=chat_sessions

# Redis (容器內)
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# SQLite (容器內)
SQLITE_DB_PATH=/app/data/skill_metadata.db

# File Paths (容器內路徑)
UPLOAD_DIR=/app/uploadfiles
PDF_UPLOAD_DIR=/app/uploadfiles/pdf

# Vector Store
VECTOR_STORE_BACKEND=faiss
VECTOR_STORE_PATH=/app/data/vector_store

# Server
HOST=0.0.0.0
PORT=8082
LOG_LEVEL=INFO
```

### 6.2 環境變數對照表

| 變數 | 本機開發值 | 容器化值 | 說明 |
|------|-----------|---------|------|
| `MONGODB_URI` | mongodb://localhost:27017 | mongodb://mongodb:27017 | 服務名稱解析 |
| `REDIS_HOST` | localhost | redis | 容器網路內部名稱 |
| `LLM_PROVIDER_BASE_URL` | http://localhost:11434 | http://host.docker.internal:11434 | 訪問主機服務 |
| `UPLOAD_DIR` | ./uploadfiles | /app/uploadfiles | 容器內路徑 |
| `SQLITE_DB_PATH` | ./data/skill_metadata.db | /app/data/skill_metadata.db | 容器內路徑 |

---

## 7. 資料遷移策略

### 7.1 SQLite 資料遷移

```bash
# 1. 停止服務
docker compose down

# 2. 複製現有資料庫到 Volume
docker run --rm \
  -v docai_data:/app/data \
  -v $(pwd)/data:/source \
  alpine cp -a /source/. /app/data/

# 3. 啟動服務
docker compose up -d
```

### 7.2 FAISS 索引遷移

```bash
# 複製 FAISS 索引
docker run --rm \
  -v docai_data:/app/data \
  -v $(pwd)/data/faiss_indices:/source \
  alpine cp -a /source /app/data/faiss_indices
```

### 7.3 MongoDB 資料匯入（如有現有資料）

```bash
# 匯出現有 MongoDB 資料
mongodump --db docai --out ./mongo_backup

# 匯入到容器
docker compose exec -T mongodb mongorestore --db docai /mongo_backup/docai
```

---

## 8. 部署流程

### 8.1 首次部署

```bash
# 1. 建立映像
docker compose build

# 2. 啟動服務
docker compose up -d

# 3. 檢查狀態
docker compose ps
docker compose logs -f docai-app

# 4. 健康檢查
curl http://localhost:8082/
curl http://localhost:8082/docs
```

### 8.2 更新部署

```bash
# 1. 拉取最新程式碼
git pull

# 2. 重新建立映像
docker compose build docai-app

# 3. 滾動更新
docker compose up -d --no-deps docai-app

# 4. 清理舊映像
docker image prune -f
```

### 8.3 完整重啟

```bash
# 停止所有服務
docker compose down

# 清理並重啟
docker compose up -d --build
```

---

## 9. 監控與維運

### 9.1 日誌查看

```bash
# 查看所有服務日誌
docker compose logs -f

# 只看應用日誌
docker compose logs -f docai-app

# 查看 MongoDB 日誌
docker compose logs -f mongodb
```

### 9.2 資源監控

```bash
# 即時資源使用
docker stats

# 容器詳細資訊
docker compose exec docai-app df -h
docker compose exec mongodb mongosh --eval "db.stats()"
docker compose exec redis redis-cli INFO memory
```

### 9.3 備份策略

```bash
#!/bin/bash
# backup.sh - 自動備份腳本

BACKUP_DIR="./backups/$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR

# 備份 MongoDB
docker compose exec -T mongodb mongodump --out /dump
docker compose cp mongodb:/dump $BACKUP_DIR/mongodb

# 備份 SQLite
docker compose cp docai-app:/app/data/skill_metadata.db $BACKUP_DIR/

# 備份 FAISS 索引
docker compose cp docai-app:/app/data/faiss_indices $BACKUP_DIR/

# 備份 Redis (RDB)
docker compose exec redis redis-cli BGSAVE
sleep 5
docker compose cp redis:/data/dump.rdb $BACKUP_DIR/redis.rdb

echo "Backup completed: $BACKUP_DIR"
```

---

## 10. 安全性考量

### 10.1 生產環境建議

| 項目 | 建議 | 優先級 |
|------|------|--------|
| MongoDB 認證 | 啟用 username/password | 高 |
| Redis 密碼 | 設定 requirepass | 高 |
| 網路隔離 | 限制外部存取資料庫埠 | 高 |
| HTTPS | 使用反向代理 (Nginx/Traefik) | 中 |
| 映像安全 | 定期更新基礎映像 | 中 |

### 10.2 網路安全配置

```yaml
# 生產環境：不暴露資料庫埠
services:
  mongodb:
    ports: []  # 移除外部映射
    # 只在內部網路可存取

  redis:
    ports: []  # 移除外部映射
```

---

## 11. 實施時程建議

| 階段 | 任務 | 預估時間 |
|------|------|----------|
| **Phase 1** | 建立 Dockerfile | 2 小時 |
| **Phase 2** | 建立 docker-compose.yml | 2 小時 |
| **Phase 3** | 環境變數配置與測試 | 1 小時 |
| **Phase 4** | 資料遷移腳本 | 1 小時 |
| **Phase 5** | 整合測試 | 2 小時 |
| **Phase 6** | 文檔與部署指南 | 1 小時 |
| **總計** | | **9 小時** |

---

## 12. 已知限制與注意事項

### 12.1 Ollama LLM 連接

由於 Ollama 需要 GPU 支援，建議：
- 選項 A：Ollama 在主機運行，容器透過 `host.docker.internal` 連接
- 選項 B：使用 NVIDIA Docker 運行 Ollama 容器（需 nvidia-docker）

### 12.2 GPU 支援

若需 CUDA 加速 embedding：

```yaml
services:
  docai-app:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

### 12.3 檔案權限

確保 Volume 掛載的目錄有正確權限：

```bash
# 設定正確權限
chmod -R 755 ./uploadfiles
chmod -R 755 ./logs
```

---

## 13. 下一步行動

1. [ ] 建立 `Dockerfile`
2. [ ] 建立 `docker-compose.yml`
3. [ ] 建立 `.env.docker` 環境變數檔
4. [ ] 建立資料遷移腳本
5. [ ] 進行本機測試
6. [ ] 建立部署文檔
7. [ ] 建立備份/還原腳本

---

*文件結束 - DocAI Dockerization Plan v1.0*
