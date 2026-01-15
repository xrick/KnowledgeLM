<!-- claudedocs/docai_main_ui_design_spec.md -->
# DocAI Main UI Design Specification

**Date**: 2025-01-XX  
**Status**: ✅ **FINAL DESIGN**  
**Source**: `template/ui_preview_redesigned_tree.html`  
**Focus**: Frontend UI Design Only (No Backend)

---

## 🎯 Design Overview

### Design Philosophy
- **Modern & Minimalist**: Clean, simple interface with grey-based color scheme
- **Consistent Styling**: Unified design language across all components
- **User-Friendly**: Intuitive navigation with clear visual hierarchy
- **Responsive**: Collapsible sidebar for flexible workspace management

### Key Features
- Full-width title banner with logo and navigation
- Collapsible sidebar (expands to 360px, collapses to 60px showing icons only)
- White chat area with centered content
- ChatGPT-style rounded input box with model selector and audio input
- Grey-based color palette for a professional, modern look

---

## 📐 Layout Structure

### Overall Structure
```
┌─────────────────────────────────────────────────────────────┐
│  Title Banner (Full Width)                                    │
│  [☰] [Logo] DocAI with Skills  [Skill Mgmt] [Settings] [🌐] │
├──────────────┬───────────────────────────────────────────────┤
│              │                                               │
│  Sidebar     │  Main Content Area                            │
│  (360px)     │  (Flexible Width)                             │
│              │                                               │
│  • Skill 1   │  ┌─────────────────────────────────────────┐  │
│  • Skill 2   │  │  Welcome Message / Chat Messages      │  │
│  • Skill 3   │  └─────────────────────────────────────────┘  │
│  ...         │                                               │
│              │  ┌─────────────────────────────────────────┐  │
│              │  │  [Input Box] [Model ▼] [🎤]           │  │
│              │  └─────────────────────────────────────────┘  │
└──────────────┴───────────────────────────────────────────────┘
```

### Layout Components

#### 1. Title Banner
- **Width**: 100% (full width)
- **Height**: Auto (padding: 0.75rem 1.5rem)
- **Background**: `#ffffff` (white)
- **Border**: Bottom border `1px solid #e5e7eb`
- **Layout**: Flexbox with `justify-content: space-between`
- **Position**: Fixed at top, `flex-shrink: 0`

#### 2. Sidebar
- **Width (Expanded)**: `360px`
- **Width (Collapsed)**: `60px`
- **Background**: `#f9fafb` (light grey)
- **Border**: Right border `1px solid #e5e7eb`
- **Transition**: `width 0.3s ease`
- **Overflow**: `hidden`

#### 3. Main Content Area
- **Background**: `#ffffff` (white) for chat area
- **Layout**: Flex column
- **Padding**: `2rem` (chat area)
- **Max Width**: `900px` (centered for chat messages)

#### 4. Input Area
- **Background**: `#ffffff` (white)
- **Border**: Top border `1px solid #e5e7eb`
- **Padding**: `1rem 0`
- **Width**: Full width with `2rem` side margins

---

## 🎨 Color Palette

### Primary Colors

#### Backgrounds
| Element | Color | Hex Code |
|---------|-------|----------|
| Body Background | Light Grey | `#f5f5f5` |
| Sidebar Background | Very Light Grey | `#f9fafb` |
| Main Content | White | `#ffffff` |
| Skill Item Background | White | `#ffffff` |
| Selected Skill Background | Medium Grey | `#e5e7eb` |
| Hover Background | Light Grey | `#f3f4f6` or `#f9fafb` |

#### Borders
| Element | Color | Hex Code |
|---------|-------|----------|
| Default Border | Light Grey | `#e5e7eb` |
| Input Border | Medium Grey | `#d1d5db` |
| Focus Border | Blue | `#2563eb` |
| Selected Skill Border | Grey | `#9ca3af` |

#### Text Colors
| Element | Color | Hex Code |
|---------|-------|----------|
| Primary Text | Dark Grey | `#1f2937` |
| Secondary Text | Medium Grey | `#64748b` |
| Muted Text | Light Grey | `#6b7280` |
| Placeholder Text | Light Grey | `#9ca3af` |

