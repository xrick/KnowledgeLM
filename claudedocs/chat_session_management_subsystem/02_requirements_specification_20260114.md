# Chat Session Management - 需求規格書

**文件日期**: 2026-01-14  
**版本**: 1.0  
**狀態**: 初版完成

---

## 1. 概述

本文件定義「用戶對話管理子系統」的完整需求規格，包含當前已實現功能、待開發功能，以及未來擴展規劃。

---

## 2. 核心概念模型

### 2.1 實體關係圖

```
┌─────────────────────────────────────────────────────────────────┐
│                        User (用戶)                               │
│  user_id: uuid                                                  │
│  user_name: string                                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 1:N
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ChatSession (對話)                            │
│  session_id: skill_{user_id}_{skill_id}_{timestamp?}            │
│  user_id: uuid                                                  │
│  skill_id: string                                               │
│  session_name: string (可選)                                    │
│  is_active: boolean                                             │
│  created_at: datetime                                           │
│  updated_at: datetime                                           │
│  expires_at: datetime (可選)                                    │
│  archived_at: datetime (可選)                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 1:N
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Message (訊息)                                │
│  role: user | assistant                                         │
│  content: string                                                │
│  timestamp: datetime                                            │
│  metadata: { citations, sources_count, etc. }                   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Session ID 格式演進

| 階段 | 格式 | 說明 |
|------|------|------|
| **Phase 1**（當前） | `skill_{user_id}_{skill_id}` | 每用戶每 Skill 一個對話 |
| **Phase 2**（新對話功能） | `skill_{user_id}_{skill_id}_{uuid8}` | 支援多對話 |
| **Phase 3**（企業版） | `skill_{org_id}_{user_id}_{skill_id}_{uuid8}` | 支援組織級別 |

---

## 3. 需求清單

### 3.1 Phase 1 - 基礎功能（當前已實現）

| 編號 | 需求 | 狀態 | 說明 |
|------|------|------|------|
| R1.1 | 用戶識別 | ✅ 已實現 | 使用 user_id (UUID) 識別用戶 |
| R1.2 | Skill 獨立對話 | ✅ 已實現 | 每個 Skill 有獨立的對話歷史 |
| R1.3 | 對話持久化 | ✅ 已實現 | MongoDB 儲存對話歷史 |
| R1.4 | 清除單一對話 | ✅ 已實現 | DELETE /api/v1/skills/sessions/{session_id} |
| R1.5 | 清除所有對話 | ✅ 已實現 | DELETE /api/v1/skills/sessions/clear-all |
| R1.6 | 對話歷史載入 | ✅ 已實現 | 自動載入最近 N 筆對話 |
| R1.7 | 用戶隔離 | ✅ 已實現 | 不同用戶的對話完全隔離 |

### 3.2 Phase 2 - 進階功能（待開發）

| 編號 | 需求 | 優先級 | 說明 |
|------|------|--------|------|
| R2.1 | 建立新對話 | P0 | 同一 Skill 可創建多個獨立對話 |
| R2.2 | 對話列表 | P0 | 顯示用戶在該 Skill 的所有對話 |
| R2.3 | 切換對話 | P0 | 在同一 Skill 的不同對話間切換 |
| R2.4 | 對話重命名 | P1 | 用戶可自訂對話名稱 |
| R2.5 | 刪除特定對話 | P1 | 刪除指定對話（非清除全部） |
| R2.6 | 預設對話 | P1 | 標記一個對話為該 Skill 的預設 |
| R2.7 | 對話搜尋 | P2 | 搜尋歷史對話內容 |
| R2.8 | 對話摘要 | P2 | 自動生成對話摘要標題 |

### 3.3 Phase 3 - 企業功能（未來規劃）

| 編號 | 需求 | 說明 |
|------|------|------|
| R3.1 | 對話分享 | 將對話分享給其他用戶 |
| R3.2 | 對話匯出 | 匯出為 PDF/Markdown |
| R3.3 | 對話歸檔 | 自動歸檔舊對話 |
| R3.4 | 使用統計 | 統計用戶使用行為 |
| R3.5 | 對話模板 | 預設對話開場白 |
| R3.6 | 組織級管理 | 組織管理員可管理所有對話 |
| R3.7 | 合規審計 | 對話記錄審計功能 |

---

## 4. 資料模型

### 4.1 當前 Schema（Phase 1）

```javascript
// MongoDB Collection: chat_sessions
{
  session_id: "skill_{user_id}_{skill_id}",
  user_id: "uuid-xxx",
  file_ids: ["skill_id"],
  created_at: ISODate,
  updated_at: ISODate,
  messages: [
    {
      role: "user" | "assistant",
      content: "string",
      timestamp: ISODate,
      metadata: { skill_id, type, citations, sources_count }
    }
  ],
  metadata: {
    type: "skill_progressive_chat",
    skill_id: "skill_xxx",
    total_messages: Number
  }
}
```

### 4.2 建議 Schema（Phase 2）

```javascript
// MongoDB Collection: chat_sessions
{
  // 核心識別
  session_id: "skill_{user_id}_{skill_id}_{uuid8}",
  user_id: "uuid-xxx",
  skill_id: "skill_xxx",
  
  // 對話元資料
  session_name: "2026年投資規劃",     // 用戶可編輯
  session_order: 1,                    // 顯示順序
  is_default: true,                    // 是否為該 Skill 的預設對話
  is_active: true,                     // 是否活躍（軟刪除）
  
  // 時間戳記
  created_at: ISODate,
  updated_at: ISODate,
  last_message_at: ISODate,
  expires_at: ISODate | null,          // 可選：自動過期
  archived_at: ISODate | null,         // 可選：歸檔時間
  
  // 統計資訊
  message_count: 24,
  total_tokens: 15000,                 // 用於計費或限制
  
  // 訊息內容
  messages: [
    {
      message_id: "uuid",              // 新增：訊息唯一識別
      role: "user" | "assistant",
      content: "string",
      timestamp: ISODate,
      metadata: {
        skill_id: "string",
        type: "string",
        citations: ["string"],
        sources_count: Number,
        tokens_used: Number            // 新增：該訊息使用的 tokens
      }
    }
  ],
  
  // 擴展元資料
  metadata: {
    type: "skill_chat",
    source: "web" | "mobile" | "api",  // 來源
    client_version: "1.0.0",
    first_query: "string",             // 新增：首次查詢（用於摘要）
    tags: ["string"]                   // 新增：標籤
  }
}
```

---

## 5. API 設計

### 5.1 Phase 1 API（當前）

| Method | Endpoint | 說明 |
|--------|----------|------|
| POST | `/api/v1/skills/{skill_id}/chat/stream` | 對話串流 |
| POST | `/api/v1/skills/demo/query` | 對話查詢（非串流） |
| DELETE | `/api/v1/skills/sessions/{session_id}` | 刪除指定 session |
| DELETE | `/api/v1/skills/{skill_id}/sessions` | 刪除 skill 的所有 session |
| DELETE | `/api/v1/skills/sessions/clear-all` | 清除所有 session |
| GET | `/api/v1/skills/sessions/list` | 列出所有 session |

### 5.2 Phase 2 API（建議新增）

| Method | Endpoint | 說明 |
|--------|----------|------|
| POST | `/api/v1/skills/{skill_id}/sessions` | 建立新對話 |
| GET | `/api/v1/skills/{skill_id}/sessions` | 列出 Skill 的所有對話 |
| GET | `/api/v1/skills/sessions/{session_id}` | 取得對話詳情 |
| PATCH | `/api/v1/skills/sessions/{session_id}` | 更新對話（重命名等） |
| POST | `/api/v1/skills/sessions/{session_id}/default` | 設為預設對話 |

---

## 6. UI 設計

### 6.1 對話列表（Phase 2）

```
┌─────────────────────────────────────────────────────────────────┐
│  📁 投資理財                                        [+ 新對話]   │
├─────────────────────────────────────────────────────────────────┤
│  💬 對話列表                                                     │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ ● 2026年投資規劃 (預設)              今天 10:20    [⋮]       ││
│  │   最近: 「請總結所有文件內容」                               ││
│  ├─────────────────────────────────────────────────────────────┤│
│  │ ○ ETF 研究筆記                        昨天 15:30    [⋮]      ││
│  │   最近: 「ETF 和股票的差異是什麼？」                         ││
│  ├─────────────────────────────────────────────────────────────┤│
│  │ ○ 風險評估討論                        3天前         [⋮]      ││
│  │   最近: 「如何計算投資組合的風險？」                         ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘

