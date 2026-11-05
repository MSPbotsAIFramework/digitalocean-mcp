# PRD-21343 · Code review

## Round 1 · 2026-11-05 · reviewed dev/PRD-21343 @ 7209c35 (base 34681e7)

Verdict: approved

### Findings

1. [suggestion] Dockerfile:28 — `LABEL org.opencontainers.image.description="DigitalOcean App Platform MCP server..."` is stale for this connector (it is Apps-specific wording), but the file is byte-identical to `origin/main`'s Dockerfile (same stale label already present there, inherited from PRD-21338 via the from-scratch SOP template both tickets followed independently). Cosmetic image metadata only, not functional. Left as-is; worth a one-line fix in a follow-up once the repo's shared files are reconciled across all four sibling tickets (do not fix unilaterally here since it is shared infrastructure, not an Inference-only file).
2. [suggestion] `docs/tickets/PRD-21343.md` Open questions / Risks & dependencies — the design correctly flags that the shared repo's tool count (18 from merged PRD-21338 + this ticket's 4 = 22) is now over the SOP §2.1 reference ceiling of ≤20 tools per service. This is a "should" guideline, not a hard "must" gate, and the SOP's own escape valve ("exceeding the ceiling requires per-tool justification in the delivery notes") is already satisfied by this ticket's own `Decisions made by DEV01` section, which justifies each of the 4 tools individually and documents what was cut. The actual ceiling breach is caused by the aggregate across 4 sibling tickets sharing one MCP service, not by anything in this ticket's diff alone — trimming this ticket's 4 tools would not fix the aggregate, and this ticket cannot unilaterally trim PRD-21338's already-merged 18. Recorded here as a known, acknowledged risk for whoever reviews PRD-21344/PRD-21345 next (each additional resource group makes the gap worse); not a reason to hold this ticket back. No BA-visible functional break results from it.

No must-fix. Everything the diff touches is scoped to `src/digitalocean_mcp/inference_client.py`, `src/digitalocean_mcp/tools/inference.py`, and the shared scaffold files it needed from scratch (`server.py`, `settings.py`, `middleware.py`, `errors.py`, `tools/_shared.py`, `tools/__init__.py`, `Dockerfile`, `pyproject.toml`) — all consistent with the tech design, AC1–AC10, and the 12-case `.ac.json`.

### Verification performed this round

- Read `docs/tickets/PRD-21343.md` (product design, tech design, test cases, self-test, handoff) and `docs/tickets/PRD-21343.ac.json` (12 cases) in full.
- `git diff 34681e7...7209c35`: 26 files, matches the `[DEV]` stub's described scope; no changes outside this ticket's Inference slice and the from-scratch shared scaffold.
- Credential handling (`middleware.py`, `tools/_shared.py`, `inference_client.py`): header-only (`X-DigitalOcean-Api-Token`), `contextvars`-scoped, reset in `finally`, no env-var fallback, no persistence to disk/log — matches SOP §3 and AC2/AC9.
- Error mapping (`inference_client.py:_to_result`): 401/403→`unauthorized`, 404→`not_found`, 400/422→`invalid_argument`, 429→`rate_limited`, 5xx→`upstream_error`, matches the tech design's envelope and AC4/AC7/AC8. Retry/backoff is bounded (`max_retries`, `max_retry_wait_seconds`), honors `Retry-After` when present, falls back to exponential backoff otherwise — matches AC7.
- Tool surface (`tools/inference.py`): 4 tools, each wrapped in the shared `tool_guard`, parameters/returns match § Data & API contract (AC3–AC6).
- README: connector-section byte-diff against `~/.claude/skills/vendor-mcp-development/reference/readme-connector-section.md` (stripping only this repo's own `<!-- BEGIN/END -->` wrapper comments, which are not part of the reference file) — identical. Tool table lists all 4 tools; header table documents `X-DigitalOcean-Api-Token` with both PAT and Model Access Key paths — matches AC10/TC11.
- `docs/tickets/PRD-21343.ac.json`: 12 cases, 11 `pass`, 1 `untested` (TC12, needs a real DigitalOcean account) with a non-empty `notes` reason and partial de-risking evidence (live 401 smoke test) — satisfies REVIEW.md §2.3 (no red/unexplained-untested cases).
- No Chinese characters anywhere in the repo (`grep -rnP '[\x{4e00}-\x{9fff}]'`, no matches). No hardcoded tokens/secrets in source (only the literal test fixtures `do_fake_token_test` / `token-A` / `token-B` referenced in the design, confined to tests).
- **Independent re-verification on the review host** (pytest itself could not be rerun — this host has no `uv` and no Python ≥3.12, a pre-existing environment gap noted by `mbp.py doctor`, not a defect in this ticket):
  - `sudo docker build --platform linux/amd64 -t digitalocean-mcp:prd21343-review .` — builds clean, non-root `app` user, `curl` present, matches the self-test's claim.
  - Container run: `GET /health` → `{"status":"ok"}`; `POST /mcp` with no credential header → `401`; `initialize` with a placeholder token → `200` with the Inference-specific `instructions` string; `tools/list` → exactly the 4 expected tool names (`digitalocean_inference_list_models`, `_create_chat_completion`, `_create_embedding`, `_generate_image`) with the annotations and parameter schemas described in the tech design (`list_models` is the only `readOnlyHint: true` tool). This independently confirms the self-test's TC1/TC2/AC1–AC3 claims rather than taking the doc's word for it.
  - Test container and image removed after verification.

### Known cross-ticket reconciliation needed at merge (not a review finding against this ticket — already flagged by the ticket's own design/self-test/handoff, to be resolved during R5/merge, documented there)

`origin/main` has moved since this ticket's dev leg synced (`34681e7` → `a090895`, PRD-21338's Apps connector merged 2026-11-05, ~9.5h after this ticket's dev leg finished). Confirmed by diffing this ticket's copies of the scaffold files against the current `main`:

- `errors.py`, `settings.py`: still byte-identical to `main`.
- `middleware.py`, `tools/_shared.py`, `__main__.py`: `main`'s versions gained structured observability logging (`telemetry.py`, request-id tagging, `tool_call` log lines) via PRD-21338's own review-round fix, which landed after this ticket's dev leg copied these files — not a gap in this ticket's code, a timing artifact of two tickets developing in parallel against the same empty repo.
- `tools/_shared.py`'s `get_client()` returns a single concrete type per branch (`DigitalOceanClient` on `main` for Apps, `DigitalOceanInferenceClient` here for Inference) — these need to become one parameterized helper at merge, since both resource groups' tool modules call it the same way.
- `server.py`: each branch registers only its own resource group's tools; needs combining.
- `README.md`: each branch documents only its own resource group; needs combining.
- `tools/__init__.py` docstring: needs combining.

None of this is a defect in PRD-21343's diff — it is exactly the scenario this ticket's own design (§ Risks & dependencies), self-test, and handoff sections anticipated and explicitly deferred to "whichever ticket merges second." Handled during this review's R5 merge step, with each resolution documented in the merge commit / R6 stub per `toolchain.md` §6.

Status: frozen @ 7209c35
