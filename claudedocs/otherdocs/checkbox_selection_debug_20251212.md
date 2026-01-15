# Checkbox Selection Debug Analysis

**Date**: 2025-12-12
**Issue**: User expands AMD skill tree, selects checkbox, but query still returns "找不到相關資訊"
**User Confirmation**: "I am very sure I select AMD skill" + "I do expand the AMD skill tree, and select the checkbox"

---

## 🔍 Root Cause Hypothesis

**Hypothesis**: Frontend sends incorrect skill_id or no skill_id at all to backend

### Evidence Chain

#### 1. Frontend Checkbox HTML Generation (Line 1861)

```html
<input type="checkbox"
       class="item-checkbox"
       data-item-id="${doc.skill_id}"
       onclick="handleCheckboxClick(event, '${safeId}')"
       ${checkedItems.has(doc.skill_id) ? 'checked' : ''}>
```

**Key Variables**:
- `doc.skill_id`: Raw skill ID from API (e.g., `skill_20251211_161308_48af4341_feb60e`)
- `safeId`: Escaped ID with `replace(/'/g, "\\'")`

**Problem**: Two different ID sources:
1. `data-item-id="${doc.skill_id}"` (unescaped)
2. `onclick="handleCheckboxClick(event, '${safeId}')"` (escaped)

---

#### 2. Checkbox Click Handler (Lines 2865-2886)

```javascript
function handleCheckboxClick(event, itemId) {
    event.stopPropagation();
    const checkbox = event.target;

    if (checkbox.checked) {
        checkedItems.add(itemId);  // ✅ Uses onclick parameter (safeId)
    } else {
        checkedItems.delete(itemId);
    }

    updateSelectedFromCheckboxes();
}
```

**Observation**: Uses `itemId` parameter from onclick (which is `safeId`)

---

#### 3. "Select All" Handler (Lines 2813-2844)

```javascript
function toggleSkillSelectAll(groupId, event) {
    const groupItems = document.querySelectorAll(`.attachment-item[data-group-id="${groupId}"]`);

    groupItems.forEach(item => {
        const checkbox = item.querySelector('.item-checkbox');
        const itemId = checkbox?.dataset?.itemId;  // ✅ Uses data-item-id attribute

        if (checkbox && itemId) {
            checkbox.checked = isChecked;
            if (isChecked) {
                checkedItems.add(itemId);  // Uses dataset (unescaped)
```

**Critical Difference**:
- **Individual checkbox click**: Uses onclick parameter (`safeId` - escaped)
- **Select All**: Uses dataset.itemId (unescaped `doc.skill_id`)

**Potential Issue**: If skill_id contains special characters, these two paths will store different values in `checkedItems` Set!

---

#### 4. Update Selected Skills (Lines 2888-2944)

```javascript
function updateSelectedFromCheckboxes() {
    selectedSkills = [];
    checkedItems.forEach(itemId => {
        if (allSkillsData[0]?.head_id) {
            // Tree format - search in documents
            for (const skill of allSkillsData) {
                if (skill.documents) {
                    const doc = skill.documents.find(d => d.skill_id === itemId);
                    if (doc) {
                        selectedSkills.push({
                            id: itemId,  // ✅ Should be skill_id
                            name: doc.source_name || 'Document',
                            chunks: doc.total_chunks || 0,
                            category: skill.category || 'General',
                            isAttachment: true
                        });
                        break;
                    }
                }
            }
        }
    });
}
```

**Search Logic**: `d.skill_id === itemId`
- If `itemId` is escaped but `d.skill_id` is not, match will fail!
- If `itemId` is unescaped, match should succeed

---

#### 5. Query Send (Lines 2448-2452)

```javascript
const skillIds = selectedSkills.map(s => s.id);
const requestBody = skillIds.length > 1
    ? { skill_ids: skillIds, query: query, top_k: 10 }
    : { skill_id: skillIds[0], query: query, top_k: 10 };
```

**What gets sent**:
- If `selectedSkills` is empty → `skillIds` is empty → API error
- If `selectedSkills` has wrong ID → Backend can't find documents

---

## 🐛 Test Scenarios

### Scenario A: Individual Checkbox Click
**User Action**: Expand AMD → Click checkbox next to "Strix Halo Engineering Interlock..."

