# Agent Rewrite Plan

Status: DRAFT — awaiting approval
Approach: **Full clean rewrite**, reusing the good ideas (adapter pattern, auto-discovery registry) but rebuilding the core with self-modification and multi-format file handling designed in from day one.

---

## What we keep from v0.2

These were the right calls. They survive the rewrite:

- **Provider adapter pattern** (`models/base.py` → ollama / openai / anthropic). Good abstraction.
- **Auto-discovery tool registry** (`tools/base/registry.py`). Drop a folder, get a tool. This is the mechanism the self-build mode rides on.
- **Pydantic `ToolDefinition`**. Type-safe tool specs.

## What we throw out / fix

- **Tool-result message routing** — `agent.py:75` hardcodes OpenAI format for all providers. The adapters already have `build_tool_result_message()` that never gets called. Fixed in the new loop.
- **Anthropic history corruption** — `agent.py:59` drops `tool_use` blocks. New loop stores full provider-native assistant messages.
- **String-parsed "thinking"** — `agent.py:63` greps `Thinking:` out of text. Fragile. Replaced with real structured thinking (Phase 2).
- **Wrong defaults** — `OLLAMA_HOST=https://ollama.com` (marketing site, not API), `AGENT_MODEL=gpt-oss:120b-cloud` (not a real model). Fixed in config.
- **Weak web_search** — DuckDuckGo Instant Answers returns almost nothing for technical queries. Swapped for a real search API (Tavily/Brave/Serper).

---

## Target architecture

```
main.py                 CLI entry, arg parsing, mode dispatch
config.py               provider/model/env resolution (fixed defaults)
agent/
  loop.py               core conversation loop (provider-correct tool routing)
  thinking.py           structured thinking (Phase 2)
  session.py            save/load conversation history to disk
  modes.py              chat | research | self-build mode dispatch
models/
  base.py               ModelAdapter ABC (keep)
  ollama.py openai.py anthropic.py   (keep, wire up build_tool_result_message)
tools/
  base/                 registry + ToolDefinition (keep)
  files/                NEW: unified multi-format CRUD (Phase 1)
  research/             NEW: autonomous research tools (Phase 3)
  self_build/           NEW: code-writing + self-edit tools (Phase 4)
  ... existing tools (grep, run_command, web_search, etc.)
```

---

## Phase 0 — Working foundation (rewrite the core)  ✅ DONE

Goal: the agent works correctly on all three providers before adding anything new.

- [x] Rewrite `agent/loop.py` with provider-correct tool-result routing (calls `adapter.build_tool_result_message()`)
- [x] Store full provider-native assistant messages (fix Anthropic `tool_use` history) via `build_assistant_message()`
- [x] `config.py` per-provider default model (env `AGENT_MODEL` still wins). NOTE: Ollama Cloud config was NOT a bug — left intact.
- [x] Add `agent/session.py` — save/load history as JSON + `/save` `/load` `/sessions` `/reset` chat commands
- [x] Add context-window guard (`agent/context.py`) — trims oldest turns, never orphans a tool result
- [x] Swap `web_search` to a real backend — Tavily if `TAVILY_API_KEY` set, else DuckDuckGo HTML scrape (keyless, real results)
- [x] Smoke test: full app imports clean, context guard verified

Exit criteria: a multi-turn, multi-tool conversation completes cleanly on all 3 providers. (Import + unit verified; live multi-provider run pending real API calls.)

---

## Phase 1 — Multi-format file CRUD  ✅ DONE

Goal: full Create / Read / Update / Delete across txt, md, DOCX, Excel, CSV, PDF, images (OCR).

Delivered: `tools/files/` dispatch engine + unified `read_file` / `write_file` / `edit_file` / `delete_file`. 14/14 format round-trip tests pass. `create_file` removed (superseded by `write_file`). Dead `create_pdf`/`edit_pdf` dirs cleaned up. Tesseract OCR binary not installed — image read fails with a clear install message (graceful).

Design: ONE `tools/files/` package with format dispatch by extension. The model sees simple verbs (`read_file`, `write_file`, `edit_file`, `delete_file`); the dispatch picks the right parser underneath.

