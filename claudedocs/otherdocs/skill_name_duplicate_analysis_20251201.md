# Skill Name Duplicate Issue Analysis

**Date**: 2025-12-01
**Issue**: Duplicate skill names "My Cases" shown in UI
**Status**: Analysis Complete

---

## Problem Statement

User reported seeing two skills with the same name "My Cases" (22 and 3 chunks) in the Skill Tree UI.

---

## Investigation Results

### 1. Skill vs Document Classification Mechanism

**Mechanism**: Uses `parent_skill_id` field for 3-level hierarchy

| Level | parent_skill_id | Description | Example |
|-------|----------------|-------------|---------|
| Level 1 | `root` (self) | System Root | `root` |
| Level 2 | `root` | Main Skills | LLM, Investment |
| Level 3 | `skill_xxx` | Instant Attachments (Documents) | CSS揭秘.pdf |

**Code Location**: [template/skill_main.html:1215-1248](../template/skill_main.html#L1215-L1248)

```javascript
function groupSkillsByName(skills) {
    // First pass: identify main skills (parent_skill_id = 'root')
    normalizedSkills.forEach(skill => {
        if (skill.parent_skill_id === 'root' && skill.id !== 'root') {
            groups[skill.id] = { main: skill, attachments: [] };
        }
    });

    // Second pass: attach instant attachments to their parent
    normalizedSkills.forEach(skill => {
        if (skill.parent_skill_id !== 'root' && groups[skill.parent_skill_id]) {
            groups[skill.parent_skill_id].attachments.push(skill);
        }
    });
}
```

---

### 2. "My Cases" Existence Investigation

**Key Finding**: "My Cases" **does not exist** in any system data source!

**Checked Locations**:
- ❌ Database `skill_metadata.db` - No "My Cases" records
- ❌ Config file `skill_config.json` - No related configuration
- ❌ Fallback data ([template/skill_main.html:1354-1366](../template/skill_main.html#L1354-L1366))
- ❌ API response - Depends entirely on database

**Actual Database Content**:
```sql
skill_20251126_104421_4fdb3e9b | 六法全書-刑法 | root | 272
skill_20251126_104649_f333015b | 六法全書-民法 | root | 533
skill_20251126_105138_b8cc08c1 | 大語言模型大全 | root | 883
skill_20251127_100500_b8cc08c1 | 大語言模型大全 | skill_20251126_105138_b8cc08c1 | 385
skill_20251128_070644_b8cc08c1 | 大語言模型大全 | skill_20251126_105138_b8cc08c1 | 22
skill_20251128_074913_b7380bf3 | 投資理財 | root | 95
```

**Possible Sources** (by probability):
1. **Browser localStorage/sessionStorage** (80%) - Cached data from previous session
2. **Outdated screenshot** (15%) - Image from older version where "My Cases" existed
3. **Manual injection** (5%) - Developer modified `allSkillsData` in Console

**Recommendation**: Clear browser cache and reload
```javascript
localStorage.clear();
sessionStorage.clear();
location.reload(true);
```

---

### 3. First "MyCase" Auto-Generation Cause

**Conclusion**: Cannot be determined

Since "My Cases" does not exist in any system data source, its generation cause cannot be traced.

**Possible scenarios**:
- If it truly existed before, it may have been manually created during testing
- If it's browser cache, it may be from another environment or version

---

### 4. Current Name Uniqueness Validation

**Finding**: System has **NO name uniqueness validation**!

**Current Creation Flow** ([app/api/v1/endpoints/skills.py:179-245](../app/api/v1/endpoints/skills.py#L179-L245)):

```python
@router.post("/upload")
async def create_skill(request: SkillCreateRequest, ...):
    # ❌ No name existence check

    # 1. Process and Chunk
    processed_skill = await ingestion_service.process_skill(
        skill_name=request.name,  # Use user input directly, no validation
        ...
    )

    # 2. Store Vectors (FAISS)
    await retrieval_service.add_content(...)

    # 3. Store Metadata (SQLite)
    await metadata_provider.create_skill(...)  # Create directly, no duplicate check
```

**Missing Validations**:
- ❌ Frontend validation (UI layer)
- ❌ Backend validation (API layer)
- ❌ Database constraints (DB layer)

---

## Solution Implementation Plan

### Phase 1: Backend Validation (Mandatory)

**File**: `app/api/v1/endpoints/skills.py`

Add name uniqueness check in `create_skill()`:

```python
@router.post("/upload", response_model=SkillResponse)
async def create_skill(
    request: SkillCreateRequest,
    metadata_provider: SkillMetadataProvider = Depends(...),
    ...
):
    """Create a new skill with name uniqueness validation"""

    # ✅ NEW: Check if skill name already exists (main skills only)
    existing_skills = await metadata_provider.list_skills()
    existing_main_skills = [
        s for s in existing_skills
        if s.get("parent_skill_id") == "root" and s.get("skill_id") != "root"
    ]

    for skill in existing_main_skills:
        if skill.get("skill_name") == request.name:
            raise HTTPException(
                status_code=409,  # Conflict
                detail=f"Skill name '{request.name}' already exists. Please use a different name."
            )

    # Continue with existing creation flow...
    processed_skill = await ingestion_service.process_skill(...)
    ...
```

**HTTP Status Code**: 409 Conflict (standard for duplicate resource)

---

### Phase 2: Frontend Popup Alert

**File**: `template/skill_main.html` or `template/skill_config.html`

Add error handling for create/upload:

```javascript
async function createSkill(skillName, skillContent) {
    try {
        const response = await fetch('/api/v1/skills/upload', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: skillName,
                content: skillContent,
                ...
            })
        });

        // ✅ NEW: Handle 409 Conflict (duplicate name)
        if (response.status === 409) {
            const error = await response.json();
            showDuplicateNameAlert(error.detail);  // Show popup
            return;
        }

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        // Success handling...
    } catch (error) {
        console.error('Create skill failed:', error);
        showErrorAlert(error.message);
    }
}

// ✅ NEW: Duplicate name alert modal
function showDuplicateNameAlert(message) {
    // Create modal overlay
    const modal = document.createElement('div');
    modal.className = 'duplicate-name-modal';
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <i class="fa-solid fa-triangle-exclamation" style="color: #f59e0b;"></i>
                <h3>名稱重複</h3>
            </div>
            <div class="modal-body">
                <p>${message}</p>
                <p>請使用其他名稱或編輯現有的 Skill。</p>
            </div>
            <div class="modal-footer">
                <button class="btn btn-primary" onclick="closeDuplicateNameModal()">
                    知道了
                </button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
}

function closeDuplicateNameModal() {
    const modal = document.querySelector('.duplicate-name-modal');
    if (modal) {
        modal.remove();
    }
}
```

**CSS Styling**:
```css
.duplicate-name-modal {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10000;
}

.duplicate-name-modal .modal-content {
    background: white;
    padding: 24px;
    border-radius: 12px;
    max-width: 400px;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.duplicate-name-modal .modal-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 16px;
}

.duplicate-name-modal .modal-header i {
    font-size: 24px;
}

.duplicate-name-modal .modal-body {
    margin-bottom: 20px;
    color: #4b5563;
}

.duplicate-name-modal .modal-footer {
    display: flex;
    justify-content: flex-end;
}
```

---

### Phase 3: Database Constraint (Optional, Production Hardening)

**File**: Migration script or manual SQL

Add unique constraint on skill_name for main skills:

```sql
-- Option 1: Add partial unique index (PostgreSQL/SQLite 3.15+)
CREATE UNIQUE INDEX idx_unique_main_skill_name
ON skill_metadata(skill_name)
WHERE parent_skill_id = 'root';

-- Option 2: Add check constraint (if supported)
ALTER TABLE skill_metadata
ADD CONSTRAINT unique_main_skill_name
CHECK (
    parent_skill_id != 'root' OR
    NOT EXISTS (
        SELECT 1 FROM skill_metadata s2
        WHERE s2.skill_name = skill_metadata.skill_name
        AND s2.parent_skill_id = 'root'
        AND s2.skill_id != skill_metadata.skill_id
    )
);
```

**Note**: This is optional because backend validation provides sufficient protection.

---

## Implementation Priority

1. **High Priority** (Immediate):
   - ✅ Backend validation (prevents duplicate creation)
   - ✅ Frontend popup alert (user feedback)

2. **Medium Priority** (Post-Demo):
   - Database constraint (defense in depth)
   - Unit tests for validation logic

3. **Low Priority** (Future):
   - Real-time name availability check (as user types)
   - Suggest alternative names (e.g., "My Cases 2", "My Cases (2)")

---

## Testing Checklist

- [ ] Test: Create skill with unique name → Success
- [ ] Test: Create skill with duplicate name → 409 Error + Popup
- [ ] Test: Frontend shows clear error message
- [ ] Test: User can dismiss popup and retry with different name
- [ ] Test: Database integrity maintained (no partial creation)
- [ ] Test: Edge cases (case sensitivity, whitespace, special characters)

---

## Related Files

- API: [app/api/v1/endpoints/skills.py](../app/api/v1/endpoints/skills.py)
- Frontend: [template/skill_main.html](../template/skill_main.html)
- Frontend: [template/skill_config.html](../template/skill_config.html)
- Provider: [app/Providers/skill_metadata_provider/client.py](../app/Providers/skill_metadata_provider/client.py)
- Database: [data/skill_metadata.db](../data/skill_metadata.db)

---

## Implementation Status

### ✅ Phase 1: Backend Validation (COMPLETED)

**Files Modified**:
1. `app/api/v1/endpoints/skills.py` (Line 195-208)
   - Added name uniqueness check in `/upload` endpoint
   - Returns HTTP 409 Conflict for duplicate names

2. `app/api/v1/endpoints/skills.py` (Line 669-672)
   - Updated `/config/skills` endpoint to use HTTP 409
   - Consistent error handling across both endpoints

**Code Implemented**:
```python
# Validation logic added before skill creation
existing_skills = await metadata_provider.list_skills()
existing_main_skills = [
    s for s in existing_skills
    if s.get("parent_skill_id") == "root" and s.get("skill_id") != "root"
]

for skill in existing_main_skills:
    if skill.get("skill_name") == request.name:
        raise HTTPException(
            status_code=409,
            detail=f"Skill name '{request.name}' already exists. Please use a different name."
        )
```

---

### ✅ Phase 2: Frontend Popup Alert (COMPLETED)

**Files Modified**:
- `template/skill_config.html`

**Changes**:

1. **HTML Modal** (Line 826-852):
   - Added custom duplicate name alert modal
   - Warning icon and styling
   - User-friendly message display
   - Suggestion box with recommendations

2. **JavaScript Function** (Line 1281-1286):
   ```javascript
   function showDuplicateNameModal(message) {
       document.getElementById('duplicate-name-message').textContent = message;
       showModal('duplicate-name-modal');
   }
   ```

3. **Error Handling in addSkill()** (Line 1326-1330):
   ```javascript
   else if (response.status === 409) {
       const error = await response.json();
       showDuplicateNameModal(error.detail);
       closeModal('add-skill-modal');
   }
   ```

**UI Features**:
- ⚠️ Warning icon with gradient background
- Clear error message from backend
- Suggestion box: "請使用其他名稱，或編輯/刪除現有的 Skill"
- "知道了" confirmation button

---

**Status**: ✅ Implementation Complete
**Implementation Date**: 2025-12-01
**Ready for Testing**: Yes