**Expected Flow**:
1. onclick triggers: `handleCheckboxClick(event, 'skill_20251211_161308_48af4341_feb60e')`
2. `checkedItems.add('skill_20251211_161308_48af4341_feb60e')`
3. `updateSelectedFromCheckboxes()` finds match in `allSkillsData`
4. `selectedSkills = [{ id: 'skill_20251211_161308_48af4341_feb60e', ... }]`
5. Query sends: `{ skill_id: 'skill_20251211_161308_48af4341_feb60e', ... }`

**If Escape Causes Issue**:
- Step 1: `safeId` might be different if skill_id contains `'`
- Step 3: `find(d => d.skill_id === itemId)` fails because of escape mismatch
- Step 4: `selectedSkills` is empty
- Step 5: API error or 404

---

### Scenario B: "Select All" Click
**User Action**: Expand AMD → Click "選取此技能的所有文件"

**Expected Flow**:
1. `toggleSkillSelectAll('head_xxx', event)` triggers
2. Reads `checkbox.dataset.itemId` (unescaped `doc.skill_id`)
3. `checkedItems.add(doc.skill_id)`
4. `updateSelectedFromCheckboxes()` finds match (both unescaped)
5. Should work correctly!

**Hypothesis**: If "Select All" works but individual checkbox doesn't, it's an escape issue.

---

## 🔧 Diagnosis Steps

### Step 1: Verify Actual skill_id Format
```bash
sqlite3 data/skill_metadata.db "SELECT skill_id FROM skill_metadata WHERE skill_name = 'AMD';"
```

**Expected**: `skill_20251211_161308_48af4341_feb60e`
**Check**: Does it contain single quotes (`'`) or other special characters?

---

### Step 2: Add Console Logging

**Modify template/skill_main.html** - Add temporary debug logs:

```javascript
// Line 2870 - handleCheckboxClick
function handleCheckboxClick(event, itemId) {
    event.stopPropagation();
    const checkbox = event.target;

    console.log('=== Checkbox Click Debug ===');
    console.log('itemId (onclick param):', itemId);
    console.log('checkbox.dataset.itemId:', checkbox.dataset.itemId);
    console.log('Match?', itemId === checkbox.dataset.itemId);

    if (checkbox.checked) {
        checkedItems.add(itemId);
    } else {
        checkedItems.delete(itemId);
    }

    console.log('checkedItems after:', Array.from(checkedItems));
    updateSelectedFromCheckboxes();
}

// Line 2903 - updateSelectedFromCheckboxes
function updateSelectedFromCheckboxes() {
    selectedSkills = [];
    console.log('=== Update Selected Debug ===');
    console.log('checkedItems:', Array.from(checkedItems));
    console.log('allSkillsData:', allSkillsData);

    checkedItems.forEach(itemId => {
        console.log('Searching for itemId:', itemId);
        if (allSkillsData[0]?.head_id) {
            for (const skill of allSkillsData) {
                if (skill.documents) {
                    const doc = skill.documents.find(d => d.skill_id === itemId);
                    if (doc) {
                        console.log('Found doc:', doc);
                        selectedSkills.push({
                            id: itemId,
                            name: doc.source_name || 'Document',
                            chunks: doc.total_chunks || 0,
                            category: skill.category || 'General',
                            isAttachment: true
                        });
                        break;
                    } else {
                        console.log('No match in skill:', skill.skill_name, 'docs:', skill.documents.map(d => d.skill_id));
                    }
                }
            }
        }
    });

    console.log('selectedSkills after:', selectedSkills);
}

// Line 2449 - sendTraditionalQuery
const skillIds = selectedSkills.map(s => s.id);
console.log('=== Query Send Debug ===');
console.log('selectedSkills:', selectedSkills);
console.log('skillIds:', skillIds);
const requestBody = skillIds.length > 1
    ? { skill_ids: skillIds, query: query, top_k: 10 }
    : { skill_id: skillIds[0], query: query, top_k: 10 };
console.log('requestBody:', requestBody);
```

---

### Step 3: Test with Browser DevTools

1. Open browser DevTools (F12) → Console tab
2. Navigate to `/skill`
3. Expand AMD skill tree
4. Check checkbox next to "Strix Halo Engineering Interlock..."
5. Observe console logs

