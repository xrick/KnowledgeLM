# DocAI Docker Deployment

Docker 容器化部署配置，包含 DocAI 應用、MongoDB 和 Redis。

## 目錄結構

```
docker/
├── docker-compose.yml      # 服務編排配置
├── .env.example            # 環境變數範本
├── .dockerignore           # Docker 忽略檔案
├── Makefile                # 便捷命令
├── docai/
│   ├── Dockerfile          # DocAI 應用映像
│   └── entrypoint.sh       # 容器啟動腳本
└── mongodb/
    └── init-scripts/
        └── init-docai.js   # MongoDB 初始化腳本
```

## 快速開始

### 1. 準備環境

```bash
# 複製環境變數配置
cp .env.example .env

# 編輯 .env 檔案，設定 LLM 服務位址等
vim .env
```

### 2. 構建並啟動

```bash
# 使用 Makefile
make build
make up

# 或直接使用 docker-compose
docker-compose build
docker-compose up -d
```

### 3. 檢查服務狀態

```bash
make status
# 或
docker-compose ps
```

### 4. 訪問服務

- **DocAI 應用**: http://localhost:8082
- **健康檢查**: http://localhost:8082/health
- **MongoDB**: localhost:27017
- **Redis**: localhost:6379

## 服務架構

```
┌─────────────────────────────────────────────────────────┐
│                    docai-network                         │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐ │
│  │  docai-app   │   │   mongodb    │   │    redis     │ │
│  │  (FastAPI)   │──▶│  (Mongo 7)   │   │  (Redis 7)   │ │
│  │   :8082      │   │   :27017     │   │   :6379      │ │
│  └──────────────┘   └──────────────┘   └──────────────┘ │
│         │                                      │         │
│         └──────────────────────────────────────┘         │
│                                                          │
└─────────────────────────────────────────────────────────┘
          │
          ▼ (host.docker.internal)
    ┌──────────────┐     ┌──────────────┐
    │   Ollama     │     │   Milvus     │
    │   :11434     │     │   :19530     │
    └──────────────┘     └──────────────┘
```

## 環境變數說明

### LLM 設定

| 變數 | 說明 | 預設值 |
|------|------|--------|
| `LLM_PROVIDER_BASE_URL` | LLM API 位址 | `http://host.docker.internal:11434/v1` |
| `LLM_PROVIDER_API_KEY` | API 金鑰 | `ollama` |
| `DEFAULT_LLM_MODEL` | 預設模型 | `gpt-oss:20b` |
| `LLM_TIMEOUT` | 請求超時（秒）| `300.0` |

### 資料庫設定

| 變數 | 說明 | 預設值 |
|------|------|--------|
| `MONGODB_URI` | MongoDB 連接字串 | `mongodb://mongodb:27017/docai` |
| `REDIS_HOST` | Redis 主機 | `redis` |
| `REDIS_PORT` | Redis 端口 | `6379` |
| `MILVUS_HOST` | Milvus 主機 | `host.docker.internal` |
| `MILVUS_PORT` | Milvus 端口 | `19530` |

## 常用命令

### Makefile 命令

```bash
make help       # 顯示所有命令
make build      # 構建映像
make up         # 啟動服務
make down       # 停止服務
make restart    # 重啟服務
make logs       # 查看應用日誌
make logs-all   # 查看所有日誌
make shell      # 進入應用容器
make shell-mongo # 進入 MongoDB shell
make status     # 查看服務狀態
make health     # 健康檢查
make backup     # 備份 MongoDB
make clean      # 清理所有容器和卷
```

### Docker Compose 命令

```bash
# 啟動服務（背景）
docker-compose up -d

# 查看日誌
docker-compose logs -f docai-app

# 重啟特定服務
docker-compose restart docai-app

# 停止並移除容器
docker-compose down

# 停止並移除容器和卷
docker-compose down -v
```

## 資料持久化

### Volumes 說明

| Volume | 用途 | 容器路徑 |
|--------|------|----------|
| `docai_uploads` | 上傳檔案 | `/app/data/uploads` |
| `docai_faiss` | FAISS 向量索引 | `/app/data/faiss_indices` |
| `docai_skills` | Skill 資料 | `/app/data/skills` |
| `docai_sqlite` | SQLite 資料庫 | `/app/data/db` |
| `docai_logs` | 應用日誌 | `/app/logs` |
| `docai_mongodb_data` | MongoDB 資料 | `/data/db` |
| `docai_redis_data` | Redis 資料 | `/data` |

### 備份與還原

```bash
# 備份 MongoDB
make backup

# 還原 MongoDB
make restore

# 手動備份 volumes
docker run --rm -v docai_uploads:/data -v $(pwd)/backups:/backup \
    alpine tar czf /backup/uploads_backup.tar.gz -C /data .
```

## 開發模式

### 掛載本地目錄

編輯 `docker-compose.yml`，取消註解以下部分：

```yaml
volumes:
  # 開發時掛載本地目錄
  - ./data/uploads:/app/data/uploads
  - ./data/faiss_indices:/app/data/faiss_indices
```

### 查看容器日誌

```bash
# 即時查看
docker-compose logs -f docai-app

# 查看最後 100 行
docker-compose logs --tail=100 docai-app
```

## 生產環境建議

### 1. 安全性

```yaml
# 啟用 MongoDB 認證
environment:
  - MONGO_INITDB_ROOT_USERNAME=admin
  - MONGO_INITDB_ROOT_PASSWORD=強密碼
```

### 2. 資源限制

```yaml
services:
  docai-app:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
```

### 3. 日誌管理

```yaml
services:
  docai-app:
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
        max-file: "3"
```

## 故障排除

### 服務無法啟動

```bash
# 檢查日誌
docker-compose logs docai-app

# 檢查容器狀態
docker-compose ps

# 檢查網路
docker network ls
docker network inspect docai-network
```

### MongoDB 連接問題

```bash
# 測試 MongoDB 連接
docker-compose exec mongodb mongosh --eval "db.adminCommand('ping')"

# 查看 MongoDB 日誌
docker-compose logs mongodb
```

### 無法連接 Ollama

確保 Ollama 在主機上運行並監聽所有介面：

```bash
# 在主機上
OLLAMA_HOST=0.0.0.0 ollama serve
```

## 版本資訊

- **DocAI**: 1.0.0
- **Python**: 3.11
- **MongoDB**: 7.0
- **Redis**: 7-alpine
- **FastAPI**: 0.109.0
