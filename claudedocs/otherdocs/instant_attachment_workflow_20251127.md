# Duplicate Skill Issue Analysis - 2025-11-27

## Problem Description

When uploading a PDF to an existing skill via the new `upload_source_to_skill` endpoint, the system creates a **NEW skill** with the same name instead of adding to the existing skill. This results in duplicate skills appearing in the UI.

### Screenshot Evidence
![Two LLM Skills](../refData/errors/images/two_LLM_skill.png)

---

## Root Cause Analysis

### Code Location
- **File**: `app/api/v1/endpoints/skills.py`
- **Function**: `process_pdf_for_skill()` (lines 628-821)

### Issue
The `process_pdf_for_skill()` function always generates a **new skill_id** and creates a new skill record, regardless of whether a skill with the same name already exists.

```python
# Current behavior (problematic)
skill_id = f"skill_{timestamp}_{name_hash}"  # Always creates new ID
await metadata_provider.create_skill(...)     # Always creates new record
```

---

## Data Clarification

### Database Query Results
```sql
SELECT skill_id, skill_name, total_chunks FROM skill_metadata WHERE skill_name = 'LLM';
```

| Skill ID | Name | Chunks | Created | Documents |
|----------|------|--------|---------|-----------|
| skill_20251126_105138_b8cc08c1 | LLM | 883 | 11/26 | Build_a_Large_Language_Model_From_Scratch, LLM_Engineers_Handbook |
| skill_20251127_100500_b8cc08c1 | LLM | 385 | 11/27 | Decoding_Large_Language_Models |

### Important Finding
**They contain DIFFERENT books!** Deleting either one loses unique data.

- **Original (883 chunks)**: Contains 2 books from initial skill build
- **New (385 chunks)**: Contains 1 book from the upload test

---

## Proposed Solution: Three-Level Hierarchy

### UI Concept
```
📁 Skill Tree
  └── 🧠 LLM (883 chunks - main)
        └── 📎 Instant Attachments
              └── Decoding_Large_Language_Models.pdf (385 chunks)
  └── ⚖️ 六法全書-民法 (533 chunks)
  └── ⚔️ 六法全書-刑法 (272 chunks)
```

### Design Rationale
This matches the existing `instant_attachments` concept in `skill_config.json`:
- Main skill contains the "built" embeddings from rebuild script
- Instant attachments are uploaded PDFs pending integration
- Users can see both in the UI with clear visual distinction

---

## Implementation Options

### Option A: Demo Quick Fix (Recommended for 下周一、二 Demo)

**Action**: Rename the duplicate skill to distinguish it

```sql
UPDATE skill_metadata
SET skill_name = 'LLM (instant)'
WHERE skill_id = 'skill_20251127_100500_b8cc08c1';
```

**Pros**:
- Fast (1 minute)
- No code changes
- All data preserved

**Cons**:
- Not a proper solution
- Manual intervention needed

---

### Option B: Production Solution (Post-Demo)

#### B1. Modify Upload Endpoint
Check if skill exists before creating:
```python
async def process_pdf_for_skill(...):
    # Check for existing skill
    existing = await metadata_provider.get_skill_by_name(skill_name)

    if existing:
        # Add to existing skill's instant attachments
        skill_id = existing['skill_id']
        # Store in instant_attachments table
    else:
        # Create new skill
        skill_id = generate_new_skill_id()
```

#### B2. Modify Sidebar UI
Update `skill_main.html` to show expandable skill items:
```javascript
// Render skill with instant attachments
function renderSkillItem(skill) {
    return `
        <div class="skill-item expandable">
            <div class="skill-header" onclick="toggleSkillExpand('${skill.skill_id}')">
                <i class="fa-solid fa-chevron-right"></i>
                <span>${skill.skill_name}</span>
                <span class="chunk-count">${skill.total_chunks}</span>
            </div>
            <div class="instant-attachments" id="ia-${skill.skill_id}">
                ${skill.instant_attachments.map(renderAttachment).join('')}
            </div>
        </div>
    `;
}
```

#### B3. Modify Query Logic
Search both main skill and instant attachments:
```python
async def query_skill(skill_id: str, query: str):
    # Search main skill index
    main_results = await retrieval_service.search(skill_id, query)

    # Search instant attachments
    instant_results = await search_instant_attachments(skill_id, query)

    # Merge and rank results
    return merge_results(main_results, instant_results)
```

---

## Temporary Workaround for Demo

Until the proper solution is implemented, apply the quick rename:

```bash
# Execute this to rename the duplicate
sqlite3 data/skill_metadata.db "UPDATE skill_metadata SET skill_name='LLM (Decoding)' WHERE skill_id='skill_20251127_100500_b8cc08c1';"
```

Then verify:
```bash
sqlite3 data/skill_metadata.db "SELECT skill_id, skill_name, total_chunks FROM skill_metadata;"
```

---

## Related Files

- `app/api/v1/endpoints/skills.py` - Upload endpoint with `process_pdf_for_skill()`
- `template/skill_main.html` - Sidebar UI
- `scripts/skill_data/skill_config.json` - Contains `instant_attachments` concept
- `data/skill_metadata.db` - SQLite database with duplicate records

---

## Next Steps

1. **Immediate (Demo)**: Apply quick rename workaround
2. **Post-Demo Week 1**: Implement instant_attachments table and API
3. **Post-Demo Week 2**: Update sidebar UI with 3-level hierarchy
4. **Post-Demo Week 3**: Implement merged query logic

---

*Document created: 2025-11-27*
*Status: Issue identified, workaround available, proper solution planned for post-demo*
