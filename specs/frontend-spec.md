# KB Manager v2 — Frontend Spec

> **Read `specs/shared-contracts.md` FIRST.** This file covers frontend-specific implementation: pages, screens, UX flows, state management, and design system.

---

## 1. Navigation Structure

```
Sidebar (navy background, always visible)
├── Dashboard        (home icon)
├── Sources          (globe icon)
├── Files            (file icon — badge shows pending review count)
├── KB               (search icon)
└── [New Ingestion]  (button at bottom)
```

- **Discovery page does NOT exist** — link triage is part of the ingestion wizard (Content Map step)
- No floating chat panels or prompt bars

---

## 2. Pages & Screens

### Dashboard (`/dashboard`)

**Stats Strip (top):**

| Total Files | Pending Review | Approved | Public KB | Internal KB | Active Jobs |

**Quick Actions:**
- "New Ingestion" → opens wizard
- "Review Pending" → `/files?tab=pending`
- "All Files" → `/files`

**Active Jobs Section:**
- Cards for each in-progress job: source URL, status (scouting/processing), progress
- Click → goes to job detail (Content Map or progress view)

**Recent Activity:**
- Last 5 completed jobs with summary (files created, approved, review)

---

### Ingestion Wizard (Modal, multi-step)

#### Step 1: Choose Source
Two tabs: **"Crawl a website"** | **"Upload files"**

