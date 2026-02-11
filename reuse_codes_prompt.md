<!-- reuse_codes_prompt.md -->

📋 STEP 1: READ REQUIREMENTS
Claude, read the rules in u/CLAUDE.md, then use sequential thinking and proceed to the next step.
STOP. Before reading further, confirm you understand:

1. This is a code reuse and consolidation project
2. Creating new files requires exhaustive justification
3. Every suggestion must reference existing code
4. Violations of these rules make your response invalid

CONTEXT: Previous developer was terminated for ignoring existing code and creating duplicates. You must prove you can work within existing architecture.

MANDATORY PROCESS:

1. Start with "COMPLIANCE CONFIRMED: I will prioritize reuse over creation"
2. Analyze existing code BEFORE suggesting anything new
3. Reference specific files from the provided analysis
4. Include validation checkpoints throughout your response
5. End with compliance confirmation

RULES (violating ANY invalidates your response):
❌ No new files without exhaustive reuse analysis
❌ No rewrites when refactoring is possible
❌ No generic advice - provide specific implementations
❌ No ignoring existing codebase architecture
✅ Extend existing services and components
✅ Consolidate duplicate code
✅ Reference specific file paths
✅ Provide migration strategies

```
/sc:design --think-hard --focus architecture --magic --c7 --seq --serena
請嚴格遵守以下規則與任務目標執行：
【重要限制】
在未獲得我明確允許之前，不得修改任何現有程式碼。
僅能在我指定的範圍內進行調整或新增功能。
【主要任務目標】
**使用者介面改版**: 請看以下二個圖片：
- 新增檔案新介面：refData/design/add_multifiles_modified.png
- 批次處理新介面：refData/design/processing_multiple_files_UI.jpg
請修改系統，使其符合以下功能需求：
支援使用者「同時選擇多個檔案或多個目錄」。
支援「批次上傳與批次處理」功能，包含：
系統需處理所有被選取的檔案。
若選擇的是目錄，需自動處理該目錄內所有檔案。
所有被選取或被處理的檔案，皆必須符合系統規定的檔案格式。
若檔案格式不符合規定，系統應略過或提示錯誤（不得強制處理）。
請確保最終設計符合上述所有限制與條件。
   
```
  
FINAL REMINDER: If you suggest creating new files, explain why existing files cannot be extended. If you recommend rewrites, justify why refactoring won't work.
🔍 STEP 2: ANALYZE CURRENT SYSTEM
Analyze the existing codebase and identify relevant files for the requested feature implementation.
Then proceed to Step 3.
🎯 STEP 3: CREATE IMPLEMENTATION PLAN
Based on your analysis from Step 2, create a detailed implementation plan for the requested feature.
Then proceed to Step 4.
🔧 STEP 4: PROVIDE TECHNICAL DETAILS
Create the technical implementation details including code changes, API modifications, and integration points.
Then proceed to Step 5.
✅ STEP 5: FINALIZE DELIVERABLES
Complete the implementation plan with testing strategies, deployment considerations, and final recommendations.
🎯 INSTRUCTIONS
Follow each step sequentially. Complete one step before moving to the next. Use the findings from each previous step to inform the next step. The other instruction is always chat with me in traditional chinese
except technology, computer science, AI, Machine Learning...etc terms
