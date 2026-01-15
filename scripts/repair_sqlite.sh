#!/bin/bash
# =============================================================================
# DocAI SQLite Database Repair Script
# =============================================================================
# 此腳本用於自動修復損壞的 SQLite 資料庫
#
# 支援的資料庫:
#   - data/skill_metadata.db (Skill 系統)
#   - data/docai.db (File 系統)
#
# 使用方式:
#   chmod +x repair_sqlite.sh
#   ./repair_sqlite.sh                    # 修復所有資料庫
#   ./repair_sqlite.sh skill_metadata.db  # 只修復指定資料庫
#
# 作者: SuperClaude Framework
# 日期: 2026-01-14
# =============================================================================

set -e

# =============================================================================
# 顏色定義
# =============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# =============================================================================
# 輔助函數
# =============================================================================
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
# 配置
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DATA_DIR="$PROJECT_ROOT/data"
BACKUP_DIR="$DATA_DIR/backups/$(date +%Y%m%d_%H%M%S)"

# 要檢查的資料庫列表
DATABASES=(
    "skill_metadata.db"
    "docai.db"
)

# =============================================================================
# 檢查 sqlite3 是否安裝
# =============================================================================
check_sqlite() {
    if ! command -v sqlite3 &> /dev/null; then
        print_error "sqlite3 未安裝"
        echo ""
        echo "請先安裝 sqlite3:"
        echo "  Ubuntu/Debian: sudo apt-get install sqlite3"
        echo "  CentOS/RHEL:   sudo yum install sqlite"
        echo "  macOS:         brew install sqlite3"
        echo "  Windows:       下載 https://sqlite.org/download.html"
        exit 1
    fi
    print_success "sqlite3 已安裝: $(sqlite3 --version)"
}

# =============================================================================
# 檢查資料庫完整性
# =============================================================================
check_integrity() {
    local db_path="$1"
    local db_name=$(basename "$db_path")

    print_info "檢查資料庫完整性: $db_name"

    if [ ! -f "$db_path" ]; then
        print_warning "資料庫不存在: $db_path"
        return 2  # 不存在
    fi

    # 執行完整性檢查
    local result=$(sqlite3 "$db_path" "PRAGMA integrity_check;" 2>&1)

    if [ "$result" = "ok" ]; then
        print_success "$db_name 完整性檢查通過"
        return 0  # 正常
    else
        print_error "$db_name 完整性檢查失敗: $result"
        return 1  # 損壞
    fi
}

# =============================================================================
# 備份資料庫
# =============================================================================
backup_database() {
    local db_path="$1"
    local db_name=$(basename "$db_path")

    # 創建備份目錄
    mkdir -p "$BACKUP_DIR"

    local backup_path="$BACKUP_DIR/${db_name}.corrupted"

    print_info "備份損壞的資料庫到: $backup_path"
    cp "$db_path" "$backup_path"

    # 同時備份 WAL 和 SHM 文件（如果存在）
    if [ -f "${db_path}-wal" ]; then
        cp "${db_path}-wal" "$BACKUP_DIR/${db_name}-wal.corrupted"
        print_info "已備份 WAL 文件"
    fi

    if [ -f "${db_path}-shm" ]; then
        cp "${db_path}-shm" "$BACKUP_DIR/${db_name}-shm.corrupted"
        print_info "已備份 SHM 文件"
    fi

    print_success "備份完成: $BACKUP_DIR/"
}

# =============================================================================
# 修復資料庫 - 方法 1: .recover 命令
# =============================================================================
repair_with_recover() {
    local db_path="$1"
    local db_name=$(basename "$db_path")
    local recovered_path="${db_path}.recovered"

    print_info "嘗試方法 1: 使用 .recover 命令修復"

    # 使用 .recover 命令（SQLite 3.29+）
    if sqlite3 "$db_path" ".recover" 2>/dev/null | sqlite3 "$recovered_path" 2>/dev/null; then
        # 檢查修復後的資料庫
        if sqlite3 "$recovered_path" "PRAGMA integrity_check;" 2>/dev/null | grep -q "ok"; then
            print_success "方法 1 成功: 資料庫已修復"

            # 替換原檔案
            mv "$recovered_path" "$db_path"

            # 刪除舊的 WAL/SHM 文件
            rm -f "${db_path}-wal" "${db_path}-shm"

            return 0
        else
            rm -f "$recovered_path"
            print_warning "方法 1: 修復後的資料庫仍有問題"
        fi
    else
        rm -f "$recovered_path"
        print_warning "方法 1: .recover 命令失敗（可能版本不支援）"
    fi

    return 1
}

# =============================================================================
# 修復資料庫 - 方法 2: .dump + 重建
# =============================================================================
repair_with_dump() {
    local db_path="$1"
    local db_name=$(basename "$db_path")
    local dump_path="${db_path}.sql"
    local rebuilt_path="${db_path}.rebuilt"

    print_info "嘗試方法 2: 使用 .dump 命令重建"

    # 嘗試 dump 資料
    if sqlite3 "$db_path" ".dump" > "$dump_path" 2>/dev/null; then
        # 檢查 dump 文件是否有內容
        if [ -s "$dump_path" ]; then
            # 重建資料庫
            if sqlite3 "$rebuilt_path" < "$dump_path" 2>/dev/null; then
                # 檢查重建後的資料庫
                if sqlite3 "$rebuilt_path" "PRAGMA integrity_check;" 2>/dev/null | grep -q "ok"; then
                    print_success "方法 2 成功: 資料庫已重建"

                    # 替換原檔案
                    mv "$rebuilt_path" "$db_path"
                    rm -f "$dump_path"

                    # 刪除舊的 WAL/SHM 文件
                    rm -f "${db_path}-wal" "${db_path}-shm"

                    return 0
                fi
            fi
        fi
    fi

    rm -f "$dump_path" "$rebuilt_path"
    print_warning "方法 2: .dump 重建失敗"
    return 1
}

