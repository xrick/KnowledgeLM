# Rebuild Skill "undefined" Issue - Diagnosis & Fix

**Date**: 2025-12-01
**Issue**: Rebuild skill functionality showing "undefined" instead of skill name
**Status**: ✅ Fixed
**Severity**: High (功能性錯誤)

---

## Problem Statement

When clicking the "Rebuild" button for a skill in the Skill Configuration page:

1. **Confirmation dialog** displays: `Rebuild skill "undefined"?`
2. **Start notification** displays: `Rebuild started for skill: undefined`
3. **Rebuild logs** show: `No logs available` (無法追蹤進度)

### Evidence (Screenshots)

- `refData/errors/images/rebuild_skill_undefine.png` - 確認對話框顯示 "undefined"
- `refData/errors/images/rebuild_skill_undefine_2.png` - 開始通知顯示 "undefined"
- `refData/errors/images/rebuild_skill_undefine_3.png` - Rebuild logs 為空

---

## Root Cause Analysis

### Data Structure Mismatch

**Config File Structure** (`scripts/skill_data/skill_config.json`):
```json
{
  "skills": [
    {
      "skill_name": "大語言模型大全",  // ✅ Has skill_name
      "description": "...",
      "category": "Technology",
      "sources": [...]
      // ❌ No skill_id field
    }
  ]
}
```

**Frontend Code Issue** (`template/skill_config.html`):

1. **Line 1139 - Rebuild Button**:
   ```javascript
   <button onclick="rebuildSkill('${skill.skill_id}')">
   ```
   - Problem: `skill.skill_id` is `undefined` (field doesn't exist)
   - Should be: `skill.skill_name` or `safeSkillName`

2. **Line 1517 - API Request**:
   ```javascript
   body: JSON.stringify({
       skill_id: skillId,  // ❌ Wrong field name
       ...
   })
   ```
   - Problem: Backend expects `skill_name`, not `skill_id`

### Backend API Contract

**API Endpoint**: `/api/v1/skills/rebuild` (POST)

**Request Model** (`app/api/v1/endpoints/skills.py` Line 110-115):
```python
class RebuildRequest(BaseModel):
    skill_name: Optional[str] = Field(None, description="Optional: only rebuild this skill")
    clean_first: bool = Field(True, ...)
    use_smart_strategy: bool = Field(True, ...)
    force_all: bool = Field(False, ...)
```

**Conclusion**: Backend accepts `skill_name`, NOT `skill_id`!

---

## Solution Implementation

### Changes Made

**File**: `template/skill_config.html`

#### 1. Fix Rebuild Button Parameter (Line 1139)

**Before**:
```javascript
<button onclick="rebuildSkill('${skill.skill_id}')">
    <i class="fa-solid fa-rotate"></i> Rebuild
</button>
```

**After**:
```javascript
<button onclick="rebuildSkill('${safeSkillName}')">
    <i class="fa-solid fa-rotate"></i> Rebuild
</button>
```

**Reasoning**:
- `safeSkillName` is already defined in Line 1118: `skill.skill_name.replace(/'/g, "\\'")`
- Properly escaped for JavaScript string injection

#### 2. Fix `rebuildSkill()` Function (Line 1509-1535)

**Before**:
```javascript
async function rebuildSkill(skillId) {
    if (!confirm(`Rebuild skill "${skillId}"?...`)) return;

    const response = await fetch('/api/v1/skills/rebuild', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            skill_id: skillId,  // ❌ Wrong field name
            clean_first: true,
            use_smart_strategy: false,
            force_all: false
        })
    });

    alert(`✅ Rebuild started for skill: ${skillId}...`);
}
```

**After**:
```javascript
async function rebuildSkill(skillName) {
    if (!confirm(`Rebuild skill "${skillName}"?...`)) return;

    const response = await fetch('/api/v1/skills/rebuild', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            skill_name: skillName,  // ✅ Correct field name
            clean_first: true,
            use_smart_strategy: false,
            force_all: false
        })
    });

    alert(`✅ Rebuild started for skill: ${skillName}...`);
}
```

**Changes**:
1. Parameter renamed: `skillId` → `skillName` (更語義化)
2. Request body field: `skill_id` → `skill_name` (符合後端 API 契約)
3. Dialog and alert messages now correctly display skill name

---

## Expected Results After Fix

### User Flow

1. **User clicks "Rebuild" button** for "大語言模型大全"
2. **Confirmation dialog** shows:
   ```
   Rebuild skill "大語言模型大全"?

   This will regenerate the vector index for this skill.
   ```
3. **User confirms** → Click "確定"
4. **Success notification** shows:
   ```
   ✅ Rebuild started for skill: 大語言模型大全

   Check logs for progress.
   ```
5. **Rebuild Logs modal** opens automatically with real-time progress

### Technical Validation

- ✅ Frontend passes correct `skill_name` to backend
- ✅ Backend receives valid skill name and starts rebuild process
- ✅ Rebuild logs capture progress correctly
- ✅ User sees skill name (not "undefined") in all messages

---

## Testing Checklist

- [ ] Test: Click Rebuild button → Confirm dialog shows correct skill name
- [ ] Test: Confirm rebuild → Success notification shows correct skill name
- [ ] Test: Check rebuild logs → Logs show rebuild progress (not "No logs available")
- [ ] Test: Backend processes rebuild correctly for specified skill
- [ ] Test: Multiple skills → Each rebuild operates on correct skill only
- [ ] Test: Edge case - Skill name with special characters (e.g., apostrophes)

---

## Related Files

- **Frontend**: [template/skill_config.html](../template/skill_config.html) (Line 1139, 1509-1535)
- **Backend API**: [app/api/v1/endpoints/skills.py](../app/api/v1/endpoints/skills.py) (Line 110-115, 1303-1400)
- **Config**: [scripts/skill_data/skill_config.json](../scripts/skill_data/skill_config.json)
- **Error Images**:
  - [refData/errors/images/rebuild_skill_undefine.png](../refData/errors/images/rebuild_skill_undefine.png)
  - [refData/errors/images/rebuild_skill_undefine_2.png](../refData/errors/images/rebuild_skill_undefine_2.png)
  - [refData/errors/images/rebuild_skill_undefine_3.png](../refData/errors/images/rebuild_skill_undefine_3.png)

---

## Lessons Learned

### 1. Data Contract Consistency

**Problem**: Frontend used `skill_id` while backend expected `skill_name`

**Prevention**:
- Always verify backend API contracts before frontend implementation
- Use TypeScript interfaces or JSON Schema for type safety
- Document data models clearly in API documentation

### 2. Variable Naming Clarity

**Problem**: Parameter named `skillId` but actually contained skill name

**Best Practice**:
- Use descriptive variable names matching actual data type
- `skillName` vs `skillId` vs `skill_id` (consistency matters)

### 3. Testing Data Structure Assumptions

**Problem**: Assumed `skill_id` field exists in config without verification

**Prevention**:
- Test with real config data early in development
- Add TypeScript or JSDoc type annotations
- Console.log data structures during development

---

**Status**: ✅ Fixed
**Verification**: Ready for testing
**Next Steps**: Test rebuild functionality with real skills