| Format | Read | Write/Create | Edit | Library |
|--------|------|--------------|------|---------|
| txt / md | ✓ | ✓ | ✓ | stdlib |
| CSV | ✓ | ✓ | ✓ (row/cell) | stdlib `csv` |
| Excel (xlsx) | ✓ | ✓ | ✓ (cell) | `openpyxl` |
| DOCX | ✓ | ✓ | ✓ (paragraph) | `python-docx` |
| PDF | ✓ (text) | ✓ (generate) | append-only | `pdfplumber` read, `reportlab` write |
| Images | ✓ (OCR) | — | — | `pytesseract` + `pillow` |

- [ ] `tools/files/dispatch.py` — extension → handler map
- [ ] Handlers: `text_handler`, `csv_handler`, `xlsx_handler`, `docx_handler`, `pdf_handler`, `image_ocr_handler`
- [ ] Unified tools: `read_file`, `write_file`, `edit_file`, `delete_file` (delete stays format-agnostic)
- [ ] Graceful failure when a format can't do an op (e.g. "PDF edit is append-only")
- [ ] Tesseract is a system binary — document the install (`apt install tesseract-ocr`), fail with a clear message if missing
- [ ] Tests per format with sample fixture files

Notes / honest limits:
- **PDF editing is not real editing.** PDFs aren't text files. We support read (extract text) + create (generate new) + append. In-place edit of an existing PDF is out of scope — say so plainly to the model.
- **Image OCR is read-only.** We're not generating/editing images.

Open question to confirm during this phase: do you want **structured** reads (e.g. CSV → rows the model can reason over) or just **flattened text**? Structured is more useful for data tasks; flattened is simpler.

---

## Phase 2 — Real thinking method  ✅ DONE

Goal: replace the `Thinking:` string-grep hack with structured reasoning the model actually supports.

Delivered: `parse_response` now returns `(content, tool_calls, thinking)`. `gpt-oss` via Ollama returns NATIVE thinking (`think=True` → `message.thinking`) — verified live, reasoning arrives in its own channel. Anthropic extended thinking wired + guarded (auto-disables on reject). OpenAI/gpt-4o uses the prompted `<thinking>` fallback via `agent/thinking.py`. Loop renders thinking in a dim blue channel, never mixed into the answer. Thinking blocks persist in history (Anthropic requires it). Correction to original plan: Ollama gpt-oss is a NATIVE-thinking path, not a fallback.

Two layers:

1. **Native reasoning where the provider supports it**
   - Anthropic: extended thinking via the `thinking` parameter — real reasoning tokens, returned as `thinking` blocks.
   - OpenAI: reasoning models (o-series) expose reasoning effort.
   - Ollama: fall back to a prompted scratchpad (the current approach, but isolated cleanly).

2. **Explicit plan-act-observe scratchpad** (provider-agnostic)
   - Before tool calls, the model writes a short plan to a dedicated `thinking.py` channel, NOT mixed into user-visible content.
   - Rendered separately in the CLI (dim/blue), kept in history so the model can see its own past reasoning.

- [ ] `agent/thinking.py` — abstraction over native-vs-prompted thinking
- [ ] Per-adapter: expose native reasoning when available, prompted scratchpad otherwise
- [ ] CLI renders thinking in a separate visual channel (not parsed out of text)
- [ ] Thinking persisted in session history

This also feeds Phase 3/4 — research and self-build need the model to plan explicitly before acting.

---

## Phase 2.5 — Multi-modal + memory + UX  ✅ DONE

Added between Phase 2 and 3 on user request. Three capability jumps:

**Vision (describe_image tool)** — the agent can SEE images, not just OCR text.
Runs on `qwen3-vl:235b-instruct` via Ollama Cloud API (zero local capacity — a
235B model can't fit on a laptop, so it's cloud-only by design). Verified: it
described a red-circle-on-blue image that OCR returns nothing for. Configurable
via `VISION_MODEL`. Main agent stays on gpt-oss (text-only).