[⋮] 選單：
├── 重新命名
├── 設為預設
├── 匯出對話
└── 刪除對話
```

### 6.2 對話切換確認（建議）

當用戶切換到有歷史對話的 Skill 時：

```
┌─────────────────────────────────────────────────────────────────┐
│                     💬 發現既有對話                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  此 Skill 有 3 個既有對話：                                      │
│                                                                 │
│  • 2026年投資規劃 (今天 10:20)                                   │
│  • ETF 研究筆記 (昨天 15:30)                                     │
│  • 風險評估討論 (3天前)                                          │
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐                       │
│  │ 繼續既有對話    │  │   開始新對話    │                       │
│  └─────────────────┘  └─────────────────┘                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. Session ID 生成方案比較

### 7.1 方案 A：時間戳

```
skill_{user_id}_{skill_id}_{timestamp}
```

| 優點 | 缺點 |
|------|------|
| 簡單、直觀 | ID 較長 |
| 自然排序 | 無法處理同秒多對話 |

### 7.2 方案 B：序號

```
skill_{user_id}_{skill_id}_v{version}
```

| 優點 | 缺點 |
|------|------|
| ID 簡短 | 需查詢最大序號 |
| 清晰版本概念 | 刪除後不連續 |

### 7.3 方案 C：UUID（推薦）

