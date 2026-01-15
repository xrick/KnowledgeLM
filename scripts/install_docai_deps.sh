#!/bin/bash
# =============================================================================
# DocAI Dependencies Installation Script
# =============================================================================
# 此腳本將在 Linux 系統上安裝:
# - MongoDB 7.0 (Community Edition)
# - Redis Server 7.x
# 並初始化 DocAI 所需的資料結構
#
# 支援的 Linux 發行版:
# - Ubuntu 20.04/22.04/24.04
# - Debian 11/12
# - CentOS/RHEL 8/9
# - Rocky Linux 8/9
#
# 使用方式:
#   chmod +x install_docai_deps.sh
#   sudo ./install_docai_deps.sh
#
# 作者: SuperClaude Framework
# 日期: 2026-01-14
# =============================================================================

set -e  # Exit on any error

# =============================================================================
# 顏色定義
# =============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# =============================================================================
# 輔助函數
# =============================================================================
print_header() {
    echo -e "\n${BLUE}=====================================================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}=====================================================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# 檢測 Linux 發行版
detect_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        DISTRO=$ID
        VERSION=$VERSION_ID
        CODENAME=$VERSION_CODENAME
    elif [ -f /etc/redhat-release ]; then
        DISTRO="rhel"
        VERSION=$(cat /etc/redhat-release | grep -oE '[0-9]+' | head -1)
    else
        DISTRO="unknown"
        VERSION="unknown"
    fi

    echo "Detected: $DISTRO $VERSION"
}

# 檢查是否為 root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        print_error "請使用 sudo 執行此腳本"
        echo "Usage: sudo ./install_docai_deps.sh"
        exit 1
    fi
}

# =============================================================================
# MongoDB 安裝函數
# =============================================================================
install_mongodb_ubuntu_debian() {
    print_header "安裝 MongoDB 7.0 (Ubuntu/Debian)"

    # 安裝必要工具
    apt-get update
    apt-get install -y gnupg curl

    # 添加 MongoDB GPG key
    curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | \
        gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor

    # 添加 MongoDB 倉庫
    if [ "$DISTRO" = "ubuntu" ]; then
        echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/ubuntu ${CODENAME}/mongodb-org/7.0 multiverse" | \
            tee /etc/apt/sources.list.d/mongodb-org-7.0.list
    elif [ "$DISTRO" = "debian" ]; then
        echo "deb [ signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/debian ${CODENAME}/mongodb-org/7.0 main" | \
            tee /etc/apt/sources.list.d/mongodb-org-7.0.list
    fi

    # 安裝 MongoDB
    apt-get update
    apt-get install -y mongodb-org

    # 啟動並設定開機啟動
    systemctl daemon-reload
    systemctl start mongod
    systemctl enable mongod

    print_success "MongoDB 7.0 安裝完成"
}

install_mongodb_rhel() {
    print_header "安裝 MongoDB 7.0 (RHEL/CentOS/Rocky)"

    # 創建 MongoDB 倉庫文件
    cat > /etc/yum.repos.d/mongodb-org-7.0.repo << 'EOF'
[mongodb-org-7.0]
name=MongoDB Repository
baseurl=https://repo.mongodb.org/yum/redhat/$releasever/mongodb-org/7.0/x86_64/
gpgcheck=1
enabled=1
gpgkey=https://www.mongodb.org/static/pgp/server-7.0.asc
EOF

    # 安裝 MongoDB
    if command -v dnf &> /dev/null; then
        dnf install -y mongodb-org
    else
        yum install -y mongodb-org
    fi

    # 啟動並設定開機啟動
    systemctl daemon-reload
    systemctl start mongod
    systemctl enable mongod

    print_success "MongoDB 7.0 安裝完成"
}

# =============================================================================
# Redis 安裝函數
# =============================================================================
install_redis_ubuntu_debian() {
    print_header "安裝 Redis Server (Ubuntu/Debian)"

    # 添加官方 Redis 倉庫
    apt-get update
    apt-get install -y lsb-release curl gpg

    curl -fsSL https://packages.redis.io/gpg | gpg --dearmor -o /usr/share/keyrings/redis-archive-keyring.gpg

    echo "deb [signed-by=/usr/share/keyrings/redis-archive-keyring.gpg] https://packages.redis.io/deb $(lsb_release -cs) main" | \
        tee /etc/apt/sources.list.d/redis.list

    # 安裝 Redis
    apt-get update
    apt-get install -y redis

    # 啟動並設定開機啟動
    systemctl start redis-server
    systemctl enable redis-server

    print_success "Redis Server 安裝完成"
}