#### Interactive Elements
| Element | Color | Hex Code |
|---------|-------|----------|
| Button Background (Active) | Blue | `#2563eb` |
| Button Hover | Dark Blue | `#1d4ed8` |
| Button Disabled | Grey | `#d1d5db` |
| Badge Background (Default) | Light Grey | `#f3f4f6` |
| Badge Background (Selected) | Medium Grey | `#9ca3af` |
| Badge Text (Selected) | White | `#ffffff` |

---

## 📝 Typography

### Font Family
```css
font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
```

### Font Sizes

| Element | Size | Weight | Line Height |
|---------|------|--------|-------------|
| Title Text | `1rem` | `600` | Normal |
| Navigation Buttons | `0.875rem` | `500` | Normal |
| Skill Name | `0.875rem` | `500` | Normal |
| Chat Message | `0.95rem` | Normal | `1.6` |
| Input Text | `0.95rem` | Normal | `1.5` |
| Badge | `0.7rem` | `500` | Normal |
| Model Selector | `0.8rem` | Normal | Normal |
| Welcome Title | `1.25rem` | `600` | Normal |
| Welcome Text | `0.95rem` | Normal | `1.6` |

### Letter Spacing
- Title: `-0.01em` (slightly tighter)

---

## 🧩 Component Specifications

### 1. Title Banner

#### Structure
```html
<div class="title-banner">
  <div class="title-banner-left">
    <button class="sidebar-toggle">[☰]</button>
    <img class="logo" src="mapleleaf_taiwan.svg">
    <div class="title-text">DocAI with Skills</div>
  </div>
  <div class="title-banner-right">
    <a class="nav-icon-item">[📁] Skill Management</a>
    <a class="nav-icon-item">[⚙️] Settings</a>
    <div class="language-selector">[🌐] English</div>
  </div>
</div>
```

#### Styling
- **Background**: `#ffffff`
- **Padding**: `0.75rem 1.5rem`
- **Border**: Bottom `1px solid #e5e7eb`
- **Layout**: Flexbox, `justify-content: space-between`
- **Alignment**: `align-items: center`

#### Logo
- **Height**: `28px`
- **Width**: `auto`
- **Object Fit**: `contain`

#### Title Text
- **Font Size**: `1rem`
- **Font Weight**: `600`
- **Color**: `#1f2937`
- **Letter Spacing**: `-0.01em`

---

### 2. Sidebar Toggle Button

#### Styling
- **Size**: `36px × 36px`
- **Background**: `transparent`
- **Border Radius**: `6px`
- **Color**: `#64748b`
- **Icon Size**: `1.1rem`
- **Transition**: `all 0.2s`

#### States
- **Default**: Transparent background, grey icon
- **Hover**: Background `#f9fafb`, color `#111827`
- **Collapsed**: Icon changes to `fa-chevron-right`

---

### 3. Navigation Buttons (Skill Management, Settings)

#### Structure
```html
<a class="nav-icon-item [active]">
  <i class="fa-solid fa-folder-open"></i>
  <span>Skill Management</span>
</a>
```

#### Styling
- **Display**: Flex, `align-items: center`
- **Gap**: `0.5rem`
- **Padding**: `0.5rem 0.75rem`
- **Border Radius**: `6px`
- **Font Size**: `0.875rem`
- **Color**: `#6b7280`
- **Background**: `transparent`
- **Icon Size**: `0.875rem`
- **Font Weight**: `500` (span)

#### States
- **Default**: Transparent background, grey text
- **Hover**: Background `#f3f4f6`, color `#374151`
- **Active**: Background `#e5e7eb`, color `#374151`, font-weight `500`

#### Icons
- Skill Management: `fa-folder-open`
- Settings: `fa-gear`

---

### 4. Language Selector

#### Structure
```html
<div class="language-selector">
  <i class="fa-solid fa-globe"></i>
  <span>English</span>
</div>
```

