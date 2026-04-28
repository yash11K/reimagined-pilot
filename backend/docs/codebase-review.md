# Codebase Review Report

**Scope:** `kb_manager/` (FastAPI + Strands Agents SDK), `tests/`, `scripts/`, `docs/`
**Date:** 2026-04-27
**Reviewer:** Claude Code (Opus 4.7) per `docs/Claude code review prompt.md`

---

## Executive Summary

**Findings by severity**

| Severity | Count |
|---|---|
| 🔴 Critical | 11 |
| 🟡 Improvement | 18 |
| 🟢 Nice-to-have | 9 |
| **Total** | **38** |

**Top 3 highest-priority items**

1. **The Uniqueness Agent is non-functional.** Its only tool, `query_kb`, is a `TODO` stub returning `[]`. Combined with the system prompt rule "When the KB query returns no results (empty list), always return 'unique'", every uniqueness verdict is hard-coded to `unique`. The "automated dedup" pillar of the business case is silently inert. ([kb_manager/agents/qa.py:149-175](kb_manager/agents/qa.py))
2. **Direct file uploads are silently broken.** `POST /ingest` with `connector_type="upload"` accepts a JSON body and dispatches `_run_upload_process(..., [])` — an empty list — so no file ever reaches the pipeline. The route never receives `multipart/form-data`. ([kb_manager/routes/ingest.py:144-159](kb_manager/routes/ingest.py))
3. **Stateful Strands `Agent` instances are reused across unrelated invocations.** `QAAgent`, `UniquenessAgent`, `ExtractorAgent`, `DiscoveryAgent`, `LinkTriageAgent` each hold a long-lived `strands.Agent` and call `invoke_async()` repeatedly. Strands accumulates conversation history per call, so each subsequent file in a job is processed with the prior file's transcript in context — eroding determinism, inflating token cost and risking context-window exhaustion. `MetadataEnricher` already documents and avoids this; the rest do not. ([kb_manager/agents/qa.py:84-98](kb_manager/agents/qa.py), [kb_manager/agents/qa.py:225-239](kb_manager/agents/qa.py), [kb_manager/services/pipeline.py:451-452](kb_manager/services/pipeline.py))

**Overall assessment**

The codebase is coherent, well-documented, and the pipeline architecture (deterministic prune → LLM discovery with hallucination defense → Strands extraction → routing matrix → S3 + Bedrock sync) is genuinely well-designed for the AEM ingestion problem. The two-phase `run_scout`/`run_process` split, the deterministic link-extraction ground truth, and the routing matrix as a pure function are real strengths.

However, the **business case promises an LLM-powered uniqueness gate** that does not work, **promises direct file uploads** that do not execute, and **promises automated KB sync** that runs on a blocking thread inside the async event loop. The async layer leaks blocking boto3 calls in many places, there is no authentication on any endpoint, CORS is misconfigured for production, and there is no global exception handler. None of these are deep architectural problems — they are concentrated, fixable issues, but they meaningfully reduce the system's "production-ready" claim.

---

## Findings

### Section 1: Agent Orchestration (Strands SDK)

#### [STRANDS] Uniqueness Agent's `query_kb` tool is a stub

| Attribute | Value |
|---|---|
| Severity | 🔴 Critical |
| Effort | Medium (1–3 days) |
| Location | [kb_manager/agents/qa.py:149-175](kb_manager/agents/qa.py) |

**Observation:**
`query_kb` returns `[]` unconditionally. The TODO comment says "Wire to Bedrock KB retrieve API." The Uniqueness Agent's system prompt says "When the KB query returns no results (empty list), always return 'unique'" — so every file is classified `unique` regardless of content.

**Why It Matters:**
The business case explicitly advertises a uniqueness gate that "flags overlaps and conflicts." Today no overlap or conflict can ever be detected. Re-ingesting the same content produces approved duplicates rather than `pending_review`. Section 3.3 of the business case, "Automated Quality Gates," is functionally a no-op for the uniqueness half.

**Recommendation:**
Wire the tool through the existing `BedrockKBClient.retrieve()`:

```python
@tool
def query_kb(content_snippet: str, limit: int = 3) -> list[dict]:
    settings = get_settings()
    if not settings.BEDROCK_KB_ID:
        return []
    from kb_manager.services.bedrock_kb import BedrockKBClient
    client = BedrockKBClient()
    raw = client.retrieve(content_snippet, limit=limit)
    return [
        {"file_id": r.get("s3_uri", ""), "title": r["title"],
         "score": r["score"], "snippet": r["snippet"][:500],
         "source_url": r["source_url"]}
        for r in raw
    ]
```

Also wrap with `asyncio.to_thread` if Strands invokes tools synchronously inside an async loop (boto3 is blocking). Confirm the file_id contract used by the Uniqueness prompt's `similar_file_ids` matches what `retrieve()` returns — at present the prompt requests UUIDs but Bedrock returns S3 URIs, which then fail `uuid.UUID(sid)` in [pipeline.py:749](kb_manager/services/pipeline.py).

---

#### [STRANDS] Strands `Agent` instances are reused across unrelated invocations — conversation history leaks between files

| Attribute | Value |
|---|---|
| Severity | 🔴 Critical |
| Effort | Low (< 1 day) |
| Location | [kb_manager/agents/qa.py:94-97](kb_manager/agents/qa.py), [kb_manager/agents/qa.py:235-239](kb_manager/agents/qa.py), [kb_manager/agents/discovery.py:167-170](kb_manager/agents/discovery.py), [kb_manager/agents/extractor.py:125-128](kb_manager/agents/extractor.py), [kb_manager/agents/link_triage.py:77-80](kb_manager/agents/link_triage.py), [kb_manager/services/pipeline.py:450-452](kb_manager/services/pipeline.py), [kb_manager/services/pipeline.py:559-560](kb_manager/services/pipeline.py) |

**Observation:**
Each agent class stores a single `strands.Agent` in `self._agent` at init time. `Pipeline.run_process` builds one `QAAgent` and one `UniquenessAgent`, then passes them through `_process_single_file` for **every** extracted file in the job (the upload path does the same). Strands' agent loop accumulates messages on every `invoke_async` (see [Strands docs: Agent Loop §3](https://strandsagents.com/docs/user-guide/concepts/agents/agent-loop/index.md)). Without an explicit conversation manager, history grows unbounded across files; with the default sliding window, history still bleeds the previous file's content into the next file's QA judgement.

`MetadataEnricher` (`agents/metadata_enricher.py:137-146`) already documents this exact failure mode and rebuilds the agent per call. The other five agents do not.

**Why It Matters:**
- Determinism: file N's QA verdict depends on files 1..N-1 in the same run, which is invisible to anyone looking at the verdict-and-reasoning columns. Two identical files in different positions will get different verdicts.
- Cost: each subsequent file pays for the previous file's tokens in the input window.
- Reliability: large jobs will eventually hit `MaxTokensReachedException` (Strands "Common Problems" section).

**Recommendation:**
Either (a) build a fresh `Agent` per `run()` invocation (pattern from `MetadataEnricher`), or (b) call `self._agent.messages.clear()` at the start of `run()`. Option (a) is simpler and matches Strands' "decompose into subtasks with fresh context" guidance:

