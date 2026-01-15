#!/bin/bash

# ============================================
# DocAI RAG Application - System Shutdown Script
# ============================================
# Author: Auto-generated for DocAI Project
# Description: Graceful shutdown script with cleanup,
#              service verification, and resource management
# ============================================

set -e

# ============================================
# Color Definitions
# ============================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# ============================================
# Utility Functions
# ============================================
print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_step() {
    echo -e "${CYAN}🔷 $1${NC}"
}

print_header() {
    echo -e "\n${MAGENTA}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${MAGENTA}  $1${NC}"
    echo -e "${MAGENTA}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

# ============================================
# Environment Detection
# ============================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
PID_FILE="/tmp/docai_server.pid"
PORT=8082

# ============================================
# Shutdown Sequence
# ============================================
print_header "DocAI 系統關閉"

# ============================================
# Stop FastAPI Server
# ============================================
print_step "停止 FastAPI 服務器..."

SERVER_STOPPED=false

# Method 1: Stop via PID file
if [ -f "$PID_FILE" ]; then
    SERVER_PID=$(cat "$PID_FILE")
    print_info "從 PID 文件讀取進程 ID: $SERVER_PID"

    if ps -p $SERVER_PID > /dev/null 2>&1; then
        print_step "終止進程 $SERVER_PID..."

        # Try graceful shutdown first (SIGTERM)
        if kill $SERVER_PID 2>/dev/null; then
            print_info "已發送 SIGTERM 信號，等待進程退出..."

            # Wait up to 10 seconds for graceful shutdown
            WAIT_COUNT=0
            while [ $WAIT_COUNT -lt 10 ]; do
                if ! ps -p $SERVER_PID > /dev/null 2>&1; then
                    print_success "進程已正常退出"
                    SERVER_STOPPED=true
                    break
                fi
                sleep 1
                WAIT_COUNT=$((WAIT_COUNT + 1))
                echo -n "."
            done
            echo ""

            # Force kill if still running
            if ps -p $SERVER_PID > /dev/null 2>&1; then
                print_warning "進程未響應，強制終止..."
                kill -9 $SERVER_PID 2>/dev/null
                sleep 1
                if ! ps -p $SERVER_PID > /dev/null 2>&1; then
                    print_success "進程已強制終止"
                    SERVER_STOPPED=true
                fi
            fi
        else
            print_warning "無法終止進程 (可能已退出)"
        fi
    else
        print_info "PID 文件中的進程不存在 (可能已停止)"
    fi

    # Clean up PID file
    rm -f "$PID_FILE"
    print_info "已清理 PID 文件"
else
    print_info "PID 文件不存在"
fi

# Method 2: Stop via port check (fallback)
if [ "$SERVER_STOPPED" = false ]; then
    print_step "檢查端口 $PORT 上的進程..."

    if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
        PORT_PIDS=$(lsof -Pi :$PORT -sTCP:LISTEN -t)
        print_warning "發現端口 $PORT 上的進程: $PORT_PIDS"

        for pid in $PORT_PIDS; do
            print_step "終止進程 $pid..."
            if kill $pid 2>/dev/null; then
                sleep 2
                if ! ps -p $pid > /dev/null 2>&1; then
                    print_success "進程 $pid 已終止"
                else
                    print_warning "強制終止進程 $pid..."
                    kill -9 $pid 2>/dev/null
                fi
            fi
        done
        SERVER_STOPPED=true
    else
        print_info "端口 $PORT 上無活動進程"
    fi
fi

if [ "$SERVER_STOPPED" = true ]; then
    print_success "FastAPI 服務器已停止"
else
    print_info "未發現運行中的 DocAI 服務器"
fi

# ============================================
# Cleanup Background Processes
# ============================================
print_header "清理後台進程"

print_step "搜索 DocAI 相關進程..."

# Find Python processes related to DocAI
DOCAI_PROCESSES=$(ps aux | grep -E "(main\.py|docaienv)" | grep -v grep | awk '{print $2}' || true)

if [ -n "$DOCAI_PROCESSES" ]; then
    print_warning "發現 DocAI 相關進程:"
    ps aux | grep -E "(main\.py|docaienv)" | grep -v grep || true
    echo ""

    echo -n "是否終止這些進程? (y/n): "
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        for pid in $DOCAI_PROCESSES; do
            if ps -p $pid > /dev/null 2>&1; then
                print_step "終止進程 $pid..."
                kill $pid 2>/dev/null || kill -9 $pid 2>/dev/null
            fi
        done
        sleep 1
        print_success "相關進程已清理"
    else
        print_info "保留後台進程"
    fi
else
    print_success "無殘留後台進程"
fi

# ============================================
# Optional: Stop MongoDB/Redis
# ============================================
print_header "數據庫服務管理"

echo -n "是否停止 MongoDB 服務? (y/n): "
read -r response
if [[ "$response" =~ ^[Yy]$ ]]; then
    print_step "停止 MongoDB..."
    if sudo systemctl stop mongod 2>/dev/null; then
        print_success "MongoDB 已停止"
    else
        print_warning "無法停止 MongoDB (可能未運行或無權限)"
    fi
else
    print_info "保持 MongoDB 運行"
fi

echo -n "是否停止 Redis 服務? (y/n): "
read -r response
if [[ "$response" =~ ^[Yy]$ ]]; then
    print_step "停止 Redis..."
    if sudo systemctl stop redis-server 2>/dev/null || sudo systemctl stop redis 2>/dev/null; then
        print_success "Redis 已停止"
    else
        print_warning "無法停止 Redis (可能未運行或無權限)"
    fi
else
    print_info "保持 Redis 運行"
fi

# ============================================
# Port Verification
# ============================================
print_header "端口驗證"

print_step "驗證端口 $PORT 已釋放..."
sleep 2

if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    PORT_PID=$(lsof -Pi :$PORT -sTCP:LISTEN -t)
    PROCESS_NAME=$(ps -p $PORT_PID -o comm= 2>/dev/null || echo "unknown")
    print_warning "端口 $PORT 仍被佔用 (PID: $PORT_PID, Process: $PROCESS_NAME)"
    print_info "您可能需要手動檢查: lsof -i :$PORT"
else
    print_success "端口 $PORT 已釋放"
fi

# ============================================
# Cleanup Temporary Files
# ============================================
print_header "清理臨時文件"

print_step "清理 Python 快取文件..."

# Clean up __pycache__ directories
PYCACHE_COUNT=$(find "$PROJECT_ROOT" -type d -name "__pycache__" 2>/dev/null | wc -l)
if [ "$PYCACHE_COUNT" -gt 0 ]; then
    find "$PROJECT_ROOT" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    print_success "已清理 $PYCACHE_COUNT 個 __pycache__ 目錄"
else
    print_info "無 __pycache__ 目錄需要清理"
fi

# Clean up .pyc files
PYC_COUNT=$(find "$PROJECT_ROOT" -type f -name "*.pyc" 2>/dev/null | wc -l)
if [ "$PYC_COUNT" -gt 0 ]; then
    find "$PROJECT_ROOT" -type f -name "*.pyc" -delete 2>/dev/null || true
    print_success "已清理 $PYC_COUNT 個 .pyc 文件"
else
    print_info "無 .pyc 文件需要清理"
fi

# Clean up .pyo files
PYO_COUNT=$(find "$PROJECT_ROOT" -type f -name "*.pyo" 2>/dev/null | wc -l)
if [ "$PYO_COUNT" -gt 0 ]; then
    find "$PROJECT_ROOT" -type f -name "*.pyo" -delete 2>/dev/null || true
    print_success "已清理 $PYO_COUNT 個 .pyo 文件"
else
    print_info "無 .pyo 文件需要清理"
fi

# Clean up .pytest_cache directories
PYTEST_CACHE_COUNT=$(find "$PROJECT_ROOT" -type d -name ".pytest_cache" 2>/dev/null | wc -l)
if [ "$PYTEST_CACHE_COUNT" -gt 0 ]; then
    find "$PROJECT_ROOT" -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
    print_success "已清理 $PYTEST_CACHE_COUNT 個 .pytest_cache 目錄"
fi

print_success "Python 快取清理完成"

# Clean up logs (optional)
echo -n "是否清理日誌文件? (y/n): "
read -r response
if [[ "$response" =~ ^[Yy]$ ]]; then
    if [ -d "$PROJECT_ROOT/logs" ]; then
        rm -f "$PROJECT_ROOT/logs/"*.log 2>/dev/null || true
        print_success "已清理日誌文件"
    else
        print_info "無日誌目錄"
    fi
else
    print_info "保留日誌文件"
fi

# ============================================
# Final Status
# ============================================
print_header "關閉完成"

print_success "DocAI 系統已成功關閉"
echo ""
print_info "系統狀態:"

# Check MongoDB
if systemctl is-active --quiet mongod; then
    echo -e "  ${GREEN}• MongoDB: 運行中${NC}"
else
    echo -e "  ${YELLOW}• MongoDB: 已停止${NC}"
fi

# Check Redis
if systemctl is-active --quiet redis-server || systemctl is-active --quiet redis; then
    echo -e "  ${GREEN}• Redis: 運行中${NC}"
else
    echo -e "  ${YELLOW}• Redis: 已停止${NC}"
fi

# Check DocAI Server
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "  ${RED}• DocAI Server: 仍在運行 (端口 $PORT 佔用)${NC}"
else
    echo -e "  ${GREEN}• DocAI Server: 已停止${NC}"
fi

echo ""
print_info "重新啟動: ./start_system.sh"
echo ""
