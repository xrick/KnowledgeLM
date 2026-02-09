# 修改日記: Prompt 語言一致性指令新增

**日期時間**: 2026-01-13 (下午)
**修改者**: Claude (SuperClaude Framework)
**風險等級**: 🟢 低

## 修改摘要

在系統提示詞中新增「語言一致性」指令，確保 LLM 回答時：
1. 以使用者提問的語言回答
2. 不翻譯來源文件內容（除非使用者明確要求）
3. 正確標註英文來源文件

## 問題背景

### 使用者反映
- 使用中文查詢時，有時會得到英文回答
- 即使來源資料是中文文件，輸出仍可能是英文

### 根本原因分析
原本的系統提示詞缺少明確的語言指令：
- ❌ 沒有：「請以與使用者提問相同的語言回答」
- ❌ 沒有：「不要翻譯來源文件的內容」
- ❌ 沒有：「若來源是英文，直接引用並註明」

當 LLM 收到混合語言的 context chunks 時，可能自行判斷輸出語言。

## 修改檔案

| 檔案 | 變更類型 | 說明 |
|------|----------|------|
| `app/Services/prompt_service.py` | 修改 | 新增語言一致性指令 (中英文版) |

## 具體修改內容

### 中文版系統提示詞 (Line 46-50)

**新增內容**：
```
5. 語言一致性：
   - 以使用者提問的語言回答
   - 不要翻譯來源文件的內容，除非使用者明確要求翻譯
   - 若來源文件是中文，直接引用中文內容
   - 若來源文件是英文，直接引用英文原文並註明「（來源為英文文件）」
```

### 英文版系統提示詞 (Line 156-160)

**新增內容**：
```
5. Language consistency:
   - Respond in the same language as the user's question
   - Do NOT translate source document content unless the user explicitly requests translation
   - If source is in Chinese, quote the Chinese content directly
   - If source is in English, quote the English content directly and note "(Source: English document)"
```

## 影響分析

- **影響範圍**: 所有使用 `PromptService` 的 RAG 查詢
  - Skill-Based 系統: `/api/v1/skills/demo/query`
  - File-Based 系統: `/api/v1/chat`
- **向後相容**: 是（僅新增指令，不影響現有邏輯）
- **需要重啟**: 是（需重啟服務器載入新的 prompt）

## 預期效果

| 情境 | 修改前行為 | 修改後行為 |
|------|------------|------------|
| 中文問題 + 中文文件 | 可能輸出英文 | ✅ 輸出中文 |
| 中文問題 + 英文文件 | 可能翻譯內容 | ✅ 直接引用英文並標註 |
| 英文問題 + 中文文件 | 可能翻譯內容 | ✅ 直接引用中文 |
| 明確要求翻譯 | 不一定翻譯 | ✅ 按要求翻譯 |

## 回滾方案

如需還原，刪除以下內容：

**中文版** (Line 46-50):
```
5. 語言一致性：
   - 以使用者提問的語言回答
   - 不要翻譯來源文件的內容，除非使用者明確要求翻譯
   - 若來源文件是中文，直接引用中文內容
   - 若來源文件是英文，直接引用英文原文並註明「（來源為英文文件）」
```

**英文版** (Line 156-160):
```
5. Language consistency:
   - Respond in the same language as the user's question
   - Do NOT translate source document content unless the user explicitly requests translation
   - If source is in Chinese, quote the Chinese content directly
   - If source is in English, quote the English content directly and note "(Source: English document)"
```

## 驗證步驟

1. 重啟服務器
2. 測試案例：
   - 用中文問題查詢中文文件 → 應輸出中文
   - 用中文問題查詢英文文件 → 應引用英文原文並註明
   - 用「請翻譯」查詢英文文件 → 應翻譯成中文

## 驗證結果

- [x] 修改語法正確
- [x] 中英文版本一致
- [ ] 功能測試通過（需重啟後驗證）

## 相關文件

- 問題分析報告: 本次 session 的 brainstorm 分析
- 系統架構: `CLAUDE.md` 中的 Prompt Service 說明