```
skill_{user_id}_{skill_id}_{uuid8}
```

| 優點 | 缺點 |
|------|------|
| 保證唯一性 | 無自然排序 |
| 無需查詢 | 需依賴 created_at 排序 |
| 適合分散式 | - |

**建議採用方案 C**，原因：
1. 不需要額外查詢即可生成唯一 ID
2. 適合未來分散式架構
3. 透過 `created_at` 排序可解決排序需求

---

## 8. 實作優先級

### 8.1 短期（1-2 週）

1. ✅ 修復當前切換 Skill 的歷史污染問題
2. 📋 提供「清除對話」按鈕
3. 📋 切換 Skill 時的確認對話框

### 8.2 中期（3-4 週）

1. 📋 Phase 2 資料模型遷移
2. 📋 「建立新對話」功能
3. 📋 對話列表 UI

### 8.3 長期（1-2 月）

1. 📋 對話重命名
2. 📋 對話搜尋
3. 📋 對話匯出

---

## 9. 修正與補足說明

### 9.1 原始想法修正

| 原始想法 | 修正 |
|----------|------|
| Session ID 由前端產生 | ⚠️ 修正：實際由後端根據 `user_id + skill_id` 生成 |

### 9.2 補足項目

| 項目 | 說明 |
|------|------|
| `session_name` | 讓用戶可命名對話 |
| `is_default` | 標記預設對話 |
| `message_count` | 統計訊息數量 |
| `is_active` | 支援軟刪除 |
| `last_message_at` | 追蹤最後活動時間 |
| `expires_at` | 支援自動過期 |
| `archived_at` | 支援歸檔功能 |

---

## 10. 相關文件

- [01_problem_analysis_20260114.md](./01_problem_analysis_20260114.md) - 問題分析報告
- [03_implementation_guide_20260114.md](./03_implementation_guide_20260114.md) - 實作指南（待建立）

---

*文件結束*