#### Styling
- **Display**: Flex, `align-items: center`
- **Gap**: `0.5rem`
- **Padding**: `0.5rem 0.75rem`
- **Border Radius**: `6px`
- **Font Size**: `0.875rem`
- **Color**: `#6b7280`
- **Background**: `transparent`
- **Icon Size**: `0.875rem`
- **Font Weight**: `500` (span)

#### States
- **Default**: Transparent background, grey text
- **Hover**: Background `#f3f4f6`, color `#374151`

---

### 5. Sidebar

#### Expanded State
- **Width**: `360px`
- **Background**: `#f9fafb`
- **Border**: Right `1px solid #e5e7eb`
- **Display**: Flex column
- **Overflow**: `hidden`

#### Collapsed State
- **Width**: `60px`
- **Skill Name**: Hidden (`display: none`)
- **Skill Badge**: Hidden (`display: none`)
- **Settings Button**: Hidden (`display: none`)
- **Skill Items**: Centered, padding `0.75rem`, margin `0.25rem 0.5rem`
- **Icons**: Still visible

#### Transition
- **Property**: `width`
- **Duration**: `0.3s`
- **Timing**: `ease`

---

### 6. Skill Item

#### Structure
```html
<div class="skill-item [selected]">
  <i class="fa-solid fa-gavel skill-icon"></i>
  <span class="skill-name">Contract Law</span>
  <span class="skill-count-badge">156</span>
  <button class="skill-settings-btn">
    <i class="fa-solid fa-ellipsis-vertical"></i>
  </button>
</div>
```

#### Styling
- **Display**: Flex, `align-items: center`
- **Padding**: `0.75rem 1rem 0.75rem 1.5rem`
- **Margin**: `0.125rem 0.5rem`
- **Gap**: `0.75rem`
- **Background**: `#ffffff`
- **Border**: Left `3px solid transparent`
- **Border Radius**: `6px`
- **Color**: `#64748b`
- **Cursor**: `pointer`
- **Transition**: `all 0.2s ease`

#### Skill Icon
- **Font Size**: `1.1rem`
- **Width**: `24px`
- **Flex Shrink**: `0`

#### Skill Name
- **Flex**: `1`
- **Font Size**: `0.875rem`
- **Font Weight**: `500`
- **Text Overflow**: `ellipsis`
- **White Space**: `nowrap`
- **Overflow**: `hidden`

#### Skill Count Badge
- **Font Size**: `0.7rem`
- **Padding**: `0.2rem 0.5rem`
- **Border Radius**: `10px`
- **Background**: `#f3f4f6`
- **Color**: `#6b7280`
- **Font Weight**: `500`
- **Flex Shrink**: `0`

#### Settings Button
- **Size**: `28px × 28px`
- **Display**: Flex, centered
- **Border Radius**: `4px`
- **Color**: `#6b7280`
- **Background**: `transparent`
- **Opacity**: `0` (visible on hover)
- **Icon Size**: `0.875rem`

#### States
- **Default**: White background, transparent left border
- **Hover**: Background `#f9fafb`, settings button opacity `1`
- **Selected**: 
  - Background `#e5e7eb`
  - Border left `3px solid #9ca3af`
  - Color `#1f2937`
  - Badge background `#9ca3af`, text `white`
- **Collapsed Selected**: Border top `3px solid #9ca3af` (instead of left)

---

### 7. Chat Area

#### Structure
```html
<div class="chat-area [empty]">
  <div class="welcome-message">
    <h3>Welcome to DocAI with Skills</h3>
    <p>Select a skill to query...</p>
  </div>
  <div class="chat-messages">
    <div class="message user">
      <div class="message-content">User message</div>
    </div>
    <div class="message assistant">
      <div class="message-content">Assistant message</div>
    </div>
  </div>
</div>
```

#### Styling
- **Flex**: `1`
- **Overflow**: `overflow-y: auto`
- **Padding**: `2rem`
- **Display**: Flex column
- **Gap**: `1rem`
- **Background**: `#ffffff`

#### Empty State
- **Alignment**: `align-items: center`, `justify-content: center`

#### Welcome Message
- **Text Align**: `center`
- **Color**: `#64748b`
- **Max Width**: `600px`