install_redis_rhel() {
    print_header "安裝 Redis Server (RHEL/CentOS/Rocky)"

    # 啟用 EPEL 倉庫
    if command -v dnf &> /dev/null; then
        dnf install -y epel-release
        dnf install -y redis
    else
        yum install -y epel-release
        yum install -y redis
    fi

    # 啟動並設定開機啟動
    systemctl start redis
    systemctl enable redis

    print_success "Redis Server 安裝完成"
}

# =============================================================================
# 驗證安裝
# =============================================================================
verify_mongodb() {
    print_header "驗證 MongoDB 安裝"

    # 等待 MongoDB 完全啟動
    sleep 3

    if systemctl is-active --quiet mongod; then
        print_success "MongoDB 服務正在運行"
    else
        print_error "MongoDB 服務未運行"
        systemctl status mongod
        return 1
    fi

    # 測試連接
    if mongosh --eval "db.runCommand({ ping: 1 })" --quiet 2>/dev/null; then
        print_success "MongoDB 連接測試成功"

        # 顯示版本
        VERSION=$(mongosh --eval "db.version()" --quiet 2>/dev/null)
        print_info "MongoDB 版本: $VERSION"
    else
        print_warning "無法連接 MongoDB，可能需要等待服務完全啟動"
    fi
}

verify_redis() {
    print_header "驗證 Redis 安裝"

    # 等待 Redis 完全啟動
    sleep 2

    # 檢查服務狀態（不同發行版服務名稱可能不同）
    if systemctl is-active --quiet redis-server 2>/dev/null || systemctl is-active --quiet redis 2>/dev/null; then
        print_success "Redis 服務正在運行"
    else
        print_error "Redis 服務未運行"
        return 1
    fi

    # 測試連接
    if redis-cli ping | grep -q "PONG"; then
        print_success "Redis 連接測試成功"

        # 顯示版本
        VERSION=$(redis-cli INFO server | grep redis_version | cut -d: -f2 | tr -d '\r')
        print_info "Redis 版本: $VERSION"
    else
        print_warning "無法連接 Redis"
    fi
}