```python
class QAAgent:
    def __init__(self) -> None:
        settings = get_settings()
        self._model_id = settings.HAIKU_MODEL_ID
        self._max_tokens = settings.HAIKU_MAX_TOKENS

    def _build_agent(self) -> Agent:
        return Agent(
            model=BedrockModel(model_id=self._model_id, max_tokens=self._max_tokens),
            system_prompt=QA_SYSTEM_PROMPT,
        )

    async def run(self, md_content: str, metadata=None) -> QAOutput:
        agent = self._build_agent()
        result = await agent.invoke_async(prompt, structured_output_model=QAOutput)
        ...
```

---

#### [STRANDS] Direct file uploads pass an empty list to the pipeline

| Attribute | Value |
|---|---|
| Severity | 🔴 Critical |
| Effort | Medium (1–3 days) |
| Location | [kb_manager/routes/ingest.py:144-159](kb_manager/routes/ingest.py), [kb_manager/services/pipeline.py:542-546](kb_manager/services/pipeline.py) |

**Observation:**
`POST /ingest` declares `ingest_request: IngestRequest` (a JSON body). When `connector_type="upload"`, the handler dispatches `_run_upload_process(request, job.id, [])`. There is no `UploadFile` parameter on the route, no `multipart/form-data` consumption, and no `files` field on `IngestRequest`. `Pipeline.run_upload_process` then iterates the empty list and finalises the job with zero files.

