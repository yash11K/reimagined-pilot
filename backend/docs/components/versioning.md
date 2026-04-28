# Versioning Service — Content Change Detection

**File:** `kb_manager/services/versioning.py`

---

## Overview

The VersioningService compares the `modify_date` of incoming content against existing KB files to decide whether to re-process or skip. When a newer version is detected, the old file is marked as `superseded`.

---

## Class: `VersioningService`

### Method: `check_and_supersede(source_url, new_modify_date, db) -> str`

#### Logic

```
1. Query existing non-superseded KBFiles for this source_url
   (ordered by modify_date DESC)

2. If no existing file found:
   → return "process" (new content)

3. If existing file has same modify_date:
   → return "skip" (unchanged)

4. If new_modify_date is strictly newer:
   → Mark existing file as "superseded"
   → return "process" (updated content)
```

#### Returns
- `"process"` — Create a new KBFile (new or updated content)
- `"skip"` — No changes detected, skip re-processing

---

## Integration with Pipeline

The pipeline calls versioning during the process phase:

```python
# In Pipeline.run_process():
decision = await self._check_versioning_and_cleanup(source.url, modify_date, db)
if decision == "skip":
    # Skip this source entirely
    continue

# If "process", the old file is already marked superseded
# Pipeline also deletes the superseded file's S3 object
```

---

## Why This Matters

Without versioning, re-ingesting the same AEM page would create duplicate KB files. The versioning service ensures:
- Unchanged content is never re-processed (saves LLM costs)
- Updated content replaces the old version cleanly
- Old S3 objects are cleaned up
- The `superseded` status provides an audit trail