# =============================================================================
# DocAI 資料結構初始化
# =============================================================================
init_mongodb_schema() {
    print_header "初始化 MongoDB 資料結構 (DocAI)"

    # 創建初始化腳本
    cat > /tmp/docai_mongo_init.js << 'EOF'
// =============================================================================
// DocAI MongoDB Schema Initialization
// =============================================================================
// Database: docai
// Collection: chat_sessions
//
// Schema:
// {
//     "_id": ObjectId,
//     "session_id": str (unique),
//     "user_id": str (optional),
//     "file_ids": [str],
//     "created_at": datetime,
//     "updated_at": datetime,
//     "messages": [
//         {
//             "role": "user" | "assistant" | "system",
//             "content": str,
//             "timestamp": datetime,
//             "metadata": {}
//         }
//     ],
//     "metadata": {}
// }
// =============================================================================

// 切換到 docai 資料庫
use docai;

// 創建 chat_sessions 集合（如果不存在）
if (!db.getCollectionNames().includes("chat_sessions")) {
    db.createCollection("chat_sessions", {
        validator: {
            $jsonSchema: {
                bsonType: "object",
                required: ["session_id", "created_at", "updated_at", "messages"],
                properties: {
                    session_id: {
                        bsonType: "string",
                        description: "Unique session identifier - required"
                    },
                    user_id: {
                        bsonType: ["string", "null"],
                        description: "Optional user identifier"
                    },
                    file_ids: {
                        bsonType: "array",
                        items: { bsonType: "string" },
                        description: "Files associated with this session"
                    },
                    created_at: {
                        bsonType: "date",
                        description: "Session creation timestamp - required"
                    },
                    updated_at: {
                        bsonType: "date",
                        description: "Last update timestamp - required"
                    },
                    messages: {
                        bsonType: "array",
                        items: {
                            bsonType: "object",
                            required: ["role", "content", "timestamp"],
                            properties: {
                                role: {
                                    enum: ["user", "assistant", "system"],
                                    description: "Message role - required"
                                },
                                content: {
                                    bsonType: "string",
                                    description: "Message content - required"
                                },
                                timestamp: {
                                    bsonType: "date",
                                    description: "Message timestamp - required"
                                },
                                metadata: {
                                    bsonType: "object",
                                    description: "Optional message metadata"
                                }
                            }
                        },
                        description: "Array of chat messages - required"
                    },
                    metadata: {
                        bsonType: "object",
                        description: "Optional session-level metadata"
                    }
                }
            }
        },
        validationLevel: "moderate",
        validationAction: "warn"
    });
    print("✅ Created collection: chat_sessions");
} else {
    print("ℹ️  Collection chat_sessions already exists");
}

// 創建索引
db.chat_sessions.createIndex({ "session_id": 1 }, { unique: true, name: "idx_session_id_unique" });
db.chat_sessions.createIndex({ "user_id": 1 }, { name: "idx_user_id" });
db.chat_sessions.createIndex({ "created_at": -1 }, { name: "idx_created_at" });
db.chat_sessions.createIndex({ "updated_at": -1 }, { name: "idx_updated_at" });
db.chat_sessions.createIndex({ "file_ids": 1 }, { name: "idx_file_ids" });

print("✅ Created indexes for chat_sessions");

// 顯示集合資訊
print("\n📊 Collection Info:");
print("   Database: docai");
print("   Collection: chat_sessions");
printjson(db.chat_sessions.getIndexes());

// 插入測試文檔（可選）
var testDoc = {
    session_id: "test_session_init",
    user_id: "system",
    file_ids: [],
    created_at: new Date(),
    updated_at: new Date(),
    messages: [
        {
            role: "system",
            content: "DocAI MongoDB initialized successfully",
            timestamp: new Date(),
            metadata: { init_script: true }
        }
    ],
    metadata: {
        init_version: "1.0",
        init_date: new Date().toISOString()
    }
};

// 檢查是否已存在測試文檔
var existing = db.chat_sessions.findOne({ session_id: "test_session_init" });
if (!existing) {
    db.chat_sessions.insertOne(testDoc);
    print("✅ Inserted test document");
} else {
    print("ℹ️  Test document already exists");
}

print("\n🎉 DocAI MongoDB initialization complete!");
EOF

    # 執行初始化腳本
    if mongosh --file /tmp/docai_mongo_init.js 2>/dev/null; then
        print_success "MongoDB 資料結構初始化完成"
    else
        print_warning "MongoDB 初始化可能需要手動執行"
        print_info "手動執行: mongosh --file /tmp/docai_mongo_init.js"
    fi

    # 清理臨時文件
    # rm -f /tmp/docai_mongo_init.js
}

init_redis_schema() {
    print_header "初始化 Redis 資料結構 (DocAI)"

    # Redis 是 key-value 存儲，不需要預先創建結構
    # 但我們可以設置一些初始配置和測試 key

    print_info "Redis Key 模式說明:"
    echo ""
    echo "  📦 Embedding Cache:     emb:{text_hash}"
    echo "     TTL: 24 hours (86400 seconds)"
    echo ""
    echo "  📦 Query Expansion:     qexp:{query_hash}"
    echo "     TTL: 1 hour (3600 seconds)"
    echo ""
    echo "  📦 Search Results:      search:{hash}"
    echo "     TTL: 30 minutes (1800 seconds)"
    echo ""
    echo "  📦 File Metadata:       file:{file_id}"
    echo "     TTL: 6 hours (21600 seconds)"
    echo ""

    # 設置初始化標記
    redis-cli SET "docai:init" "$(date -Iseconds)" EX 86400 > /dev/null 2>&1
    redis-cli SET "docai:version" "1.0.0" > /dev/null 2>&1

    # 設置一些配置說明 (使用 hash)
    redis-cli HSET "docai:config" \
        "embedding_ttl" "86400" \
        "query_expansion_ttl" "3600" \
        "search_results_ttl" "1800" \
        "file_metadata_ttl" "21600" > /dev/null 2>&1

    # 驗證
    if redis-cli GET "docai:init" > /dev/null 2>&1; then
        print_success "Redis 初始化標記已設置"
    fi

    # 顯示 Redis 資訊
    print_info "Redis 資料庫狀態:"
    redis-cli INFO keyspace 2>/dev/null | grep -E "^db|keys" || echo "  Database: db0 (default)"

    print_success "Redis 初始化完成"
}

