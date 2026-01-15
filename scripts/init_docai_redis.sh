#!/bin/bash
# =============================================================================
# DocAI Redis Initialization Script
# =============================================================================
# 此腳本用於初始化和驗證 Redis 配置
#
# 使用方式:
#   chmod +x init_docai_redis.sh
#   ./init_docai_redis.sh
#
# 可選參數:
#   ./init_docai_redis.sh [host] [port]
#   ./init_docai_redis.sh localhost 6379
#
# =============================================================================

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 默認配置
REDIS_HOST="${1:-localhost}"
REDIS_PORT="${2:-6379}"

print_header() {
    echo -e "\n${BLUE}═══════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════════${NC}\n"
}

print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_error() { echo -e "${RED}❌ $1${NC}"; }
print_info() { echo -e "${CYAN}ℹ️  $1${NC}"; }

# =============================================================================
# 主程序
# =============================================================================
print_header "DocAI Redis Initialization"

echo "Redis 連接配置:"
echo "  Host: $REDIS_HOST"
echo "  Port: $REDIS_PORT"
echo ""

# 檢查 redis-cli 是否安裝
if ! command -v redis-cli &> /dev/null; then
    print_error "redis-cli 未安裝"
    echo "請先安裝 Redis 客戶端工具"
    exit 1
fi

# 測試連接
print_info "測試 Redis 連接..."
if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping | grep -q "PONG"; then
    print_success "Redis 連接成功"
else
    print_error "無法連接到 Redis ($REDIS_HOST:$REDIS_PORT)"
    echo "請確認 Redis 服務正在運行"
    exit 1
fi

# =============================================================================
# 初始化 DocAI 配置
# =============================================================================
print_header "初始化 DocAI 配置"

# 設置初始化標記
INIT_TIME=$(date -Iseconds)
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET "docai:init" "$INIT_TIME" > /dev/null
print_success "設置初始化時間: $INIT_TIME"

# 設置版本
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET "docai:version" "1.0.0" > /dev/null
print_success "設置版本: 1.0.0"

# 設置 TTL 配置 (使用 Hash)
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HSET "docai:config" \
    "embedding_ttl" "86400" \
    "query_expansion_ttl" "3600" \
    "search_results_ttl" "1800" \
    "file_metadata_ttl" "21600" > /dev/null
print_success "設置 TTL 配置"

# =============================================================================
# 顯示 Key 模式說明
# =============================================================================
print_header "DocAI Redis Key 模式"

echo -e "${CYAN}┌─────────────────────────────────────────────────────────────────┐${NC}"
echo -e "${CYAN}│ Key Pattern            │ TTL      │ Description               │${NC}"
echo -e "${CYAN}├─────────────────────────────────────────────────────────────────┤${NC}"
echo -e "${CYAN}│${NC} emb:{text_hash}        │ 24h      │ Embedding 向量快取        ${CYAN}│${NC}"
echo -e "${CYAN}│${NC} qexp:{query_hash}      │ 1h       │ 查詢擴展結果快取          ${CYAN}│${NC}"
echo -e "${CYAN}│${NC} search:{hash}          │ 30min    │ 搜尋結果快取              ${CYAN}│${NC}"
echo -e "${CYAN}│${NC} file:{file_id}         │ 6h       │ 文件元數據快取            ${CYAN}│${NC}"
echo -e "${CYAN}│${NC} docai:init             │ -        │ 初始化時間戳              ${CYAN}│${NC}"
echo -e "${CYAN}│${NC} docai:version          │ -        │ 系統版本                  ${CYAN}│${NC}"
echo -e "${CYAN}│${NC} docai:config           │ -        │ TTL 配置 (Hash)           ${CYAN}│${NC}"
echo -e "${CYAN}└─────────────────────────────────────────────────────────────────┘${NC}"
echo ""

# =============================================================================
# 驗證
# =============================================================================
print_header "驗證初始化"

# 驗證 key 是否正確設置
echo "驗證已設置的 keys:"

INIT_VALUE=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET "docai:init")
if [ -n "$INIT_VALUE" ]; then
    print_success "docai:init = $INIT_VALUE"
else
    print_error "docai:init 未設置"
fi

VERSION_VALUE=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET "docai:version")
if [ -n "$VERSION_VALUE" ]; then
    print_success "docai:version = $VERSION_VALUE"
else
    print_error "docai:version 未設置"
fi

CONFIG_TTL=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" HGET "docai:config" "embedding_ttl")
if [ -n "$CONFIG_TTL" ]; then
    print_success "docai:config.embedding_ttl = ${CONFIG_TTL}s"
else
    print_error "docai:config 未設置"
fi

# =============================================================================
# 顯示 Redis 狀態
# =============================================================================
print_header "Redis 服務狀態"

# 顯示版本
REDIS_VERSION=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" INFO server | grep redis_version | cut -d: -f2 | tr -d '\r')
echo "Redis 版本: $REDIS_VERSION"

# 顯示已使用記憶體
USED_MEMORY=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" INFO memory | grep used_memory_human | cut -d: -f2 | tr -d '\r')
echo "已使用記憶體: $USED_MEMORY"

# 顯示連接數
CONNECTED_CLIENTS=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" INFO clients | grep connected_clients | cut -d: -f2 | tr -d '\r')
echo "連接客戶端數: $CONNECTED_CLIENTS"

# 顯示 key 數量
DBSIZE=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" DBSIZE | awk '{print $2}')
echo "Key 總數: $DBSIZE"

# =============================================================================
# 完成
# =============================================================================
print_header "初始化完成"

echo "📋 環境變數配置 (.env):"
echo ""
echo "  # Redis Settings"
echo "  REDIS_HOST=$REDIS_HOST"
echo "  REDIS_PORT=$REDIS_PORT"
echo "  REDIS_DB=0"
echo "  REDIS_EMBEDDING_TTL=86400"
echo "  REDIS_QUERY_EXPANSION_TTL=3600"
echo "  REDIS_SEARCH_RESULTS_TTL=1800"
echo ""
echo "🔗 連接 URL: redis://$REDIS_HOST:$REDIS_PORT/0"
echo ""
print_success "DocAI Redis 初始化完成！"