**Why It Matters:**
The business case markets manual markdown uploads as one of three content sources. Documentation in `docs/logic-flow.md §3` describes the full flow. Today the endpoint silently returns 202 and produces nothing. There is no test covering this path (`tests/test_pipeline.py` doesn't exercise `run_upload_process`).

**Recommendation:**
Either remove the upload code path entirely or wire it. To wire:
1. Split into two endpoints: `POST /ingest` (JSON, AEM only) and `POST /ingest/upload` accepting `files: list[UploadFile] = File(...)` plus form fields.
2. In the upload route, read each file's bytes synchronously before scheduling the background task — `UploadFile` objects don't survive past the request lifecycle.
3. Pass the in-memory file payloads into `Pipeline.run_upload_process(job_id, files: list[tuple[str, bytes]])` and refactor the method to use `(filename, content_bytes)` tuples instead of `UploadFile`.

---

#### [STRANDS] QA and Uniqueness run sequentially when they could run concurrently

| Attribute | Value |
|---|---|
| Severity | 🟡 Improvement |
| Effort | Low (< 1 day) |
| Location | [kb_manager/agents/qa.py:298-299](kb_manager/agents/qa.py) |

**Observation:**
`run_qa_and_uniqueness` awaits `qa.run(...)` then awaits `uq.run(...)`. The two agents take the same input (`md_content`, `metadata`) and have no data dependency — uniqueness does not consume the QA verdict.

**Why It Matters:**
On Haiku each call is ~1–3s. Running them concurrently halves per-file latency. With ~500 Excel rows or hundreds of AEM pages this compounds.

**Recommendation:**
```python
qa_task = asyncio.create_task(qa.run(md_content, metadata=metadata))
uq_task = asyncio.create_task(uq.run(md_content, metadata=metadata))
qa_output, uq_output = await asyncio.gather(qa_task, uq_task)
```

---

#### [STRANDS] Discovery/Link-Triage prompt sends the entire pruned JSON as a single blob

| Attribute | Value |
|---|---|
| Severity | 🟡 Improvement |
| Effort | Medium (1–3 days) |
| Location | [kb_manager/agents/discovery.py:200-205](kb_manager/agents/discovery.py), [kb_manager/agents/link_triage.py:86-90](kb_manager/agents/link_triage.py) |

**Observation:**
The Discovery Agent receives `json.dumps(pruned_json, indent=2)` — even after pruning, an AEM page's component tree is large (often 30–80KB). Combined with the pre-extracted-link list, the prompt routinely runs 50K+ chars. Haiku's `max_tokens` is configured at 8192 (output), but the input cost is per-call.

**Why It Matters:**
The pruner is doing its job at a structural level (drops chrome) but the resulting tree still contains every text field, every nested `:items` mapping, every `id`. The Discovery Agent only needs (a) the link contexts (which the pre-extracted list already supplies) and (b) the components' titles and snippets to populate `Component.text_snippet`. Sending the raw tree wastes tokens and inflates cost on every scout.

**Recommendation:**
Have the deterministic pruner emit a **component digest** alongside the links — a flat list of `{id, type, title, text_snippet[:200], links}` extracted from the same walk. Pass that digest to Discovery instead of `json.dumps(pruned)`. This also removes the agent's burden of "walking `:items` recursively," which currently forms half the system prompt.

---

#### [STRANDS] Tool description on `query_kb` does not match prompt expectations

| Attribute | Value |
|---|---|
| Severity | 🟡 Improvement |
| Effort | Low (< 1 day) |
| Location | [kb_manager/agents/qa.py:149-175](kb_manager/agents/qa.py) |

**Observation:**
The tool's docstring promises return keys `file_id, title, score, snippet`. The system prompt at [qa.py:209-210](kb_manager/agents/qa.py) says "you MUST list the file_ids of the conflicting documents in `similar_file_ids`". Today even after wiring, the natural `file_id` from Bedrock retrieval is an S3 URI — but [pipeline.py:749](kb_manager/services/pipeline.py) tries `uuid.UUID(sid)` on those values, which will throw.

**Why It Matters:**
Once the stub is replaced (finding above), the next bug surfaces immediately: the Pipeline will crash inside `_process_single_file` because S3 URIs are not UUIDs. The contract between tool, prompt, and pipeline isn't agreed upon.

**Recommendation:**
Pick one canonical identifier and use it everywhere. Easiest: store the `kb_files.id` (UUID) in the Bedrock metadata sidecar (`S3Uploader._build_metadata_document`) and have `query_kb` read that field back from `retrieve()`'s `metadata` dict. Then `similar_file_ids` are real DB UUIDs the routing/review UI can dereference.

---

#### [STRANDS] Hallucination defense is silently undermined by the "fallback uncertain" branch

| Attribute | Value |
|---|---|
| Severity | 🟡 Improvement |
| Effort | Low (< 1 day) |
| Location | [kb_manager/agents/discovery.py:274-292](kb_manager/agents/discovery.py) |

**Observation:**
When the agent skips a pre-extracted link, the code adds it back as `classification="uncertain"` with reason "Not classified by agent — added as fallback". Every such fallback creates a `needs_confirmation` source for a human to review. On a typical AEM page the agent often misses 5–10 links from a list of 30+, generating an avalanche of human-review tickets for what may be navigation links.

**Why It Matters:**
The UI promises uncertain links are "links that might be content, needs human review." The fallback bucket pollutes that meaning with "links the LLM ignored." Reviewers either rubber-stamp them (eroding trust) or drown.

**Recommendation:**
Either (a) re-prompt the agent specifically for the missed links (cheaper, more accurate), or (b) classify fallbacks as `navigation` with reason "agent omitted — defaulting to skip" — safer because the user can still find the source via `denied_navigation` if they look.

---

#### [STRANDS] Per-job agent re-instantiation costs add up

| Attribute | Value |
|---|---|
| Severity | 🟢 Nice-to-have |
| Effort | Low (< 1 day) |
| Location | [kb_manager/services/pipeline.py:143-144](kb_manager/services/pipeline.py), [kb_manager/services/pipeline.py:450-452](kb_manager/services/pipeline.py) |

**Observation:**
`Pipeline.run_scout` instantiates `DiscoveryAgent()`. `Pipeline.run_process` instantiates `ExtractorAgent`, `QAAgent`, `UniquenessAgent`. Every instantiation builds a fresh `BedrockModel`, which builds a boto3 client. With `MAX_CONCURRENT_JOBS=3` and queue churn, each item pays this cost.

**Why It Matters:**
Once the per-call agent rebuild (recommendation above) lands, the per-job class instances become trivial caches around `BedrockModel`. A single `BedrockModel` per process, shared by all agent invocations, is cheap and obvious. boto3 clients are thread-safe for the operations used here.

**Recommendation:**
Hold one `BedrockModel` (Haiku) and one `BedrockModel` (Sonnet) on the `Pipeline` and have agent classes accept a model in their constructor. Init cost moves from per-job to once.

---

#### [STRANDS] `link_triage` agent is defined but never invoked

| Attribute | Value |
|---|---|
| Severity | 🟢 Nice-to-have |
| Effort | Low (< 1 day) |
| Location | [kb_manager/agents/link_triage.py](kb_manager/agents/link_triage.py), [kb_manager/services/pipeline.py](kb_manager/services/pipeline.py) |

**Observation:**
`LinkTriageAgent` is exported from `agents/__init__.py` and documented in `docs/components/agents.md §3`. No code path in `pipeline.py`, routes, or services calls it.

**Why It Matters:**
Documentation drift — the agent's purpose ("expansion vs sibling vs navigation") is unreachable. Either it's vestigial and should be removed, or it's the missing piece that should run between Discovery's `uncertain` classification and the `needs_confirmation` source — which would dramatically reduce manual review load.

**Recommendation:**
Decide: delete or wire it. If wiring, run it in `run_scout` for each `uncertain` link (with a fetch + prune of the linked page) before deciding `needs_confirmation` vs `auto-queue`. If deleting, remove the file, doc, and exports.

---

#### [STRANDS] `_extract_modify_date` walks `jcr:content` once per top-level key

| Attribute | Value |
|---|---|
| Severity | 🟢 Nice-to-have |
| Effort | Low (< 1 day) |
| Location | [kb_manager/services/pipeline.py:632-649](kb_manager/services/pipeline.py) |

**Observation:**
The inner `aem_json.get("jcr:content", {})` lookup is inside the for-loop over the three key candidates, so the same dict is fetched three times.

**Why It Matters:**
Cosmetic/perf-only. The function reads odd at first glance.

**Recommendation:**
Lift the `jcr` lookup outside the loop and iterate against both dicts.

---

### Section 2: Python Best Practices

#### [PY-ASYNC] Blocking boto3 calls inside async functions starve the event loop

| Attribute | Value |
|---|---|
| Severity | 🔴 Critical |
| Effort | Low (< 1 day) |
| Location | [kb_manager/services/s3_uploader.py:119-198](kb_manager/services/s3_uploader.py), [kb_manager/services/bedrock_kb.py:41-201](kb_manager/services/bedrock_kb.py), [kb_manager/services/pipeline.py:96-101](kb_manager/services/pipeline.py), [kb_manager/services/pipeline.py:668](kb_manager/services/pipeline.py), [kb_manager/services/pipeline.py:768](kb_manager/services/pipeline.py), [kb_manager/routes/files.py:44](kb_manager/routes/files.py), [kb_manager/routes/files.py:53](kb_manager/routes/files.py), [kb_manager/routes/kb.py:42](kb_manager/routes/kb.py), [kb_manager/routes/kb.py:70](kb_manager/routes/kb.py) |

**Observation:**
`S3Uploader.upload`, `S3Uploader.delete`, `BedrockKBClient.retrieve`, `BedrockKBClient.retrieve_and_generate`, `BedrockKBClient.start_sync` are all synchronous boto3 calls. They are awaited from async pipeline code and async routes (`Pipeline._process_single_file`, `Pipeline._check_versioning_and_cleanup`, `Pipeline._trigger_kb_sync`, `routes/kb.py`'s SSE generators) without `asyncio.to_thread`.

**Why It Matters:**
With `MAX_CONCURRENT_JOBS=3` the worker pool has three slots, but the entire event loop is one thread. While item A is uploading to S3 (network-blocking inside `put_object`), items B and C also stop progressing — heartbeats can't fire, SSE streams can't push, FastAPI can't respond to HTTP. Bedrock `retrieve_and_generate` is even worse — it commonly takes 5–15 seconds. SSE consumers see no events until the call returns.

**Recommendation:**
Wrap every boto3 call in `await asyncio.to_thread(...)`. Or migrate to `aioboto3`. Concrete edit, e.g. for `S3Uploader.upload`:

```python
async def upload(self, file: KBFile) -> str | None:
    ...
    await asyncio.to_thread(
        self._client.put_object,
        Bucket=self._bucket, Key=s3_key,
        Body=file.md_content.encode("utf-8"),
        ContentType="text/markdown; charset=utf-8",
    )
    ...
```

Then call sites become `s3_key = await s3_uploader.upload(kb_file)` — they already `await` so this is a small surface change.

---

#### [PY-ASYNC] CORS configured with `allow_origins=["*"]` and `allow_credentials=True`

| Attribute | Value |
|---|---|
| Severity | 🔴 Critical |
| Effort | Low (< 1 day) |
| Location | [kb_manager/main.py:101-108](kb_manager/main.py) |

**Observation:**
The CORS middleware is configured with the wildcard origin and credentials enabled. Browsers reject this combination per the CORS spec; either credentials silently fail or the request is blocked depending on the browser.

**Why It Matters:**
- Functional: any frontend that needs cookies/auth headers will fail in unexpected, browser-specific ways.
- Security: when this combination *does* work (older browsers, non-browser clients), it lets any origin make credentialed requests. The system has no auth today, but when added this becomes immediately exploitable.

**Recommendation:**
Drive CORS from configuration, listing explicit origins:
```python
class Settings(BaseSettings):
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]
...
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

#### [PY-ASYNC] No global exception handler — stack traces leak in 500 responses

| Attribute | Value |
|---|---|
| Severity | 🔴 Critical |
| Effort | Low (< 1 day) |
| Location | [kb_manager/main.py](kb_manager/main.py) (missing) |

**Observation:**
`create_app` registers CORS, a request-logging middleware, and the route routers — no `app.add_exception_handler(...)` for `Exception`, `ValueError`, `IntegrityError`, etc. Any unhandled exception bubbles to FastAPI's default handler, which returns the exception's repr.

**Why It Matters:**
Internal stack traces (file paths, query fragments, `os.environ` keys in some libraries) reach API consumers. There is no consistent error envelope (`{ "error": "...", "request_id": "..." }`) so frontends have to handle ad-hoc error shapes.

**Recommendation:**
```python
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "detail": "An unexpected error occurred."},
    )