# =============================================================================
# 智能合併 .env 環境變數
# =============================================================================
# 此函數會檢查現有 .env 文件，只補充缺少的變數
# =============================================================================
smart_merge_env() {
    print_header "智能合併 .env 環境變數"

    # 取得腳本所在目錄的上層目錄（專案根目錄）
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
    ENV_FILE="$PROJECT_ROOT/.env"

    print_info "專案目錄: $PROJECT_ROOT"
    print_info ".env 路徑: $ENV_FILE"

    # 定義需要的環境變數（key=default_value 格式）
    declare -A ENV_VARS=(
        # MongoDB Settings
        ["MONGODB_URI"]="mongodb://localhost:27017"
        ["MONGODB_DATABASE"]="docai"
        ["MONGODB_CHAT_COLLECTION"]="chat_sessions"
        ["MONGODB_MIN_POOL_SIZE"]="10"
        ["MONGODB_MAX_POOL_SIZE"]="100"
        # Redis Settings
        ["REDIS_HOST"]="localhost"
        ["REDIS_PORT"]="6379"
        ["REDIS_DB"]="0"
        ["REDIS_PASSWORD"]=""
        ["REDIS_CACHE_TTL"]="3600"
        ["REDIS_EMBEDDING_TTL"]="86400"
        ["REDIS_QUERY_EXPANSION_TTL"]="3600"
        ["REDIS_SEARCH_RESULTS_TTL"]="1800"
    )

    # 定義變數的順序（因為 bash associative array 不保證順序）
    ENV_ORDER=(
        "MONGODB_URI"
        "MONGODB_DATABASE"
        "MONGODB_CHAT_COLLECTION"
        "MONGODB_MIN_POOL_SIZE"
        "MONGODB_MAX_POOL_SIZE"
        "REDIS_HOST"
        "REDIS_PORT"
        "REDIS_DB"
        "REDIS_PASSWORD"
        "REDIS_CACHE_TTL"
        "REDIS_EMBEDDING_TTL"
        "REDIS_QUERY_EXPANSION_TTL"
        "REDIS_SEARCH_RESULTS_TTL"
    )

    # 統計
    ADDED_COUNT=0
    SKIPPED_COUNT=0
    ADDED_VARS=()
    SKIPPED_VARS=()

    # 檢查 .env 文件是否存在
    if [ ! -f "$ENV_FILE" ]; then
        print_warning ".env 文件不存在，將創建新文件"
        touch "$ENV_FILE"

        # 寫入標頭
        cat >> "$ENV_FILE" << 'HEADER'

# =============================================================================
# MongoDB Settings (Chat History) - Auto-generated by install_docai_deps.sh
# =============================================================================
HEADER
    fi

    # 檢查並補充缺少的變數
    echo ""
    print_info "檢查環境變數..."
    echo ""

    # 用於追蹤是否需要添加 MongoDB 和 Redis 的區塊標頭
    NEED_MONGO_HEADER=false
    NEED_REDIS_HEADER=false

    for key in "${ENV_ORDER[@]}"; do
        value="${ENV_VARS[$key]}"

        # 檢查變數是否已存在於 .env 文件中
        if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
            # 變數已存在，跳過
            EXISTING_VALUE=$(grep "^${key}=" "$ENV_FILE" | cut -d'=' -f2-)
            echo -e "  ${YELLOW}⏭️  ${key}${NC} (已存在: ${EXISTING_VALUE})"
            SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
            SKIPPED_VARS+=("$key")
        else
            # 變數不存在，需要添加

            # 檢查是否需要添加區塊標頭
            if [[ "$key" == MONGODB_* ]] && [ "$NEED_MONGO_HEADER" = false ]; then
                # 檢查是否已有 MongoDB 標頭
                if ! grep -q "MongoDB Settings" "$ENV_FILE" 2>/dev/null; then
                    echo "" >> "$ENV_FILE"
                    echo "# ==============================================================================" >> "$ENV_FILE"
                    echo "# MongoDB Settings (Chat History)" >> "$ENV_FILE"
                    echo "# ==============================================================================" >> "$ENV_FILE"
                fi
                NEED_MONGO_HEADER=true
            fi

            if [[ "$key" == REDIS_* ]] && [ "$NEED_REDIS_HEADER" = false ]; then
                # 檢查是否已有 Redis 標頭
                if ! grep -q "Redis Settings" "$ENV_FILE" 2>/dev/null; then
                    echo "" >> "$ENV_FILE"
                    echo "# ==============================================================================" >> "$ENV_FILE"
                    echo "# Redis Settings (Cache)" >> "$ENV_FILE"
                    echo "# ==============================================================================" >> "$ENV_FILE"
                fi
                NEED_REDIS_HEADER=true
            fi

            # 添加變數
            echo "${key}=${value}" >> "$ENV_FILE"
            echo -e "  ${GREEN}✅ ${key}${NC}=${value}"
            ADDED_COUNT=$((ADDED_COUNT + 1))
            ADDED_VARS+=("$key")
        fi
    done

    echo ""
    echo "═══════════════════════════════════════════════════════════════════"
    echo ""

    # 顯示摘要
    if [ $ADDED_COUNT -gt 0 ]; then
        print_success "已添加 $ADDED_COUNT 個環境變數到 .env"
        echo "  新增變數: ${ADDED_VARS[*]}"
    else
        print_info "所有環境變數已存在，無需添加"
    fi

    if [ $SKIPPED_COUNT -gt 0 ]; then
        print_info "跳過 $SKIPPED_COUNT 個已存在的變數"
    fi

    echo ""
    print_success ".env 智能合併完成"
}

