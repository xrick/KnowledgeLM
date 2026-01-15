# 修改日記: Windows 環境初始化腳本

**日期時間**: 2026-01-14 18:30
**修改者**: Claude (SuperClaude Framework)
**風險等級**: 🟢 低

## 修改摘要
新增 Python 跨平台初始化腳本，用於在 Windows 環境下建立 DocAI 所需的所有資料儲存結構。

## 修改檔案
| 檔案 | 變更類型 | 說明 |
|------|----------|------|
| `scripts/init_docai_windows.py` | 新增 | Python 主初始化腳本（679 行），包含 SQLite、FAISS、MongoDB、Redis 四個模組 |
| `claudedocs/manual/windows_setup_guide.md` | 新增 | Windows 環境設置操作手冊 |

## 功能說明

### init_docai_windows.py 結構

```
├── Colors 類別 - Windows 相容終端顏色輸出
├── SQLiteInitializer 類別
│   ├── SCHEMA_SQL - 完整 6 表格 + 13 索引定義
│   ├── initialize() - 主初始化流程
│   ├── _backup_and_remove() - 備份舊資料庫
│   ├── _verify_database() - 完整性驗證
│   └── _show_summary() - 顯示建立摘要
├── FAISSInitializer 類別
│   ├── initialize() - 建立目錄結構
│   ├── _create_readme() - 建立說明文件
│   └── _show_structure() - 顯示目錄結構
├── MongoDBInitializer 類別
│   ├── initialize() - 主初始化流程
│   ├── _create_chat_sessions_collection() - 建立集合 + Schema Validation
│   ├── _create_indexes() - 建立 6 個索引
│   └── _verify_and_show_stats() - 驗證並顯示統計
├── RedisInitializer 類別
│   ├── initialize() - 主初始化流程
│   ├── _set_init_config() - 設置初始配置
│   └── _show_key_patterns() - 顯示 Key 模式說明
└── main() - 命令列入口點
```

### 命令列參數

| 參數 | 說明 |
|------|------|
| `--all` | 初始化所有組件（預設） |
| `--sqlite` | 只初始化 SQLite |
| `--faiss` | 只初始化 FAISS 目錄 |
| `--mongodb` | 只初始化 MongoDB |
| `--redis` | 只初始化 Redis |
| `--force` | 強制重建 |
| `--verbose` | 詳細輸出 |
| `--data-dir` | 自訂資料目錄 |
| `--mongodb-uri` | 自訂 MongoDB URI |
| `--redis-host/port` | 自訂 Redis 連線 |

## 影響分析
- 影響範圍: 新功能，不影響現有系統
- 向後相容: 是
- 需要測試: 
  1. 在 Windows 環境執行 `python scripts/init_docai_windows.py`
  2. 驗證 SQLite 資料庫建立正確
  3. 驗證 MongoDB/Redis 連線和初始化

## 回滾方案
刪除新增的兩個檔案即可：
```bash
rm scripts/init_docai_windows.py
rm claudedocs/manual/windows_setup_guide.md
```

## 驗證結果
- [x] 語法檢查通過
- [ ] Windows 環境實測（待用戶測試）
- [ ] MongoDB 連線測試（待用戶測試）
- [ ] Redis 連線測試（待用戶測試）

## 備註
- 腳本使用標準 Python 3.9+ 語法，無需額外依賴
- MongoDB 和 Redis 初始化需要對應服務已啟動
- 若服務未啟動，會顯示明確錯誤訊息並跳過該組件
