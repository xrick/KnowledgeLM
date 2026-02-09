# Docker 容器化技術指南

## 簡介
Docker 是一個開放平台，用於開發、部署和運行應用程序。

## 基本概念

### 鏡像 (Image)
Docker 鏡像是一個只讀模板，包含運行應用程序所需的所有內容。

### 容器 (Container)
容器是鏡像的運行實例，可以被創建、啟動、停止和刪除。

### Dockerfile
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

## Docker Compose
Docker Compose 用於定義和管理多容器 Docker 應用程序。

## 最佳實踐
1. 使用多階段構建減少鏡像大小
2. 不要在鏡像中存儲敏感信息
3. 使用 .dockerignore 排除不需要的文件
4. 優先使用官方基礎鏡像