**Expected Output**:
```
=== Checkbox Click Debug ===
itemId (onclick param): skill_20251211_161308_48af4341_feb60e
checkbox.dataset.itemId: skill_20251211_161308_48af4341_feb60e
Match? true
checkedItems after: ['skill_20251211_161308_48af4341_feb60e']

=== Update Selected Debug ===
checkedItems: ['skill_20251211_161308_48af4341_feb60e']
allSkillsData: [{head_id: 'head_xxx', documents: [...]}]
Searching for itemId: skill_20251211_161308_48af4341_feb60e
Found doc: {skill_id: 'skill_20251211_161308_48af4341_feb60e', source_name: 'Strix Halo...', total_chunks: 67}
selectedSkills after: [{id: 'skill_20251211_161308_48af4341_feb60e', name: 'Strix Halo...', chunks: 67}]

=== Query Send Debug ===
selectedSkills: [{id: 'skill_20251211_161308_48af4341_feb60e', ...}]
skillIds: ['skill_20251211_161308_48af4341_feb60e']
requestBody: {skill_id: 'skill_20251211_161308_48af4341_feb60e', query: 'strix halo', top_k: 10}
```

**If Mismatch Occurs**:
```
=== Checkbox Click Debug ===
itemId (onclick param): skill_20251211_161308_48af4341_feb60e\\'
checkbox.dataset.itemId: skill_20251211_161308_48af4341_feb60e
Match? false  ← ❌ PROBLEM FOUND!
```

---

## 💡 Potential Fixes

### Fix 1: Use dataset.itemId in handleCheckboxClick (Recommended)

**Problem**: onclick parameter and dataset have inconsistent values

**Solution**: Always use dataset for consistency

```javascript
function handleCheckboxClick(event, itemId) {
    event.stopPropagation();
    const checkbox = event.target;

    // ✅ FIX: Use dataset.itemId instead of onclick parameter
    const actualItemId = checkbox.dataset.itemId;

    if (checkbox.checked) {
        checkedItems.add(actualItemId);
    } else {
        checkedItems.delete(actualItemId);
    }

    updateSelectAllState();
    updateSelectedFromCheckboxes();
}
```

**HTML**: Keep as is (both onclick and data-item-id remain)

---

### Fix 2: Remove onclick parameter (Cleaner)

**Problem**: onclick parameter is redundant with dataset

**Solution**: Remove onclick parameter entirely

**HTML Change** (Line 1861):
```html
<!-- OLD -->
<input type="checkbox" class="item-checkbox"
       data-item-id="${doc.skill_id}"
       onclick="handleCheckboxClick(event, '${safeId}')" ...>

<!-- NEW -->
<input type="checkbox" class="item-checkbox"
       data-item-id="${doc.skill_id}"
       onclick="handleCheckboxClick(event)" ...>
```

**JavaScript Change**:
```javascript
function handleCheckboxClick(event) {
    event.stopPropagation();
    const checkbox = event.target;
    const itemId = checkbox.dataset.itemId;  // ✅ Always use dataset

    if (checkbox.checked) {
        checkedItems.add(itemId);
    } else {
        checkedItems.delete(itemId);
    }

    updateSelectAllState();
    updateSelectedFromCheckboxes();
}
```

---

## 🧪 Verification Checklist

After applying fix:

- [ ] Expand AMD skill tree
- [ ] Click checkbox next to "Strix Halo Engineering Interlock..."
- [ ] Verify console shows correct skill_id in selectedSkills
- [ ] Type query "strix halo"
- [ ] Click send
- [ ] Verify Network tab shows correct request body
- [ ] Verify response contains results (not "找不到")

---

## 📊 Comparison with Working Scenarios

| Scenario | Works? | ID Source | Why |
|----------|--------|-----------|-----|
| Click skill header | ❌ → ✅ (after Fix 2) | onclick sends head_id | Backend now converts head_id → skill_id |
| Click "Select All" | ✅ (likely) | dataset.itemId | Uses dataset consistently |
| Click individual checkbox | ❓ (testing needed) | onclick parameter (safeId) | Potential escape mismatch |

---

*Debug Report - Checkbox Selection Logic Analysis*
*Generated: 2025-12-12*
*Status: ⏳ Awaiting Browser Console Verification*
