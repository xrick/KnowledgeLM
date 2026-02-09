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
/sc:troubleshoot --fix
/sc:troubleshoot --fix
立即修復（低風險、高價值）：
   - 同時修改相關的程式碼
   - 列出有哪些python檔被修改
   - 請先準備roll-back機制
   - 補齊 `skill_chunk_metadata` 的 CREATE TABLE
   - 修正 `skills.py:2752` 查錯表的問題
   - 清理 9 筆孤兒記錄
when you finish, record the problem descript
   - 統一 `head_id` 前綴（修正六法全書-民法的 `skill_` 前綴）
   
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