**Crawl tab:**
- URL input field for the **homepage / root URL** (e.g. `https://www.avis.com/en/home`)
- "Load Site Navigation" button → calls `GET /nav/tree`
- **NavTreeBrowser** fills the modal: full site navigation as an expandable tree
  - Each node shows: page label, path, section
  - Homepage root itself is NOT selectable for ingestion (it's just the entry point for browsing)
  - User selects one or more **section pages** (e.g. "Protections", "Travel Guides", "Locations")
  - Each selected section becomes a separate ingestion job
- Region/Brand auto-detected from URL, editable
- KB Target selector: Public / Internal
- "Continue with N sections" button

**Upload tab:**
- Drag-and-drop zone (accepts MD, TXT, PDF, CSV, DOCX)
- File list with remove buttons
- KB Target selector: Public / Internal
- "Continue" button

**Key UX point**: The homepage is the **starting point for navigation**, not for content extraction. Users browse the site tree and pick which sections to ingest.

#### Step 2: Content Map (web ingestion only, per selected section)
After selecting sections, scouting begins. This is the core new screen.

**Layout:**
```
┌──────────────────────────────────────────────────────────┐
│  Content Map: /en/products-and-services/protections      │
│  [Open page in browser ↗]                                │
│                                                          │
│  ┌─ CONTENT BLOCKS ────────────────────────────────────┐ │
│  │                                                     │ │
│  │  ☑ Hero Section                                     │ │
│  │    "Avis Rental Protections & Coverages"            │ │
│  │                                                     │ │
│  │  ☑ Intro Text                                       │ │
│  │    "We offer a range of protections..."             │ │
│  │                                                     │ │
│  │  ☑ Card: Loss Damage Waiver                         │ │
│  │    "Our premier protection..." [Learn More →]       │ │
│  │    🔗 EXPANSION — will merge with full article      │ │
│  │    └─ /protections/ldw (2000 words, 3 sub-links)   │ │
│  │                                                     │ │
│  │  ☑ Card: Personal Accident Insurance                │ │
│  │    "Covers medical..." [Learn More →]               │ │
│  │    🔗 EXPANSION — will merge with full article      │ │
│  │    └─ /protections/pai (1500 words, 0 sub-links)   │ │
│  │                                                     │ │
│  │  ☐ Footer Navigation                       SKIPPED │ │
│  │    (navigation chrome — auto-excluded)              │ │
│  │                                                     │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌─ LINK SUMMARY ─────────────────────────────────────┐  │
│  │  5 expansion (auto-queued)                          │  │
│  │  1 sibling (auto-queued)                            │  │
│  │  0 navigation (auto-dismissed)                      │  │
│  │  1 uncertain — needs your input ⚠️                  │  │
│  │                                                     │  │
│  │  🟡 /en/products-and-services/overview              │  │
│  │     Found in: Intro paragraph inline link           │  │
│  │     Agent says: "Can't determine — could be a      │  │
│  │     parent page or a different section"             │  │
│  │     [Ingest as sibling] [Dismiss] [Peek →]          │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌─ STEERING PROMPT ──────────────────────────────────┐  │
│  │  [Optional: guide the extraction agent...]          │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                          │
│  "This will process 1 source page + 6 linked pages       │
│   producing ~7 merged files"                             │
│                                                          │
│  [← Back]                          [Confirm & Process]   │
└──────────────────────────────────────────────────────────┘
```

**Interactions:**
- Checkboxes on components: include/exclude from extraction
- Link classification overrides: click to change classification
- "Peek →" on uncertain links: fetches linked page structure via `GET /ingest/{job_id}/content-map`, shows mini-preview inline
- "N sub-links" note: informational only. User can ingest them separately later.
- "Open page in browser ↗": simple `<a target="_blank">` link

**During scouting (before Content Map is complete):**
- Show components and links appearing in real-time as SSE events arrive via `useScoutStream(jobId)`
- Pulsing skeleton for items still loading
- Link classifications appear as they're resolved (each link goes from "classifying..." to classified)

#### Step 3: Processing (after confirm)
Wizard stays open, shows real-time progress via `useProgressStream(jobId)`:

```
┌──────────────────────────────────────────────────────────┐
│  Processing: /en/products-and-services/protections       │
│  ████████████████████░░░░░░░  4/7 pages                  │
│                                                          │
│  ✅ Hero + Intro → protections-overview.md               │
│     Quality: good  |  Uniqueness: unique  |  APPROVED    │
│                                                          │
│  ✅ LDW (merged: card + full article) → ldw.md           │
│     Quality: good  |  Uniqueness: unique  |  APPROVED    │
│                                                          │
│  ⏳ PAI (merged: card + full article) → extracting...    │
│                                                          │
│  ⬜ ALI                                                   │
│  ⬜ ESP                                                   │
│  ⬜ PEP                                                   │
│  ⬜ TPL                                                   │
│                                                          │
│  [Minimize — continue in background]                     │
└──────────────────────────────────────────────────────────┘
```

**On completion:**
```
┌──────────────────────────────────────────────────────────┐
│  ✅ Ingestion Complete                                   │
│                                                          │
│  7 files created                                         │
│  5 approved (uploaded to KB)                             │
│  2 need review                                           │
│  0 rejected                                              │
│                                                          │
│  [Review pending files]    [View all files]    [Close]   │
└──────────────────────────────────────────────────────────┘
```

---

### Files Page (`/files`)

**Two tabs**: "Pending Review" | "All Files"

**Filter bar**: search, region, brand, content_type, kb_target, status (All Files only)

**Table columns**: Title, Status, Quality, Uniqueness, KB Target, Source, Created

**Quality column**: Verdict badge — `Good ✓` (green) | `Acceptable ⚠` (amber) | `Poor ✗` (red)

**Uniqueness column**: Verdict badge — `Unique ✓` | `Overlapping ⚠` | `Duplicate ✗`

**Row click** → opens file detail panel (right sidebar or modal)

**File Detail Panel:**
```
┌─────────────────────────────────────────────┐
│  Loss Damage Waiver (LDW)                   │
│  Status: Pending Review                     │
│                                             │
│  ── Quality Report ──────────────────────── │
│  Verdict: Good ✓                            │
│  "Substantial 2000-word article covering    │
│   LDW details, eligibility, claim process.  │
│   Well-structured with clear sections."     │
│                                             │
│  ── Uniqueness Report ───────────────────── │
│  Verdict: Overlapping ⚠                     │
│  "73% semantic overlap with 'Rental         │
│   Protections Overview'. That file covers   │
│   protections broadly; this one goes deep   │
│   on LDW specifically."                     │
│  Similar: [Rental Protections Overview →]   │
│                                             │
│  ── Content ─────────────────────────────── │
│  [Preview] [Edit]                           │
│  (markdown rendered preview)                │
│                                             │
│  ── Metadata ────────────────────────────── │
│  Source: /en/protections/ldw                │
│  Merged from: /protections (card) +         │
│    /protections/ldw (full)                  │
│  Region: NAM | Brand: Avis | KB: Public    │
│                                             │
│  [Approve]  [Reject]                        │
│  Notes: [optional input]                    │
└─────────────────────────────────────────────┘
```

**Similar file click**: Expands inline below the uniqueness report showing the similar file's title, source URL, and a short content snippet (~200 chars). No side-by-side panel, no separate page, no navigation away. Just enough context to decide if it's a real overlap.

---

### Sources Page (`/sources`)

**Table**: Type (AEM/Upload icon), URL/Filename, Brand, Region, KB Target, Files count, Last Ingested, Status

**Source Detail** (`/sources/{sourceId}`):
- Stats: total files, approved, pending, rejected
- Jobs list with status + summary
- Files subtable filtered to this source

---

### KB Page (`/kb`)

**Mode toggle**: Retrieve | Retrieve & Generate

**KB Target selector**: Public | Internal | Both

**Search/Chat interface**: Input field, streaming results/answers, source pills with expand.

This is the ONLY chat interface in v2. No floating panels or prompt bars.

---

## 3. State Management

**SWR hooks (data fetching):**
- `useStats()` — dashboard stats, 30s refresh
- `useActiveJobs()` — active jobs, 5s refresh
- `useSources(filters)` — paginated sources
- `useFiles(filters)` — paginated files
- `useFileDetail(fileId)` — single file with QA reports
- `useContentMap(jobId)` — content map data (after scouting)
- `useScoutStream(jobId)` — SSE connection for scouting phase
- `useProgressStream(jobId)` — SSE connection for processing phase

**URL state**: Tab, mode, filters all in URL search params for deep-linking.

---

## 4. Design System — Avis Budget Group Theme

### Brand Colors

| Token | Hex | Usage |
|-------|-----|-------|
| `primary-red` | `#D4002A` | Primary CTA buttons, active states, key accents |
| `primary-red-hover` | `#91001D` | Button hover states |
| `navy` | `#275075` | Section backgrounds, secondary buttons, sidebar |
| `white` | `#FFFFFF` | Page backgrounds, text on dark surfaces |
| `black` | `#0D0D0B` | Primary text |
| `gray-700` | `#524D4D` | Secondary text |
| `gray-500` | `#736D6D` | Tertiary text, placeholders |
| `gray-200` | `#E8E6E6` | Borders, dividers, disabled states |
| `gray-100` | `#F4F4F4` | Subtle backgrounds, card fills |

### Verdict Badge Colors

| Badge | Background | Text |
|-------|-----------|------|
| Good / Unique ✓ | `#E8F5E9` | `#2E7D32` |
| Acceptable / Overlapping ⚠ | `#FFF3E0` | `#E65100` |
| Poor / Duplicate ✗ | `#FFEBEE` | `#C62828` |

### Status Badges

| Status | Color |
|--------|-------|
| Approved | Green |
| Pending Review | Amber |
| Rejected | Red |
| Processing / Scouting | Navy (pulsing animation) |

### Typography
- Body: Inter or system sans-serif font stack
- Monospace: for URLs, code, and technical metadata

### Overall Aesthetic
Professional, high-contrast, clean. Red accents on white backgrounds. Navy for depth (sidebar, section headers). Minimal decoration — let content breathe.

**Sidebar**: Navy (`#275075`) background, white text, red accent bar on active nav item.

---

## 5. Features NOT in v2

| Feature | Reason |
|---------|--------|
| Speed Review / Speed Discovery | Standard table + detail panel is sufficient |
| Discovery page | Link triage is part of Content Map step in wizard |
| Uniqueness Workbench | Replaced by inline verdict + inline expand |
| Score system (0-30) | Replaced by verdict badges with reasoning |
| AgentChatPanel + PilotPromptBar | Dropped — QA reports + Content Map replace their value |
| Context Agent + KB Agent | KB search/chat page is the only chat interface |
| Batch revalidation | Single-file revalidate only |
| Homepage ingestion | Homepage is nav entry point only, not ingested |