**RAG / vector memory** — `index_file` + `search_knowledge` tools backed by
`agent/memory.py`. Embeddings via LOCAL `nomic-embed-text` (274MB, CPU-light;
the cloud plan has no embedding model → 401). Store is numpy + JSON cosine
search (NOT chromadb — its onnxruntime dep has no Python 3.10 wheel, and we
bring our own embeddings so we don't need it). Persists to `vector_store/`,
survives restarts → cross-session memory. Verified: semantic retrieval works
("how much is rent?" → budget.xlsx).

**Streaming + token tracking** — Ollama responses stream live (thinking + answer
print as tokens arrive) via `stream_chat`. Token usage shown per-call and
cumulative. Graceful: non-streaming providers use the existing path; thinking
fallback intact. Verified end-to-end with a tool call across two streamed turns.

Architecture note: text brain on gpt-oss (Ollama), specialized senses split —
vision on cloud, embeddings on local. All overridable via env.

---

## Phase 3 — Auto-research mode

Goal: an autonomous research loop. Given a topic, the agent searches, reads multiple sources, synthesizes, and writes structured notes — without a human driving each step.

Loop: `plan → search → read sources → extract → synthesize → save → assess gaps → repeat until satisfied or budget hit`.

- [ ] `agent/modes.py` — add `research` mode (`main.py --mode research "<topic>"`)
- [ ] Research budget: max iterations / max sources / max tokens (prevents infinite loops + runaway cost)
- [ ] `tools/research/` — `search_sources`, `read_source`, `take_notes`, `synthesize`
- [ ] Output: `research/<topic_slug>/notes.md` with sources cited
- [ ] Gap assessment: after each round, model decides "do I know enough?" and either stops or queries again
- [ ] Hard stop on budget so it can't loop forever

This is the safe precursor to Phase 4: the research loop is exactly what self-build uses, minus the code-writing.

---

## Phase 4 — Self-build mode (the ambitious one)

Goal: the agent improves itself. It researches a capability gap, then **writes new tools AND can modify its own core code** (`agent/`, `config.py`, `models/`). New tools are auto-discovered by the registry; core edits require a restart.

Scope (your call): **full self-modification** — tools + core code.

Flow:
```
1. Identify gap (user says it, or agent notices a failure)
2. Research how to solve it (Phase 3 loop)
3. Write the code (new tool file, or edit to core)
4. [SAFETY GATE — see below]
5. Validate (syntax check, import check, run tests)
6. Activate (registry auto-loads new tool / restart for core edit)
7. On failure → rollback
```

- [ ] `tools/self_build/` — `write_tool`, `edit_core`, `validate_code`, `run_tests`
- [ ] **Mandatory git checkpoint before EVERY self-edit** — auto-commit so any change is reversible with one command
- [ ] Validation gate: new/edited code must pass `python -m py_compile` + import check + existing test suite before activation
- [ ] Crash recovery: if the agent bricks itself on a core edit, a supervisor process detects the crash and `git reset` to last good commit
- [ ] Self-edits to core require restart; new tools are hot-loaded by the registry

### ⚠️ Safety gate — DECISION DEFERRED (you chose "decide later")

When the agent writes/runs self-generated code, two designs are on the table. We pick before building Phase 4:

- **Option A — Approve before each self-edit.** Agent proposes code, you review, you approve/reject before anything is written or run. You stay in the loop.
- **Option B — Fully autonomous + git rollback.** Agent writes, commits, and runs on its own. Review happens after the fact; you `git reset` if it misbehaves.

Both ride on the same mandatory-git-checkpoint mechanism. The only difference is whether a human approves before or audits after. **This must be decided before Phase 4 starts.**

### Honest risks of full self-modification

- A bad core edit can brick the agent mid-run. Mitigation: git checkpoint + supervisor + validation gate. But you should expect it to happen at least once.
- The agent running its own generated code is an arbitrary-code-execution path by design. Keep it on a machine where that's acceptable (it already has `run_command` with shell access, so this isn't a new category of risk — but self-build makes it routine).
- "Improve itself" can mean "wander off and rewrite things you liked." The plan-act-observe thinking (Phase 2) + approval gate (Option A) are the guardrails against drift.

---

## Dependency additions (pyproject.toml)

```
pdfplumber        # PDF text extraction
reportlab         # PDF generation
python-docx       # DOCX
openpyxl          # Excel
pytesseract       # OCR (needs system tesseract-ocr binary)
pillow            # image loading for OCR
tavily-python     # real web search (or brave/serper)
```

---

## Build order summary

```
Phase 0  Working foundation (fix core, all providers green)   ← do first
Phase 1  Multi-format file CRUD
Phase 2  Real thinking method
Phase 3  Auto-research mode
Phase 4  Self-build mode      ← safety gate decision required before starting
```

Each phase ends working and committed. We don't start Phase N+1 until N is green.

---

## Decisions still open

1. **Safety gate** (Phase 4): Option A approve-first vs Option B autonomous+rollback. Deferred by your choice — must resolve before Phase 4.
2. **File reads** (Phase 1): structured (rows/cells) vs flattened text. Lean structured.
3. **Search provider** (Phase 0): Tavily (recommended) vs Brave vs Serper. Need an API key for whichever.
