# AI Agents — LLM-Powered Content Processing

**Directory:** `kb_manager/agents/`

All agents use the Strands Agents SDK with AWS Bedrock models. Haiku is used for classification/QA tasks (fast, cheap). Sonnet is used for extraction (higher quality).

---

## 1. Discovery Agent

**File:** `agents/discovery.py`
**Model:** Haiku
**Purpose:** Walk pruned AEM JSON to identify content components and classify discovered links.

### Input
- Pruned AEM JSON (after `aem_pruner.prune_aem_json()`)
- Pre-extracted links (from `extract_links_deterministic()`) — used as ground truth for hallucination defense

### Output: `DiscoveryResult`
```python
@dataclass
class DiscoveryResult:
    components: list[Component]       # id, component_type, title, text_snippet, links
    classified_links: list[ClassifiedLink]  # url, anchor_text, context, classification, reason
```

### Link Classifications
| Classification | Meaning |
|---|---|
| `certain` | Content page worth ingesting |
| `uncertain` | Might be content, needs human review |
| `navigation` | Navigation/utility link, skip |

### Hallucination Defense
The agent receives the pre-extracted link set. Any URL the LLM "discovers" that isn't in the pre-extracted set is flagged and dropped. This prevents the agent from hallucinating URLs that don't exist in the source content.

---

## 2. Extractor Agent

**File:** `agents/extractor.py`
**Model:** Sonnet
**Purpose:** Convert AEM content components into clean markdown files with metadata.

### Input
- List of component dicts (raw pruned AEM JSON per component)
- Optional steering prompt (user-provided guidance)

### Output: `list[ExtractedFile]`
```python
@dataclass
class ExtractedFile:
    title: str
    md_content: str          # Pure markdown, no YAML frontmatter
    source_url: str | None
    content_type: str | None
    region: str | None
    brand: str | None
    category: str | None
    visibility: str | None
    tags: list[str]
```

### Behaviour
- Preserves all text verbatim (no summarisation)
- Converts HTML elements to markdown
- Extracts accordion/tab content
- Derives metadata from content context
- Handles single-dict LLM output (wraps to list via validator)

---

## 3. Link Triage Agent

**File:** `agents/link_triage.py`
**Model:** Haiku
**Purpose:** Deep classification of links that the Discovery Agent couldn't confidently classify.

### Input
- Source context (the card/teaser text where the link was found)
- Linked page's pruned AEM JSON structure

### Output: `TriageResult`
```python
@dataclass
class TriageResult:
    classification: str   # expansion | sibling | navigation | uncertain
    reason: str
    has_sub_links: bool
    sub_link_count: int
```

### Classifications
| Classification | Meaning | Action |
|---|---|---|
| `expansion` | Detail page for a topic on the source page | Merge with parent during extraction |
| `sibling` | Peer page at the same level | Queue for independent processing |
| `navigation` | Navigation/utility link | Skip |
| `uncertain` | Can't determine | Mark needs_confirmation |

---

## 4. QA Agent

**File:** `agents/qa.py`
**Model:** Haiku
**Purpose:** Quality gate — decides whether a markdown file is worth ingesting.

### Input
- Markdown content of the extracted file

### Output: `QAResult.quality_verdict`
```
verdict: "accepted" | "rejected"
reasoning: str (1-3 sentences)
```

### Accept Criteria (ALL must be true)
- Content is coherent and readable as standalone document
- Contains substantive information (product details, policies, how-to, etc.)
- A customer or support agent would gain value from finding this article

### Reject Criteria (ANY triggers rejection)
- Mostly navigation elements, breadcrumbs, or site chrome
- Gibberish, garbled encoding, or placeholder text
- Near-empty stub
- Boilerplate (footers, cookie banners, legal disclaimers)
- Pure listing/index page with only links

---

## 5. Uniqueness Agent

**File:** `agents/qa.py` (same file as QA Agent)
**Model:** Haiku (with tool-use)
**Purpose:** Compare extracted content against existing KB to detect overlap.

### Input
- Markdown content
- Metadata (title, source_url, region, brand)

### Output: `QAResult.uniqueness_verdict`
```
verdict: "unique" | "overlapping" | "conflicting"
reasoning: str
similar_file_ids: list[str]
```

### Verdicts
| Verdict | Meaning |
|---|---|
| `unique` | No significant overlap with existing KB content |
| `overlapping` | Similar content exists but this adds value (different angle, more detail) |
| `conflicting` | Contradicts existing content — needs human review |

### Tool Use
The Uniqueness Agent has access to a Bedrock KB Retrieve tool. It queries the existing knowledge base to find similar documents, then makes its classification based on the results.

---

## 6. Metadata Enricher

**File:** `agents/metadata_enricher.py`
**Model:** Haiku
**Purpose:** Derive rich metadata from raw FAQ/article content (used by Excel import script).

### Input
- Raw content text (from Excel export)

### Output: `EnrichedMetadata`
```python
@dataclass
class EnrichedMetadata:
    title: str              # Clean, concise title (max ~80 chars)
    filename: str           # URL-safe slug for S3 key (max 60 chars)
    brand: str              # avis | budget | avis_budget | unknown
    category: str           # faq | policy | product | service | promotion | help | general
    visibility: str         # public | internal | restricted
    tags: list[str]         # Descriptive tags
```

### Resilience
Uses Strands `structured_output_model` for type-safe extraction, with a JSON-parsing fallback. If the LLM returns malformed JSON, the agent attempts regex-based extraction before failing.

---

## Convenience Function: `run_qa_and_uniqueness()`

**File:** `agents/qa.py`

Runs both QA and Uniqueness agents in sequence and returns a combined `QAResult`. Used by the pipeline and the file revalidation endpoint.

```python
async def run_qa_and_uniqueness(
    md_content: str,
    metadata: dict | None = None,
) -> QAResult:
```
