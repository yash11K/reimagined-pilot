# File Manager — Frontend Implementation Summary

Backend (M1–M6) ships in commit `d68e3cc`. SharePoint-style folder tree, markdown upload, file ops, cascade delete, legacy "Web Sources" surfacing. 149 backend tests green. Frontend is the remaining piece.

Base URL: `/api/v1`. All endpoints JSON unless noted.

---

## 1. Mental model

- **Folder tree = DB only.** S3 key stays attribute-based (`kb_target/brand/region/language/namespace/file.md`). Folder rename costs zero S3 / Bedrock churn.
- **One root per `kb_target`.** `kb_target` set on root, inherited down. Cross-`kb_target` move/copy forbidden (422).
- **Two file origins:**
  - URL-ingested → `folder_id = NULL` → surfaces as virtual **"Web Sources"** bucket.
  - Upload-ingested → `folder_id = <uuid>` → lives in a real folder.
- **Async pipeline.** `POST /files/upload` returns immediately. Enrichment + QA + Uniqueness run in background. Poll `GET /files/{id}` until verdicts populate.
- **Edit propagation rules** (frontend just calls PATCH — backend decides):
  - Key-segment field changed on approved file (`title` / `brand` / `region` / `language`) → S3 key recompute + new sidecar + KB sync.
  - Cosmetic-only edit (`category` / `tags` / `visibility` / `folder_id`) → sidecar resync only.

---

## 2. Endpoint reference

### Folders

| Method | Path | Notes |
|--------|------|-------|
| `POST` | `/folders` | `kb_target` required for root; subfolder inherits |
| `GET`  | `/folders?parent_folder_id=&kb_target=&roots_only=` | Listing |
| `GET`  | `/folders/{id}` | Detail + breadcrumb |
| `GET`  | `/folders/{id}/contents?page=&size=` | Child folders + paginated files |
| `PATCH`| `/folders/{id}` | Rename, change defaults. `kb_target` + parent immutable |
| `DELETE`| `/folders/{id}?cascade=false` | 409 if non-empty |
| `DELETE`| `/folders/{id}?cascade=true`  | Walks subtree, async S3 + single KB sync |

**Status codes to handle:** `404` missing parent/folder, `409` name collision or non-empty delete, `422` kb_target mismatch.

### Files

| Method | Path | Notes |
|--------|------|-------|
| `POST` | `/files/upload` | multipart: `file`, `folder_id`, `title?` |
| `POST` | `/files/{id}/copy` | Body `{folder_id}`. Same kb_target only |
| `GET`  | `/files?folder_id=&unfiled=&status=&brand=&region=&kb_target=&job_id=&source_id=&search=&page=&size=` | List + filters |
| `GET`  | `/files/{id}` | Full detail |
| `PATCH`| `/files/{id}` | Partial metadata + folder move. `folder_id: null` → unfiled |
| `PUT`  | `/files/{id}` | Replace `md_content` |
| `POST` | `/files/{id}/approve` | Body `{reviewed_by, notes?}` → S3 upload + KB sync |
| `POST` | `/files/{id}/reject` | Body `{reviewed_by, notes}` |
| `POST` | `/files/{id}/revalidate` | Re-run QA + Uniqueness |
| `DELETE`| `/files/{id}` | Hard delete |

---

## 3. Response shapes (Pydantic → TS)

```ts
type UUID = string;
type Status = "pending_review" | "approved" | "rejected" | "superseded";
type Verdict = "accepted" | "rejected" | "unique" | "overlapping" | "duplicate";

interface FolderSummary {
  id: UUID; name: string;
  parent_folder_id: UUID | null;
  kb_target: string;
  default_brand: string | null;
  default_region: string | null;
  default_language: string | null;
  created_at: string | null;
  updated_at: string | null;
}

interface FolderDetail extends FolderSummary {
  breadcrumb: { id: UUID; name: string }[];   // root → self
}

interface FolderContents {
  folder: FolderDetail | null;                 // null for root-of-kb_target listing
  child_folders: FolderSummary[];
  files: FolderChildFile[];
  files_total: number;
  files_page: number;
  files_size: number;
  files_pages: number;
}

interface FolderChildFile {
  id: UUID; title: string; status: Status;
  brand: string | null; region: string | null;
  category: string | null; visibility: string | null;
  tags: string[] | null;
  quality_verdict: Verdict | null;
  uniqueness_verdict: Verdict | null;
  s3_key: string | null;
  created_at: string | null;
}

interface FileSummary {
  id: UUID; title: string; status: Status;
  region: string | null; brand: string | null; kb_target: string;
  category: string | null; visibility: string | null;
  tags: string[] | null;
  quality_verdict: Verdict | null;
  uniqueness_verdict: Verdict | null;
  source_url: string | null;                   // "upload://<sha256>/<name>" or http(s)://
  created_at: string;
}

interface FileDetail extends FileSummary {
  md_content: string;
  modify_date: string | null;
  quality_reasoning: string | null;
  uniqueness_reasoning: string | null;
  similar_files: { id: UUID; title: string; source_url: string | null }[];
  s3_key: string | null;
  reviewed_by: string | null;
  review_notes: string | null;
  job_id: UUID;
  sources: { id: UUID; url: string }[];
}

interface UploadResponse {
  file_id: UUID; source_id: UUID; job_id: UUID; folder_id: UUID;
  status: "pending_review";
  title: string;
  deduped: boolean;                            // true → existing Source reused
}
```

