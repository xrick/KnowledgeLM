# DocAI 系統開發 TODO 管理中心

**建立日期**: 2026-01-14  
**維護者**: Development Team  
**版本**: 1.0

---

## 📋 目錄結構

```
claudedocs/dev_todo/
├── README.md                    # 本文件 - 管理中心說明
├── TODO_INDEX.md                # 所有 TODO 項目索引
├── TEMPLATE_TODO_ITEM.md        # TODO 項目模板
├── active/                      # 進行中的 TODO
│   └── {項目編號}_{簡短名稱}/
├── completed/                   # 已完成的 TODO
│   └── {項目編號}_{簡短名稱}/
├── on_hold/                     # 暫緩的 TODO
│   └── {項目編號}_{簡短名稱}/
└── cancelled/                   # 已取消的 TODO
    └── {項目編號}_{簡短名稱}/
```

---

## 🏷️ TODO 項目編號規則

**格式**: `TODO-{類別}-{年月}-{序號}`

**類別代碼**:
| 代碼 | 類別 | 說明 |
|------|------|------|
| FE | Frontend | 前端相關 |
| BE | Backend | 後端相關 |
| DB | Database | 資料庫相關 |
| UI | UI/UX | 介面設計 |
| API | API | API 設計與開發 |
| SEC | Security | 安全性相關 |
| PERF | Performance | 效能優化 |
| INFRA | Infrastructure | 基礎設施 |
| DOC | Documentation | 文件相關 |
| BUG | Bug Fix | 錯誤修復 |
| FEAT | Feature | 新功能 |
| REFAC | Refactoring | 重構 |

**範例**:
- `TODO-FEAT-2601-001` - 2026年1月第1個功能開發項目
- `TODO-BUG-2601-003` - 2026年1月第3個錯誤修復項目

---

## 📊 優先級定義

| 等級 | 標記 | 說明 | 處理時限 |
|------|------|------|----------|
| P0 | 🔴 | 緊急/阻塞性問題 | 24小時內 |
| P1 | 🟠 | 高優先級 | 1週內 |
| P2 | 🟡 | 中優先級 | 2週內 |
| P3 | 🟢 | 低優先級 | 下個迭代 |
| P4 | ⚪ | 待定/未來考慮 | 無期限 |

---

## 📝 狀態定義

| 狀態 | 標記 | 說明 |
|------|------|------|
| 🆕 NEW | 新建立 | 剛建立，尚未開始 |
| 📋 PLANNING | 規劃中 | 正在進行需求分析與設計 |
| 🔄 IN_PROGRESS | 進行中 | 正在開發實作 |
| 👀 IN_REVIEW | 審查中 | 等待代碼審查或測試 |
| ✅ COMPLETED | 已完成 | 已完成並驗證 |
| ⏸️ ON_HOLD | 暫緩 | 因故暫停 |
| ❌ CANCELLED | 已取消 | 不再執行 |

---

## 🔗 相關文件資料夾對照

| TODO 主題 | 詳細文件位置 |
|-----------|-------------|
| Chat Session Management | `claudedocs/chat_session_management_subsystem/` |
| Skill Architecture | `claudedocs/skill_architecture/` |
| OPMP Integration | `claudedocs/opmp_integration/` |
| Performance Optimization | `claudedocs/performance/` |
| Security Audit | `claudedocs/security/` |

---

## 📖 使用指南

### 建立新 TODO

1. 複製 `TEMPLATE_TODO_ITEM.md` 到 `active/` 目錄
2. 依照編號規則命名資料夾
3. 填寫模板中的各項資訊
4. 更新 `TODO_INDEX.md` 索引

### 更新 TODO 狀態

1. 在項目文件中更新狀態與日期
2. 如需移動資料夾（如完成後移至 completed/）
3. 更新 `TODO_INDEX.md` 索引

### 討論記錄

- 每次重要討論都應記錄在項目的 `discussion_history.md`
- 格式：`[日期] 參與者 - 討論摘要`

---

## 📞 聯絡資訊

如有問題，請聯繫開發團隊或在相關 TODO 項目中留言。

---

*DocAI Development Team*