```
Plus a domain-specific handler for `IntegrityError`, `httpx.RequestError`, `botocore.exceptions.ClientError`, etc.

---

#### [PY-ASYNC] No authentication or authorization on any endpoint

| Attribute | Value |
|---|---|
| Severity | 🔴 Critical |
| Effort | High (3+ days) |
| Location | All routes under `kb_manager/routes/` |

**Observation:**
Every route is open. `POST /ingest`, `POST /queue`, `DELETE /sources/{id}`, `DELETE /files/{id}`, `POST /kb/sync`, `POST /kb/chat` (which costs Bedrock dollars per call) — none require an API key, JWT, or any auth dependency.

**Why It Matters:**
The system is meant for internal ABG content ops. Anyone with network access can trigger ingestion of arbitrary URLs, drain the Bedrock budget via `kb/chat`, or delete any KB file. There is no audit trail beyond `reviewed_by` strings the client supplies (and which are not validated).

**Recommendation:**
Pick a minimum bar (API key in header, IAM SigV4, or OIDC/JWT through a corporate IdP) and apply via a FastAPI dependency on every router include:
```python
app.include_router(ingest_router, prefix="/api/v1", dependencies=[Depends(require_auth)])
```
For destructive operations (`DELETE`, `POST /kb/sync`), require an additional role check.

---

#### [PY-ASYNC] `_process_single_file` exception branch uses `dir()` instead of `locals()` — silently never recovers

| Attribute | Value |
|---|---|
| Severity | 🟡 Improvement |
| Effort | Low (< 1 day) |
| Location | [kb_manager/services/pipeline.py:777](kb_manager/services/pipeline.py) |

**Observation:**
```python
if "kb_file" in dir() and kb_file:
    await file_queries.update_file(...)
```
`dir()` returns the names visible in the *enclosing module/class scope*, not the function's locals. The variable `kb_file` is a function-local; this check returns `False` for the function-local. Compounding the bug, even if it returned True, `kb_file` may have been mutated mid-function (`kb_file = await file_queries.get_file(...)` at line 766 reassigns to potentially `None`).

**Why It Matters:**
The intent is "if we managed to create the KBFile before the failure, mark it rejected so the user sees what happened." Today that recovery never runs — failures leave files in `pending_review` with no `quality_reasoning`.

**Recommendation:**
Refactor to use a sentinel and check directly:
```python
kb_file = None
try:
    kb_file = await file_queries.create_file(...)
    ...
except Exception as exc:
    if kb_file is not None:
        await file_queries.update_file(
            db, kb_file.id, status="rejected",
            quality_reasoning=f"Processing error: {exc}",
        )
    ...