# =============================================================================
# 修復資料庫 - 方法 3: 表級別修復
# =============================================================================
repair_table_by_table() {
    local db_path="$1"
    local db_name=$(basename "$db_path")
    local rebuilt_path="${db_path}.partial"

    print_info "嘗試方法 3: 表級別修復"

    # 獲取所有表名
    local tables=$(sqlite3 "$db_path" ".tables" 2>/dev/null)

    if [ -z "$tables" ]; then
        print_warning "方法 3: 無法讀取表結構"
        return 1
    fi

    local recovered_tables=0
    local failed_tables=0

    for table in $tables; do
        print_info "  處理表: $table"

        # 獲取表結構
        local schema=$(sqlite3 "$db_path" ".schema $table" 2>/dev/null)

        if [ -n "$schema" ]; then
            # 創建表
            echo "$schema" | sqlite3 "$rebuilt_path" 2>/dev/null

            # 嘗試複製資料
            if sqlite3 "$db_path" "SELECT * FROM $table;" 2>/dev/null | \
               sqlite3 "$rebuilt_path" ".import /dev/stdin $table" 2>/dev/null; then
                print_success "    $table: 已恢復"
                recovered_tables=$((recovered_tables + 1))
            else
                print_warning "    $table: 資料恢復失敗（結構已保留）"
                failed_tables=$((failed_tables + 1))
            fi
        else
            print_error "    $table: 無法讀取結構"
            failed_tables=$((failed_tables + 1))
        fi
    done

    if [ $recovered_tables -gt 0 ]; then
        # 檢查部分修復的資料庫
        if sqlite3 "$rebuilt_path" "PRAGMA integrity_check;" 2>/dev/null | grep -q "ok"; then
            print_success "方法 3 部分成功: 恢復了 $recovered_tables 個表"
            mv "$rebuilt_path" "$db_path"
            rm -f "${db_path}-wal" "${db_path}-shm"
            return 0
        fi
    fi

    rm -f "$rebuilt_path"
    print_warning "方法 3: 表級別修復失敗"
    return 1
}

# =============================================================================
# 主修復流程
# =============================================================================
repair_database() {
    local db_path="$1"
    local db_name=$(basename "$db_path")

    print_header "修復資料庫: $db_name"

    # 檢查完整性
    check_integrity "$db_path"
    local status=$?

    if [ $status -eq 0 ]; then
        print_success "資料庫正常，無需修復"
        return 0
    elif [ $status -eq 2 ]; then
        print_warning "資料庫不存在，跳過"
        return 0
    fi

    # 備份損壞的資料庫
    backup_database "$db_path"

    # 嘗試各種修復方法
    print_info "開始修復流程..."
    echo ""

    # 方法 1: .recover
    if repair_with_recover "$db_path"; then
        return 0
    fi

    # 方法 2: .dump + 重建
    if repair_with_dump "$db_path"; then
        return 0
    fi

    # 方法 3: 表級別修復
    if repair_table_by_table "$db_path"; then
        return 0
    fi

    # 所有方法都失敗
    print_error "所有修復方法都失敗"
    echo ""
    echo "建議操作:"
    echo "  1. 從備份還原: $BACKUP_DIR/"
    echo "  2. 重新創建資料庫: ./scripts/create_skill_metadata_db.sh"
    echo "  3. 手動檢查損壞原因"
    echo ""

    return 1
}

# =============================================================================
# 主函數
# =============================================================================
main() {
    print_header "DocAI SQLite 資料庫修復工具"

    # 檢查 sqlite3
    check_sqlite
    echo ""

    # 切換到專案目錄
    cd "$PROJECT_ROOT"
    print_info "專案目錄: $PROJECT_ROOT"
    print_info "資料目錄: $DATA_DIR"
    echo ""

    # 確定要修復的資料庫
    local targets=()

    if [ $# -gt 0 ]; then
        # 用戶指定的資料庫
        for arg in "$@"; do
            if [[ "$arg" == *.db ]]; then
                targets+=("$DATA_DIR/$arg")
            else
                targets+=("$DATA_DIR/${arg}.db")
            fi
        done
    else
        # 修復所有已知資料庫
        for db in "${DATABASES[@]}"; do
            targets+=("$DATA_DIR/$db")
        done
    fi

    # 修復每個資料庫
    local success_count=0
    local fail_count=0

    for db_path in "${targets[@]}"; do
        if repair_database "$db_path"; then
            success_count=$((success_count + 1))
        else
            fail_count=$((fail_count + 1))
        fi
    done

    # 摘要
    print_header "修復摘要"
    echo "  成功: $success_count"
    echo "  失敗: $fail_count"

    if [ -d "$BACKUP_DIR" ]; then
        echo ""
        echo "  備份位置: $BACKUP_DIR/"
    fi

    echo ""

    if [ $fail_count -gt 0 ]; then
        print_warning "部分資料庫修復失敗，請查看上方建議"
        exit 1
    else
        print_success "所有資料庫修復完成！"
        exit 0
    fi
}

# 執行主函數
main "$@"