#### Welcome Title (h3)
- **Font Size**: `1.25rem`
- **Color**: `#1e293b`
- **Margin Bottom**: `0.5rem`
- **Font Weight**: `600`

#### Welcome Text (p)
- **Font Size**: `0.95rem`
- **Line Height**: `1.6`
- **Color**: `#64748b`

---

### 8. Chat Messages

#### Container
- **Display**: Flex column
- **Gap**: `1.5rem`
- **Max Width**: `900px`
- **Width**: `100%`
- **Margin**: `0 auto` (centered)
- **Padding**: `1rem 0`

#### Message
- **Display**: Flex
- **Width**: `100%`
- **Animation**: `fadeIn 0.3s ease-in`

#### User Message
- **Justify Content**: `flex-end` (right aligned)
- **Padding Left**: `2rem`
- **Message Content**: `margin-left: auto`

#### Assistant Message
- **Justify Content**: `flex-start` (left aligned)
- **Padding Right**: `2rem`

#### Message Content
- **Max Width**: `70%`
- **Padding**: `1rem 1.25rem`
- **Border Radius**: `18px`
- **Line Height**: `1.6`
- **Font Size**: `0.95rem`
- **Word Wrap**: `break-word`

#### User Message Content
- **Background**: `#f3f4f6`
- **Color**: `#1f2937`
- **Border Radius**: `18px` with `border-bottom-right-radius: 4px`

#### Assistant Message Content
- **Background**: `#f3f4f6`
- **Color**: `#1f2937`
- **Border Radius**: `18px` with `border-bottom-left-radius: 4px`

#### Animation
```css
@keyframes fadeIn {
  from { 
    opacity: 0; 
    transform: translateY(10px); 
  }
  to { 
    opacity: 1; 
    transform: translateY(0); 
  }
}
```

---

### 9. Input Area

#### Structure
```html
<div class="input-area">
  <div class="input-wrapper">
    <div class="input-main">
      <textarea placeholder="..."></textarea>
    </div>
    <div class="input-actions">
      <div class="model-selector">
        <i class="fa-solid fa-chevron-down"></i>
        <span>Model</span>
      </div>
      <button class="audio-input-btn">
        <i class="fa-solid fa-microphone"></i>
      </button>
    </div>
  </div>
</div>
```

#### Input Area Container
- **Padding**: `1rem 0`
- **Background**: `#ffffff`
- **Border**: Top `1px solid #e5e7eb`
- **Display**: Flex, `align-items: center`, `justify-content: center`

#### Input Wrapper
- **Display**: Flex, `align-items: center`
- **Gap**: `0.75rem`
- **Padding**: `0.75rem 1rem`
- **Background**: `#ffffff`
- **Border**: `1px solid #d1d5db`
- **Border Radius**: `24px`
- **Width**: `100%`
- **Margin**: `0 2rem`
- **Box Shadow**: `0 1px 2px rgba(0, 0, 0, 0.05)`
- **Transition**: `all 0.2s`

#### Focus State
- **Border Color**: `#2563eb`
- **Box Shadow**: `0 2px 8px rgba(37, 99, 235, 0.15)`

#### Textarea
- **Flex**: `1`
- **Border**: `none`
- **Background**: `transparent`
- **Font Size**: `0.95rem`
- **Color**: `#1f2937`
- **Outline**: `none`
- **Resize**: `none`
- **Max Height**: `200px`
- **Line Height**: `1.5`
- **Padding**: `0`
- **Margin**: `0`
- **Vertical Align**: `middle`

#### Placeholder
- **Color**: `#9ca3af`

#### Model Selector
- **Display**: Flex, `align-items: center`
- **Gap**: `0.5rem`
- **Padding**: `0.5rem 0.75rem`
- **Background**: `#f9fafb`
- **Border**: `1px solid #e5e7eb`
- **Border Radius**: `12px`
- **Font Size**: `0.8rem`
- **Color**: `#64748b`
- **Cursor**: `pointer`
- **Transition**: `all 0.2s`
- **Icon Size**: `0.75rem`

#### Model Selector Hover
- **Background**: `#f3f4f6`
- **Border Color**: `#d1d5db`