---

## 4. Suggested component tree

```
FilesManagerPage (/files)
├── KbTargetSwitcher                 (public | internal)
├── FolderTree (left rail)
│   ├── Lazy children via GET /folders?parent_folder_id=
│   ├── Drop target → PATCH /files/{id} { folder_id }
│   └── "Web Sources" virtual node   (unfiled=true)
├── Breadcrumb                       (FolderDetail.breadcrumb)
├── Toolbar
│   ├── New Folder      → POST /folders
│   ├── Upload          → POST /files/upload
│   └── Bulk actions
├── FileExplorer (main pane)
│   ├── Folder rows  → navigate
│   └── File rows    → status badge, verdicts, click → drawer
├── UploadDropzone (overlay)
│   └── Per-file progress + status badge polled from GET /files/{id}
├── FileDetailDrawer
│   ├── Metadata form  → PATCH /files/{id}
│   ├── Markdown editor → PUT /files/{id}
│   ├── Verdict panel  + Approve / Reject / Revalidate
│   └── Similar files list (FileDetail.similar_files)
└── Dialogs
    ├── CreateFolder / Rename
    ├── MoveFile (folder picker)
    ├── CopyFile (folder picker, same kb_target)
    └── ConfirmDelete (cascade toggle for folder)
```

---

## 5. Key flows

### 5.1 Boot

```ts
// Top-level: one tree per kb_target
GET /folders?roots_only=true&kb_target=public
GET /folders?roots_only=true&kb_target=internal
```

### 5.2 Expand folder node

```ts
GET /folders/{id}                    // breadcrumb + defaults
GET /folders/{id}/contents?page=1&size=50
```

### 5.3 Upload + poll

```ts
const fd = new FormData();
fd.append("file", file);             // .md / .markdown / .txt only, ≤ 10 MB, UTF-8
fd.append("folder_id", folderId);
fd.append("title", titleOverride);   // optional

const { file_id, deduped } = await api.post("/files/upload", fd);

// Poll until QA verdict appears
while (true) {
  const f = await api.get(`/files/${file_id}`);
  if (f.quality_verdict && f.uniqueness_verdict) break;
  await sleep(2500);
}
```

Upload errors to map:
- `400` — unsupported extension / bad UTF-8
- `413` — > 10 MB
- `404` — folder missing
- `409` — title collision in folder (post-enrichment, surfaces on detail)

### 5.4 Move / unfile

```ts
// Move into a folder
PATCH /files/{id}  { folder_id: targetId }

// Send back to Web Sources
PATCH /files/{id}  { folder_id: null }
```

Both are no-S3-key ops on the file content. Backend resyncs sidecar only.

### 5.5 Edit metadata before approve

```ts
PATCH /files/{id} {
  title: "Refueling Policy",
  brand: "avis",
  region: "nam",
  language: "en",
  category: "policy",
  visibility: "public",
  tags: ["fuel", "policy"]
}
```

For an already-approved file, changing `title` / `brand` / `region` / `language` triggers full S3 recompute in background — user sees the new `s3_key` after the next `GET /files/{id}`.

### 5.6 Approve / reject

```ts
POST /files/{id}/approve  { reviewed_by: "alice@x", notes: "looks good" }
POST /files/{id}/reject   { reviewed_by: "alice@x", notes: "wrong region" }
```

### 5.7 Copy

```ts
POST /files/{id}/copy  { folder_id: destId }
// New KBFile, new S3 object, uniqueness_verdict = "overlapping",
// similar_file_ids = [originalId]. Same kb_target only — else 422.
```

### 5.8 Cascade delete folder

```ts
// Preview
GET /folders/{id}/contents

// Execute
DELETE /folders/{id}?cascade=true     // 204; S3 + single KB sync run async
```

---

## 6. UI affordances worth getting right

- **Status badges:** `pending_review` (amber), `approved` (green), `rejected` (red), `superseded` (gray).
- **Verdict pill on row:** show `quality_verdict` + `uniqueness_verdict` next to status — that is the human signal for what to review.
- **Web Sources node** is read-only-ish in tree (no children, no rename, no delete). Files inside CAN be moved into a real folder via PATCH.
- **Folder defaults** (`default_brand` etc.) are applied as priors by the enrichment LLM. Surface them on the folder header so the user knows uploads here will inherit brand=avis without explicit tagging.
- **kb_target switcher** at top — folder tree is rooted per kb_target. Don't let user drag across roots; reject client-side and let the server be the final guard.
- **Cross-kb_target copy/move:** disable drop / hide menu entries when destination root differs.

---

## 7. Polling vs SSE

v1 backend has no SSE/websocket. Frontend polls. Suggested intervals:
- Upload pipeline: 2.5 s up to 60 s, then back off to 10 s.
- KB sync after approve: opportunistic refresh on the file row only when user re-opens it.

---

## 8. Local dev

```bash
cd backend
uv run alembic upgrade head
uv run uvicorn kb_manager.main:app --reload
# Frontend hits http://localhost:8000/api/v1/...
```

Migration `002_folders` adds the `folders` table + `kb_files.folder_id` column. Must run before the server boots or every folder route 500s.

---

## 9. Out of scope (do not build)

- PDF / DOCX / XLSX upload (markdown + txt only in v1).
- File version history UI.
- Per-folder / per-file permissions.
- Cross-kb_target move (server returns 422).
- Bulk drag-folder upload preserving nested structure.
