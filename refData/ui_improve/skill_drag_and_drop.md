Summary: Drag-and-Drop Skill Ordering Implementation
Changes Made
1. skill_config.json - Added display_order field
Each skill now has a display_order property (0, 1, 2, 3, 4...)
Skills are sorted by this field when rendered
2. skill_config.html - Drag-and-drop UI
CSS additions:
.skill-card.dragging - Visual feedback when dragging (opacity, scale)
.skill-card.drag-over - Dashed border when hovering over drop target
.drag-handle - Grip icon styling
HTML changes:
Added draggable="true" to skill cards
Added drag handle icon (⋮⋮) before skill icon
Skills are now sorted by display_order before rendering
JavaScript additions:
handleDragStart() - Start drag operation
handleDragEnd() - Clean up after drag
handleDragOver() - Visual feedback for valid drop target
handleDragLeave() - Remove visual feedback
handleDrop() - Reorder skills and save to server
saveSkillOrder() - Call API to persist order
3. skills.py - API endpoint for reorder
New endpoint: PUT /api/v1/skills/config/reorder
Accepts JSON: {"order": [{"skill_name": "...", "display_order": 0}, ...]}
Updates display_order in skill_config.json
4. skills.py - Updated /demo endpoint
Now loads display_order from skill_config.json
Returns skills sorted by display_order
Instant attachments inherit parent's display_order
5. skill_main.html - Chat page respects order
groupSkillsByName() now includes display_order
renderSkills() sorts groups by display_order
How to Use
Go to /skill/config
Drag any skill card by its grip handle (⋮⋮)
Drop it at a new position
The order is automatically saved
Go to /skill - skills appear in the new order