# =============================================================================
# 生成配置摘要
# =============================================================================
generate_config_summary() {
    print_header "配置摘要"

    cat << EOF
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

=== 服務管理命令 ===
  MongoDB:
    sudo systemctl start mongod
    sudo systemctl stop mongod
    sudo systemctl status mongod

  Redis:
    sudo systemctl start redis-server  (Ubuntu/Debian)
    sudo systemctl start redis         (RHEL/CentOS)
    sudo systemctl stop redis-server
    sudo systemctl status redis-server

=== 連接測試命令 ===
  MongoDB: mongosh --eval "db.runCommand({ ping: 1 })"
  Redis:   redis-cli ping

EOF
}

# =============================================================================
# 主函數
# =============================================================================
main() {
    print_header "DocAI 依賴安裝腳本"

    echo "此腳本將安裝:"
    echo "  • MongoDB 7.0 (Community Edition)"
    echo "  • Redis Server 7.x"
    echo "  • 初始化 DocAI 所需的資料結構"
    echo ""

    # 檢查 root 權限
    check_root

    # 檢測發行版
    detect_distro

    case "$DISTRO" in
        ubuntu|debian)
            install_mongodb_ubuntu_debian
            install_redis_ubuntu_debian
            ;;
        rhel|centos|rocky|almalinux|fedora)
            install_mongodb_rhel
            install_redis_rhel
            ;;
        *)
            print_error "不支援的 Linux 發行版: $DISTRO"
            print_info "請手動安裝 MongoDB 和 Redis"
            exit 1
            ;;
    esac

    # 驗證安裝
    verify_mongodb
    verify_redis

    # 初始化資料結構
    init_mongodb_schema
    init_redis_schema

    # 智能合併 .env 環境變數
    smart_merge_env

    # 生成配置摘要
    generate_config_summary

    print_header "安裝完成 🎉"
    echo "DocAI 的 MongoDB 和 Redis 依賴已成功安裝並初始化！"
    echo ""
    echo "下一步:"
    echo "  1. 檢查 .env 文件確認配置正確"
    echo "  2. 啟動 DocAI: ./start_system.sh"
    echo ""
}

# 執行主函數
main "$@"