#### Audio Input Button
- **Size**: `36px × 36px`
- **Display**: Flex, centered
- **Background**: `#2563eb`
- **Color**: `white`
- **Border**: `none`
- **Border Radius**: `50%` (circle)
- **Cursor**: `pointer`
- **Transition**: `all 0.2s`
- **Flex Shrink**: `0`

#### Audio Input Button States
- **Hover (enabled)**: Background `#1d4ed8`, `transform: scale(1.05)`
- **Disabled**: Background `#d1d5db`, `cursor: not-allowed`

#### Send Button (if present)
- **Size**: `36px × 36px`
- **Display**: Flex, centered
- **Background**: `#2563eb`
- **Color**: `white`
- **Border**: `none`
- **Border Radius**: `50%` (circle)
- **Font Size**: `0.875rem`
- **Cursor**: `pointer`
- **Transition**: `all 0.2s`
- **Flex Shrink**: `0`

#### Send Button States
- **Hover (enabled)**: Background `#1d4ed8`, `transform: scale(1.05)`
- **Disabled**: Background `#d1d5db`, `cursor: not-allowed`

---

## 🎭 Interactive States

### Hover States
- **Navigation Buttons**: Background `#f3f4f6`, color `#374151`
- **Language Selector**: Background `#f3f4f6`, color `#374151`
- **Skill Item**: Background `#f9fafb`, settings button opacity `1`
- **Settings Button**: Background `#e5e7eb`, color `#374151`
- **Model Selector**: Background `#f3f4f6`, border `#d1d5db`
- **Audio/Send Buttons**: Background `#1d4ed8`, scale `1.05`
- **Sidebar Toggle**: Background `#f9fafb`, color `#111827`

### Active/Selected States
- **Navigation Button Active**: Background `#e5e7eb`, color `#374151`, font-weight `500`
- **Skill Item Selected**: 
  - Background `#e5e7eb`
  - Border left `3px solid #9ca3af`
  - Color `#1f2937`
  - Badge background `#9ca3af`, text `white`
- **Collapsed Sidebar Selected**: Border top `3px solid #9ca3af`

### Focus States
- **Input Wrapper Focus**: Border `#2563eb`, box-shadow `0 2px 8px rgba(37, 99, 235, 0.15)`

### Disabled States
- **Audio/Send Buttons**: Background `#d1d5db`, cursor `not-allowed`

---

## 🔄 Transitions & Animations

### Transitions
- **Sidebar**: `width 0.3s ease`
- **Content Wrapper**: `all 0.3s ease`
- **Skill Items**: `all 0.2s ease`
- **Navigation Buttons**: `all 0.2s ease`
- **Input Wrapper**: `all 0.2s`
- **Buttons**: `all 0.2s`

### Animations
- **Message Fade In**: `fadeIn 0.3s ease-in`
  - From: `opacity: 0`, `transform: translateY(10px)`
  - To: `opacity: 1`, `transform: translateY(0)`

---

## 📏 Spacing System

### Padding
- **Title Banner**: `0.75rem 1.5rem`
- **Sidebar Content**: `0.75rem 0`
- **Skill Item**: `0.75rem 1rem 0.75rem 1.5rem`
- **Chat Area**: `2rem`
- **Input Area**: `1rem 0`
- **Input Wrapper**: `0.75rem 1rem`
- **Message Content**: `1rem 1.25rem`
- **Navigation Buttons**: `0.5rem 0.75rem`
- **Language Selector**: `0.5rem 0.75rem`
- **Model Selector**: `0.5rem 0.75rem`

### Margins
- **Skill Item**: `0.125rem 0.5rem`
- **Collapsed Skill Item**: `0.25rem 0.5rem`
- **Input Wrapper**: `0 2rem`
- **User Message**: `padding-left: 2rem`
- **Assistant Message**: `padding-right: 2rem`
- **Chat Messages Container**: `padding: 1rem 0`

### Gaps
- **Title Banner Left**: `0.875rem`
- **Title Banner Right**: `1.5rem`
- **Navigation Items**: `0.5rem`
- **Skill Item**: `0.75rem`
- **Input Wrapper**: `0.75rem`
- **Input Main**: `0.5rem`
- **Input Actions**: `0.5rem`
- **Chat Messages**: `1.5rem`
- **Chat Area**: `1rem`