```

---

#### [PY-ASYNC] `Pipeline._trigger_kb_sync` is called synchronously from async paths

| Attribute | Value |
|---|---|
| Severity | 🟡 Improvement |
| Effort | Low (< 1 day) |
| Location | [kb_manager/services/pipeline.py:93-101](kb_manager/services/pipeline.py), [kb_manager/services/pipeline.py:527](kb_manager/services/pipeline.py), [kb_manager/services/pipeline.py:622](kb_manager/services/pipeline.py) |

**Observation:**
`_trigger_kb_sync` calls `client.start_sync()` (sync boto3) directly from `run_process` and `run_upload_process` — both async. The call is fire-and-forget but still blocks the event loop while it round-trips to Bedrock.

**Why It Matters:**
Same event-loop starvation as the boto3 finding above, but specifically affects the moment a job completes — the worker can't pick up the next item until the sync call returns.

**Recommendation:**
Make it `async def _trigger_kb_sync(...)` and `await asyncio.to_thread(client.start_sync)` — or schedule it via `asyncio.create_task(...)` and let it run independently.

---

#### [PY-ASYNC] Pydantic models mix `Optional[X]` and `X | None`; some validators absent

| Attribute | Value |
|---|---|
| Severity | 🟢 Nice-to-have |
| Effort | Low (< 1 day) |
| Location | [kb_manager/agents/discovery.py:24](kb_manager/agents/discovery.py), [kb_manager/agents/extractor.py:25](kb_manager/agents/extractor.py), most other Pydantic models use `X | None` |

**Observation:**
`agents/discovery.py` and `agents/extractor.py` import `Optional` from `typing` and use `Optional[str]`, while `schemas/*.py` and most other modules use the modern `X | None` syntax (Python 3.10+). The codebase targets Python 3.12.

**Why It Matters:**
Cosmetic, but it suggests these files were written earlier and not updated. Mixing styles makes review noisier.

**Recommendation:**
Sweep `Optional[X]` → `X | None` and remove the unused `Optional` imports.

---

#### [PY-ASYNC] `IngestRequest.urls` allowed `None` despite being required for AEM

| Attribute | Value |
|---|---|
| Severity | 🟡 Improvement |
| Effort | Low (< 1 day) |
| Location | [kb_manager/schemas/ingest.py:24](kb_manager/schemas/ingest.py), [kb_manager/routes/ingest.py:103-104](kb_manager/routes/ingest.py) |

**Observation:**
`IngestRequest.urls: list[AemUrlInput] | None = None`. The route then enforces `urls required` for `connector_type=aem` via a manual `HTTPException(422)`. Pydantic v2 supports discriminated unions or `model_validator` for this directly.

**Why It Matters:**
Validation logic that lives in Pydantic is automatically reflected in OpenAPI / docs and is enforced before route code runs. Today, manual checks are easy to forget when adding `connector_type` variants.

**Recommendation:**
```python
class AEMIngestRequest(BaseModel):
    connector_type: Literal["aem"]
    urls: list[AemUrlInput] = Field(min_length=1)
    kb_target: Literal["public", "internal"]
    steering_prompt: str | None = None

class UploadIngestRequest(BaseModel):
    connector_type: Literal["upload"]
    kb_target: Literal["public", "internal"]
    steering_prompt: str | None = None

IngestRequest = Annotated[
    Union[AEMIngestRequest, UploadIngestRequest],
    Field(discriminator="connector_type"),
]
```

---

#### [PY-ASYNC] Settings: hardcoded model IDs across modules instead of via DI

| Attribute | Value |
|---|---|
| Severity | 🟢 Nice-to-have |
| Effort | Low (< 1 day) |
| Location | every agent calls `get_settings()` directly during `__init__` |

**Observation:**
Each `__init__` calls `get_settings()` and reads model ids — fine that the values come from settings, but it makes testing awkward (must monkey-patch settings) and creates implicit coupling.

**Why It Matters:**
Existing tests in `tests/test_pipeline.py` work around this by patching the agent classes. A small change makes mocking and per-test config trivial.

**Recommendation:**
Pass models as constructor args from `Pipeline`, which already holds `settings`:
```python
class QAAgent:
    def __init__(self, model: BedrockModel) -> None:
        ...
```

---

#### [PY-ASYNC] `_get_kb_client` lazy-init has a TOCTOU race

| Attribute | Value |
|---|---|
| Severity | 🟢 Nice-to-have |
| Effort | Low (< 1 day) |
| Location | [kb_manager/services/pipeline.py:87-91](kb_manager/services/pipeline.py), [kb_manager/routes/kb.py:17-23](kb_manager/routes/kb.py) |

**Observation:**
`Pipeline._get_kb_client` and `routes/kb.py._get_client` both lazy-initialise a global without a lock. With `MAX_CONCURRENT_JOBS=3` two completion events can call `_trigger_kb_sync` simultaneously and instantiate two `BedrockKBClient` objects. boto3 clients are not absurdly heavy but this is wasteful.

**Why It Matters:**
Edge case. Doesn't break anything, but reads as "deferred for later" code.

**Recommendation:**
Initialise once during `lifespan()` in `main.py` and pass through `app.state` like `s3_uploader` already is.

---

#### [DB] `KBFile.job_id` foreign key has no `ON DELETE CASCADE`

| Attribute | Value |
|---|---|
| Severity | 🟡 Improvement |
| Effort | Low (< 1 day) |
| Location | [kb_manager/models.py:150-152](kb_manager/models.py), Alembic migrations |

**Observation:**
The `source_kb_files` junction has `ondelete="CASCADE"` on both sides. `KBFile.job_id` and `IngestionJob.source_id` do not declare cascade behavior. Deleting a job leaves orphan files; deleting a source via [routes/sources.py:227-254](kb_manager/routes/sources.py) only works because the route deletes files manually first.

**Why It Matters:**
The route's manual cleanup is fragile — if it crashes mid-loop, the `delete_source` at the end will fail with FK violation, but some files are already deleted from DB. Inconsistent state.

**Recommendation:**
Add a migration: `ALTER TABLE kb_files DROP CONSTRAINT ... ADD CONSTRAINT ... FOREIGN KEY (job_id) REFERENCES ingestion_jobs(id) ON DELETE CASCADE;` and the same for jobs→sources. Then collapse the route to a single `delete_source` call and let Postgres do the work.

---

#### [DB] Frequent `ILIKE '%term%'` on title/url with no GIN/trigram index

| Attribute | Value |
|---|---|
| Severity | 🟡 Improvement |
| Effort | Medium (1–3 days) |
| Location | [kb_manager/queries/files.py:103-106](kb_manager/queries/files.py), [kb_manager/queries/sources.py:102-105](kb_manager/queries/sources.py), [kb_manager/queries/search.py:25-30](kb_manager/queries/search.py) |

**Observation:**
Every list endpoint and the global search use `ILIKE '%q%'` patterns. There is no `pg_trgm` extension or GIN index. With ~500 Decagon rows this is fine; at 10K+ files it will degrade.

**Why It Matters:**
Now: not a problem. After Decagon import scales up: any list page with a `search=` filter will table-scan.

**Recommendation:**
Migration: `CREATE EXTENSION IF NOT EXISTS pg_trgm;` then `CREATE INDEX ix_kb_files_title_trgm ON kb_files USING gin (title gin_trgm_ops);` for title and source_url. Cheap to add now.

---

#### [DB] Stats endpoint runs eight separate `SELECT count(*)` queries

| Attribute | Value |
|---|---|
| Severity | 🟢 Nice-to-have |
| Effort | Low (< 1 day) |
| Location | [kb_manager/routes/stats.py:30-95](kb_manager/routes/stats.py) |

**Observation:**
`/stats` issues eight independent COUNT queries — total files, pending, approved, rejected, public, internal, active jobs, failed jobs, etc. Each is a round-trip.

**Why It Matters:**
Dashboard endpoint hit on every page load. On a large DB the cumulative latency hurts UI responsiveness.

**Recommendation:**
Combine into two queries with `FILTER` clauses:
```python
files_stats = await db.execute(
    select(
        func.count().label("total"),
        func.count().filter(KBFile.status == "pending_review").label("pending"),
        func.count().filter(KBFile.status == "approved").label("approved"),
        ...
    ).select_from(KBFile)
)
```

---

#### [DB] `count_files_by_status` runs four queries instead of one GROUP BY

| Attribute | Value |
|---|---|
| Severity | 🟢 Nice-to-have |
| Effort | Low (< 1 day) |
| Location | [kb_manager/queries/files.py:147-167](kb_manager/queries/files.py) |

**Observation:**
Four separate counts joined through the junction table. A `GROUP BY status` returns the same in one round-trip.

**Recommendation:**
```python
result = await db.execute(
    select(KBFile.status, func.count())
    .select_from(KBFile)
    .join(source_kb_files, ...)
    .where(source_kb_files.c.source_id == source_id)
    .group_by(KBFile.status)
)
counts = {row[0]: row[1] for row in result}
return {"total": sum(counts.values()), "approved": counts.get("approved", 0), ...}
```

---

#### [LOGGING] No structured logging or correlation ID propagation

| Attribute | Value |
|---|---|
| Severity | 🟡 Improvement |
| Effort | Medium (1–3 days) |
| Location | [kb_manager/main.py:31-47](kb_manager/main.py), all log call sites |

**Observation:**
Logging uses Python `logging` with `%`-format strings. Job IDs and worker IDs are encoded as decorative prefixes (`[w0][queue=abc...]`). There is no JSON logger, no request-id middleware, no `contextvars`-based correlation.

**Why It Matters:**
Debugging a failed ingestion across `main.py` (HTTP middleware) → `pipeline.py` (scout) → `agents/qa.py` (Strands invocation) → `s3_uploader.py` (upload) means grepping by `job_id_str[:8]`. Strands SDK logs and httpx logs don't include the job id at all.

**Recommendation:**
Adopt `structlog` + `contextvars`. At request entry generate a request_id; at job creation bind `job_id`. All downstream logs automatically include both. Output JSON in production.

---

#### [SEC] Path traversal risk in `S3Uploader.upload`

| Attribute | Value |
|---|---|
| Severity | 🟡 Improvement |
| Effort | Low (< 1 day) |
| Location | [kb_manager/services/s3_uploader.py:128-147](kb_manager/services/s3_uploader.py) |

**Observation:**
`namespace = file.source_url.rstrip("/").rsplit("/", 1)[-1]` — `source_url` is LLM-derived. If the LLM emits e.g. `"foo/../../../etc/passwd"`, the namespace becomes `passwd`. The brand and region also flow from LLM/agent output. `build_s3_key` strips slashes per-segment but does not sanitize parent directory traversal.

**Why It Matters:**
S3 keys can contain `..` literally; that's not a privilege issue inside an S3 bucket (no parent directory concept), but the resulting keys can collide with operator-created keys and be hard to enumerate. With Bedrock indexing, malformed keys also break filter logic.

**Recommendation:**
Sanitize all five segments through a single regex `[^a-zA-Z0-9_-]` → `-`, drop empty segments, cap each at 60 chars. Add a guard rejecting `..` outright.

---

#### [PY-ASYNC] StreamManager subscriber list mutated from multiple coroutines without lock

| Attribute | Value |
|---|---|
| Severity | 🟡 Improvement |
| Effort | Low (< 1 day) |
| Location | [kb_manager/services/stream_manager.py:29-71](kb_manager/services/stream_manager.py), [kb_manager/routes/ingest.py:32-71](kb_manager/routes/ingest.py) |

**Observation:**
`_channels: dict[..., list[asyncio.Queue]]` is mutated from multiple coroutines. Routes (in `ingest.py:42`) bypass `StreamManager.subscribe()` and append to the underlying list directly. Single event-loop ⇒ no true race, but ordering is fragile and the intent is unclear.

Worse, `publish_event` iterates `self._event_subscribers` after copying via `list(...)`, but the mutation pattern in `add_event_subscriber`/`remove_event_subscriber` uses `list.append` and `list.remove`. If a subscriber's queue raises `QueueFull` during `put_nowait`, the message is silently dropped — the SSE consumer just misses an event.

**Why It Matters:**
SSE clients silently lose updates when the global stream burst fills `Queue(maxsize=256)`. UI shows stale state.

**Recommendation:**
- Have `routes/ingest.py` use `StreamManager.subscribe()` rather than touch private attrs.
- On `QueueFull`, drop the slowest subscriber rather than silently discard the event for everyone (or use unbounded queues with periodic monitoring).
- Add `weakref.finalize` to remove subscribers when the underlying coroutine finishes.

---

#### [PY-ASYNC] Background tasks via `BackgroundTasks` for long work prevent graceful shutdown

| Attribute | Value |
|---|---|
| Severity | 🟡 Improvement |
| Effort | Medium (1–3 days) |
| Location | [kb_manager/routes/ingest.py:140-142](kb_manager/routes/ingest.py), [kb_manager/routes/sources.py:213-217](kb_manager/routes/sources.py) |

**Observation:**
`POST /ingest` and `POST /sources/{id}/confirm` schedule the entire scout+process pipeline via `BackgroundTasks`, which runs after the response is sent but is tracked by the request context, not the worker. On shutdown, FastAPI awaits these tasks but cancellation is not graceful — the pipeline may be in the middle of an LLM call.

**Why It Matters:**
The queue worker has a clean lifecycle (`worker.stop()` cancels everything). The background-task path doesn't. In production a deploy mid-job leaves the job in `processing` state and only the stale-sweep recovers it.

**Recommendation:**
Route these two endpoints through the queue (`queue_queries.add_to_queue`) rather than `BackgroundTasks`. The user already has the queue worker for orchestration; using `BackgroundTasks` for the same work duplicates the lifecycle story.

---

### Section 3: API Design

#### [API] No API versioning strategy beyond `/v1` prefix; no documented contract for breaking changes

| Attribute | Value |
|---|---|
| Severity | 🟢 Nice-to-have |
| Effort | Low (< 1 day) |
| Location | [kb_manager/main.py:131-141](kb_manager/main.py) |

**Observation:**
All routes are mounted under `/api/v1`. There is no `/v2` plan, no deprecation header, no versioning policy in `docs/`.

**Why It Matters:**
Frontend (`apps/frontend`) imports endpoints as constants. When something has to change shape, the team has to coordinate or break the UI. Documented strategy ("add v2, support v1 for 90 days, deprecate via Sunset header") avoids cliff-edge migrations.

**Recommendation:**
Add a section to `docs/architecture.md` describing the policy. Until v2 exists this is purely documentation.

---

#### [API] `POST /kb/search` and `POST /kb/chat` use SSE but Bedrock RetrieveAndGenerate is non-streaming

| Attribute | Value |
|---|---|
| Severity | 🟡 Improvement |
| Effort | Low (< 1 day) |
| Location | [kb_manager/routes/kb.py:32-92](kb_manager/routes/kb.py), [kb_manager/services/bedrock_kb.py:100-171](kb_manager/services/bedrock_kb.py) |

**Observation:**
`_chat_sse_generator` calls the blocking `retrieve_and_generate`, gets back the full text, then chunks it into 200-char fake "tokens" before yielding SSE events. The user perceives streaming, but the backend is not actually streaming.

**Why It Matters:**
- Latency: the user sees nothing for 5–15s while RAG completes, then a flood of fake tokens.
- Misleading API: clients write streaming consumers thinking the backend supports it; this prevents future "real" streaming without breaking changes.

**Recommendation:**
Either (a) use Bedrock's `invoke_model_with_response_stream` for the generation half (Strands SDK supports streaming) and emit real tokens, or (b) drop the SSE wrapping and return JSON directly. Option (a) is the better UX; (b) is honest about what's happening.

---

#### [API] `DELETE` operations return 204 but background S3 cleanup may fail silently

| Attribute | Value |
|---|---|
| Severity | 🟡 Improvement |
| Effort | Low (< 1 day) |
| Location | [kb_manager/routes/files.py:386-394](kb_manager/routes/files.py), [kb_manager/routes/sources.py:257-266](kb_manager/routes/sources.py) |

**Observation:**
`_delete_s3_file` swallows exceptions silently. The DB row is deleted before S3 cleanup runs. If S3 fails, the file is unreachable from the API but still occupies the bucket and (worse) is still in Bedrock's index until the next sync.

Also: `_delete_s3_file` calls `delete(s3_key)` then `delete(s3_key + ".metadata.json")`. But `S3Uploader.delete` already cascades to the metadata sidecar — so the metadata gets deleted, then a 404 is logged when the second delete fails on the now-missing key. Spurious noise.

**Why It Matters:**
Cost (orphaned S3 objects) + correctness (Bedrock returns deleted articles in search until next sync).

**Recommendation:**
- Mark the file as `status="deleted"` first, run S3 cleanup, then hard-delete the row. Trigger Bedrock sync after cleanup.
- Remove the redundant `s3_key + ".metadata.json"` delete in `_delete_s3_file`.

---

#### [API] Inconsistent SSE event handling — some endpoints publish via `StreamManager`, others write to the queue directly

| Attribute | Value |
|---|---|
| Severity | 🟡 Improvement |
| Effort | Low (< 1 day) |
| Location | [kb_manager/routes/ingest.py:32-71](kb_manager/routes/ingest.py) (direct `_channels` access) |

**Observation:**
`_sse_stream_generator` writes directly to `stream_manager._channels[key]` instead of using the public `subscribe()` API. The route also doesn't notify on disconnect via `close_channel`.

**Why It Matters:**
Encapsulation broken. If `StreamManager` internals change, the route silently breaks. Also this is the only route doing direct dict access — every other consumer of streams uses public methods.

**Recommendation:**
Use `async for item in stream_manager.subscribe(job_id, channel):` and rely on the subscribe context manager to handle cleanup.

---

#### [API] `POST /ingest` returns 202 even when the source/job creation fails

| Attribute | Value |
|---|---|
| Severity | 🟡 Improvement |
| Effort | Low (< 1 day) |
| Location | [kb_manager/routes/ingest.py:92-162](kb_manager/routes/ingest.py) |

**Observation:**
The route iterates URLs, creates source + job + schedules background task, and only commits at the end. If any URL's source creation fails inside the loop, prior URLs have orphan source rows committed (actually they don't, because commit is at the end — but the in-memory `source` objects are lost on error). Either way, the response shape is "success" only — there is no partial-success reporting.

**Why It Matters:**
For multi-URL ingest requests, a single bad URL aborts the whole batch silently from the user's perspective.

**Recommendation:**
Track per-URL status (`accepted`, `failed`, `error_message`) and return them all in the response. Use a savepoint per URL so one bad URL doesn't poison the others.

---

#### [API] List endpoints accept `region`/`brand` filters with `ILIKE` semantics — surprises users

| Attribute | Value |
|---|---|
| Severity | 🟢 Nice-to-have |
| Effort | Low (< 1 day) |
| Location | [kb_manager/queries/sources.py:93-95](kb_manager/queries/sources.py), [kb_manager/queries/files.py:83-85](kb_manager/queries/files.py) |

**Observation:**
`region=nam` filter uses `ilike("%nam%")`. So `region=na` matches `nam` *and* `nam_extra` if it ever existed. `brand` does the same.

**Why It Matters:**
The fields are constrained to a small enumerated set. Loose `ILIKE` matching is a leftover from search and is misleading for filter columns.

**Recommendation:**
Use exact match (`Source.region == region`). Reserve `ILIKE` for fields that genuinely want substring search (URL, title).

---

#### [API] Queue route exposes `worker._max_workers` (private) attribute

| Attribute | Value |
|---|---|
| Severity | 🟢 Nice-to-have |
| Effort | Low (< 1 day) |
| Location | [kb_manager/routes/queue.py:118-121](kb_manager/routes/queue.py), [kb_manager/services/queue_worker.py:74-77](kb_manager/services/queue_worker.py) |

**Observation:**
`worker._max_workers` and `worker._semaphore._value` are accessed from the route. The latter uses a private asyncio Semaphore field.

**Why It Matters:**
`asyncio.Semaphore._value` is undocumented. A Python upgrade could rename or remove it.

**Recommendation:**
Add a public `max_workers` property and use the existing public `active_count`. They're already semantic — promote them.

---

#### [API] No file-size or MIME type limits on (currently dead) upload path

| Attribute | Value |
|---|---|
| Severity | 🟡 Improvement |
| Effort | Low (< 1 day) |
| Location | [kb_manager/routes/ingest.py:144-159](kb_manager/routes/ingest.py), [kb_manager/services/pipeline.py:572-574](kb_manager/services/pipeline.py) |

**Observation:**
Even once the upload route is wired, there is no `Content-Length` cap, no MIME validation, no extension check. `upload_file.read()` followed by `.decode("utf-8")` will OOM on a malicious large file.

**Why It Matters:**
DoS surface as soon as auth lands and the path goes live.

**Recommendation:**
- Require `.md`/`.markdown` extensions; whitelist `text/markdown` and `text/plain`.
- Cap size at e.g. 2 MB; reject before reading.
- Stream-decode in chunks rather than `read()` all at once.

---

#### [API] Pagination uses `(page, size)` everywhere except `/activity` which uses Python-side sort+slice

| Attribute | Value |
|---|---|
| Severity | 🟡 Improvement |
| Effort | Medium (1–3 days) |
| Location | [kb_manager/routes/activity.py:34-116](kb_manager/routes/activity.py) |

**Observation:**
`/activity` issues three independent queries with `LIMIT (limit + offset)` each, unions the results in Python, sorts by timestamp, and slices. With `limit=20, offset=0` this fetches 60 rows and returns 20.

**Why It Matters:**
Inefficient and wrong as offset grows: `offset=100` fetches 360 rows but yields 20 from the end of an in-memory sort. Total count is also computed across whatever subset happened to be fetched, not the true total — `total` is misleading.

**Recommendation:**
Use a SQL `UNION ALL` with a common shape, sort and paginate at the DB level. Or compute the `total` per-source separately and aggregate.

---

### Section 4: Documentation Drift

#### [DOC] `docs/components/agents.md` lists 6 agents; one (`LinkTriageAgent`) is unwired

| Attribute | Value |
|---|---|
| Severity | 🟡 Improvement |
| Effort | Low (< 1 day) |
| Location | [docs/components/agents.md §3](docs/components/agents.md), [kb_manager/agents/link_triage.py](kb_manager/agents/link_triage.py) |

**Observation:**
The doc describes `LinkTriageAgent` as if it runs between Discovery and the source-creation loop. No code path invokes it. The pipeline goes straight from Discovery's `uncertain` to creating a `needs_confirmation` source.

**Why It Matters:**
Engineers reading docs first will look for triage logic that does not exist. Either the doc is aspirational or the agent is dead code.

**Recommendation:**
If wiring the agent (Strands recommendation above), keep the doc and add the call. If not, delete `link_triage.py` and the doc section.

---

#### [DOC] `docs/components/api-routes.md` references `GET /api/v1/queue/counts` and `GET /api/v1/nav` — second is wrong

| Attribute | Value |
|---|---|
| Severity | 🟡 Improvement |
| Effort | Low (< 1 day) |
| Location | [docs/components/api-routes.md §Navigation](docs/components/api-routes.md), [kb_manager/routes/nav.py:40](kb_manager/routes/nav.py) |

**Observation:**
The doc says `GET /api/v1/nav`. The actual route is `GET /api/v1/nav/tree`. The doc also omits the `force_refresh` query param and the `502` error mode.

**Recommendation:**
Update path; document `force_refresh`; add 502 to the error contract.

---

#### [DOC] `business-case.md §3.5` says Excel rows are linked to a `Source.url=decagon://<id>` but the Excel script is uncommitted

| Attribute | Value |
|---|---|
| Severity | 🟢 Nice-to-have |
| Effort | Low (< 1 day) |
| Location | [docs/business-case.md:101-107](docs/business-case.md), `scripts/ingest_excel.py` |

**Observation:**
`scripts/ingest_excel.py` is in the working tree but untracked (per `git status`). The business case promises behavior but the script's actual behavior cannot be verified against `main`.

**Recommendation:**
Either commit the script or amend the business case to mark Excel ingestion as in-progress. Add a CI check that the script runs end-to-end against a fixture file.

---

#### [DOC] `docs/components/api-routes.md` documents no auth/rate-limit information

| Attribute | Value |
|---|---|
| Severity | 🟡 Improvement |
| Effort | Low (< 1 day) |
| Location | [docs/components/api-routes.md](docs/components/api-routes.md) |

**Observation:**
The doc doesn't mention that all endpoints are public (no auth) and that there are no rate limits. A frontend engineer reading it would assume there's auth.

**Recommendation:**
Add an "Authentication" section that says "no auth currently — must be added before production." Keeps reviewers honest.

---

#### [DOC] `docs/components/queue-worker.md` retry table doesn't match code

| Attribute | Value |
|---|---|
| Severity | 🟢 Nice-to-have |
| Effort | Low (< 1 day) |
| Location | [docs/components/queue-worker.md §Retry Logic](docs/components/queue-worker.md), [kb_manager/queries/queue.py:138](kb_manager/queries/queue.py) |

**Observation:**
The doc's table shows "1st retry: 10s" with `base=5`. The code computes `base * (2 ** retry_count)` after `retry_count += 1`, so the first retry gets `5 * 2^1 = 10s` ✓. But the doc adds a "Total Wait" column claiming 10s, 30s, 70s — those are cumulative, but the code resets `started_at` on requeue, so observability of "total wait" doesn't actually surface. Minor confusion.

**Recommendation:**
Drop the "Total Wait" column or clarify it's a notional sum, not a tracked value.

---

#### [DOC] `docs/components/database.md` says `Source.metadata` but the column attribute is `metadata_`

| Attribute | Value |
|---|---|
| Severity | 🟢 Nice-to-have |
| Effort | Low (< 1 day) |
| Location | [docs/components/database.md §Source](docs/components/database.md), [kb_manager/models.py:78](kb_manager/models.py) |

**Observation:**
The Python attribute is `metadata_` (with trailing underscore to avoid clashing with `Base.metadata`). The DB column is `metadata`. The doc shows `metadata_` once and `metadata` elsewhere, never explaining the alias.

**Recommendation:**
Add a one-line note that the Python attribute is `metadata_` due to SQLAlchemy's reserved `metadata` name on `DeclarativeBase`, and the DB column is `metadata`.

---

## Prioritised Action Plan

Sorted: Critical first, then Improvement, then Nice-to-have. Within each tier: Low-effort first.

| Priority | Finding | Severity | Effort | Expected Impact |
|---|---|---|---|---|
| 1 | Stateful Strands `Agent` reused across files — clear or rebuild per call | 🔴 | Low | Restores QA verdict determinism; cuts token cost; prevents context-window failures on large jobs |
| 2 | CORS `*` + `allow_credentials=True` misconfiguration | 🔴 | Low | Unblocks credentialed frontend requests; closes future XSS amplification once auth lands |
| 3 | Add global exception handler middleware | 🔴 | Low | Stops leaking stack traces; gives clients a stable error envelope |
| 4 | Wrap all boto3 calls in `asyncio.to_thread` (or migrate to `aioboto3`) | 🔴 | Low | Stops event-loop starvation; restores SSE keepalive cadence; lets concurrent jobs actually run concurrently |
| 5 | Wire `query_kb` tool to `BedrockKBClient.retrieve` and align the file-id contract | 🔴 | Medium | Activates the uniqueness gate (the second half of the QA story); enables real dedup |
| 6 | Fix or remove the upload code path (currently passes `[]` to pipeline) | 🔴 | Medium | Restores the third documented content source or removes a misleading endpoint |
| 7 | Add authentication + authorization on every route | 🔴 | High | Closes the "anyone with network access can drain Bedrock budget / delete KB" gap |
| 8 | Fix `_process_single_file` recovery (`dir()` → `locals()` / sentinel) | 🟡 | Low | File failures are correctly marked rejected with reason instead of silently stuck |
| 9 | Run QA + Uniqueness via `asyncio.gather` | 🟡 | Low | Halves per-file QA latency |
| 10 | Make `_trigger_kb_sync` async via `asyncio.to_thread` | 🟡 | Low | Removes sync-blocking moment at end of every job |
| 11 | Tighten `region`/`brand` list filters from `ILIKE` to `==` | 🟡 | Low | Removes surprising matches; avoids future bugs as enums grow |
| 12 | Discriminated-union schemas for `IngestRequest` | 🟡 | Low | Validation moves into Pydantic; fewer manual `HTTPException(422)` |
| 13 | Replace `_sse_stream_generator` direct `_channels` access with `subscribe()` | 🟡 | Low | Restores encapsulation; cleanup happens in one place |
| 14 | Remove redundant metadata-sidecar delete in `_delete_s3_file` | 🟡 | Low | Stops 404 noise |
| 15 | Cap upload size + validate MIME (when route is wired) | 🟡 | Low | Closes DoS surface |
| 16 | Sanitize S3 key segments derived from LLM output | 🟡 | Low | Prevents collision/garbage S3 keys; stops Bedrock filter breakage |
| 17 | Add `ON DELETE CASCADE` on file→job and job→source FKs | 🟡 | Low | Removes the manual cleanup loop in `delete_source`; eliminates partial-failure FK errors |
| 18 | Update doc drift (api-routes, agents, database, queue-worker) | 🟡 | Low | Reduces surprise during onboarding |
| 19 | Make `BackgroundTasks` ingestion go via the queue | 🟡 | Medium | One lifecycle for jobs; graceful shutdown actually graceful |
| 20 | Decide & wire/delete `LinkTriageAgent` | 🟡 | Medium | Removes confusion; if wired, dramatically reduces `needs_confirmation` volume |
| 21 | Slim Discovery prompt input (component digest instead of full pruned JSON) | 🟡 | Medium | 30–60% Haiku cost reduction per scout |
| 22 | Replace `kb/chat` fake streaming with real Bedrock streaming or honest JSON | 🟡 | Low | Honest UX; sets up real streaming |
| 23 | Re-implement `/activity` pagination at the DB level | 🟡 | Medium | Correct counts; scalable past a few hundred events |
| 24 | Adopt `structlog` + correlation IDs | 🟡 | Medium | Debugging across pipeline → agents → S3 becomes feasible |
| 25 | Add `pg_trgm` GIN indexes on title/url for ILIKE searches | 🟡 | Medium | Search remains fast at 10K+ rows |
| 26 | Improve hallucination-defense fallback (re-prompt or default to navigation) | 🟡 | Low | Cleaner `needs_confirmation` queue |
| 27 | Lift module-shared `BedrockKBClient` into `app.state` | 🟢 | Low | Removes TOCTOU; consistent with other services |
| 28 | Combine `/stats` queries into a single FILTER aggregation | 🟢 | Low | Faster dashboard load |
| 29 | Replace `count_files_by_status` four queries with single GROUP BY | 🟢 | Low | Cosmetic perf |
| 30 | Sweep `Optional[X]` → `X \| None` | 🟢 | Low | Style consistency |
| 31 | Pass models via DI to agent classes | 🟢 | Low | Easier testing |
| 32 | Promote `worker._max_workers` to a public property | 🟢 | Low | Stop accessing private semaphore field |
| 33 | Reuse one `BedrockModel` instance per process | 🟢 | Low | Fewer boto3 client init calls |
| 34 | Lift `_extract_modify_date` jcr lookup outside loop | 🟢 | Low | Cosmetic perf/clarity |
| 35 | Add API versioning policy to `docs/architecture.md` | 🟢 | Low | Sets up future migrations |
| 36 | Document Decagon Excel script status | 🟢 | Low | Honest business-case doc |
| 37 | Document `metadata_` Python attribute alias | 🟢 | Low | One-line clarification |
| 38 | Document queue-worker "Total Wait" caveat | 🟢 | Low | Removes minor confusion |

---

## Appendix: Strands SDK References Used

- **Agent Loop / Conversation History** — [`docs/user-guide/concepts/agents/agent-loop/index.md`](https://strandsagents.com/docs/user-guide/concepts/agents/agent-loop/index.md), §3 Messages and Conversation History, §6 Common Problems → Context Window Exhaustion / MaxTokensReachedException. Confirms each `invoke_async` accumulates messages on the agent and recommends "decompose large tasks into subtasks, each handled with a fresh context."
- **Structured Output Best Practices** — [`docs/user-guide/concepts/agents/structured-output/index.md`](https://strandsagents.com/docs/user-guide/concepts/agents/structured-output/index.md), §3.6 Best Practices: keep schemas focused, use descriptive field names, handle errors with fallbacks. The codebase follows the first two but its fallbacks (`MetadataEnricher._fallback`) silently produce `Untitled` records — fine for resilience, but worth surfacing in metrics.
- **Multi-Agent Patterns** — [`docs/user-guide/concepts/multi-agent/multi-agent-patterns/index.md`](https://strandsagents.com/docs/user-guide/concepts/multi-agent/multi-agent-patterns/index.md). The pipeline implements a bespoke linear workflow (Scout → Process); none of Strands' Graph, Swarm, or Workflow primitives are in use. Given the pipeline's tight integration with the queue worker and DB sessions, custom orchestration is reasonable — moving to Strands' Workflow primitive would not buy much beyond making the agent chain explicit.
- **Prompt Engineering / Security** — [`docs/user-guide/safety-security/prompt-engineering/index.md`](https://strandsagents.com/docs/user-guide/safety-security/prompt-engineering/index.md). The Discovery and Extractor prompts are clear and structured. The QA prompt embeds untrusted markdown (`md_content`) directly inside `\`\`\`markdown ... \`\`\`` fences — sufficient for current adversaries (AEM content, not user input) but worth noting once the upload path goes live, since uploaded markdown is user-supplied.