---

## 🎨 Border Radius

| Element | Border Radius |
|---------|---------------|
| Sidebar Toggle | `6px` |
| Navigation Buttons | `6px` |
| Language Selector | `6px` |
| Skill Item | `6px` |
| Settings Button | `4px` |
| Skill Badge | `10px` |
| Model Selector | `12px` |
| Message Content | `18px` (with modified bottom corners) |
| Input Wrapper | `24px` |
| Audio/Send Buttons | `50%` (circle) |

---

## 🔤 Icons

### Icon Library
- **Font Awesome 6.5.1** (CDN: `https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css`)

### Icon Usage

| Icon | Class | Usage | Size |
|------|-------|-------|------|
| Hamburger Menu | `fa-bars` | Sidebar toggle (expanded) | `1.1rem` |
| Chevron Right | `fa-chevron-right` | Sidebar toggle (collapsed) | `1.1rem` |
| Folder Open | `fa-folder-open` | Skill Management button | `0.875rem` |
| Gear | `fa-gear` | Settings button | `0.875rem` |
| Globe | `fa-globe` | Language selector | `0.875rem` |
| Gavel | `fa-gavel` | Legal skills icon | `1.1rem` |
| Code | `fa-code` | Technical skills icon | `1.1rem` |
| Chart Line | `fa-chart-line` | Financial skills icon | `1.1rem` |
| Book | `fa-book` | Knowledge base icon | `1.1rem` |
| Ellipsis Vertical | `fa-ellipsis-vertical` | Skill settings button | `0.875rem` |
| Chevron Down | `fa-chevron-down` | Model selector | `0.75rem` |
| Microphone | `fa-microphone` | Audio input button | Default |

---

## 📱 Responsive Behavior

### Sidebar Collapse
- **Trigger**: Click on sidebar toggle button
- **Expanded Width**: `360px`
- **Collapsed Width**: `60px`
- **Transition**: `0.3s ease`
- **Collapsed State**:
  - Hides: Skill name, count badge, settings button
  - Shows: Skill icon only
  - Centers: Icon in skill item
  - Selected indicator: Changes from left border to top border

### Mobile Behavior (Optional)
- **Breakpoint**: `768px` (if implemented)
- **Behavior**: Sidebar auto-closes when clicking outside on mobile

---

## 🎯 Design Principles Applied

1. **Consistency**: All buttons, inputs, and interactive elements follow the same design patterns
2. **Visual Hierarchy**: Clear distinction between primary actions, secondary actions, and content
3. **Feedback**: Hover states, active states, and transitions provide clear user feedback
4. **Accessibility**: Sufficient color contrast, clear focus states, readable font sizes
5. **Modern Aesthetics**: Rounded corners, subtle shadows, smooth transitions
6. **Grey-Based Palette**: Professional, neutral color scheme with blue accents for actions

---

## 📋 Implementation Notes

### Key Files
- **Design Source**: `template/ui_preview_redesigned_tree.html`
- **Production Target**: `template/skill_main.html` (to be updated)

### CSS Organization
- All styles are in a single `<style>` block in the HTML file
- No external CSS files used (except Font Awesome CDN)
- Styles organized by component sections with clear comments

### JavaScript
- Sidebar toggle functionality
- Icon state management (hamburger ↔ chevron)
- Optional mobile click-outside-to-close behavior

---

## ✅ Design Checklist

- [x] Full-width title banner with logo
- [x] Collapsible sidebar (360px ↔ 60px)
- [x] Grey-based color scheme
- [x] White chat area
- [x] ChatGPT-style input box
- [x] Model selector in input area
- [x] Audio input button
- [x] Skill list with count badges
- [x] Settings button on hover
- [x] Navigation buttons with icons
- [x] Language selector
- [x] Smooth transitions
- [x] Consistent spacing
- [x] Modern rounded corners
- [x] Clear visual hierarchy

---

**Document Version**: 1.0  
**Last Updated**: 2025-01-XX  
**Maintained By**: Design Team

