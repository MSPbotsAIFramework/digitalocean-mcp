# PRD-21345 · Code review

Status: frozen @ 0c4604c

## Round 1 · 2026-11-05 · reviewed dev/PRD-21345 @ 0c4604c (base main @ 1688412)

Verdict: approved

### Findings

None.

Cross-checked the tool-to-DigitalOcean-operation mapping against DigitalOcean's own public OpenAPI spec (`https://api-engineering.nyc3.cdn.digitaloceanspaces.com/spec-ci/DigitalOcean-public.v2.yaml`, downloaded fresh for this review) — the same check that caught a query-params-vs-JSON-body bug in PRD-21344's round 1: `vpc_peerings_patch` (PATCH), `firewalls_update` (PUT), `domains_update_record`/`domains_patch_record` (PATCH used, matches the tool's stated partial-update semantics), `loadBalancers_update` (PUT with `region`+`forwarding_rules` required, both present in the tool's required args), `vpcs_patch` (PATCH) all match the HTTP verb and required-body-field shape the implementation actually sends — no params/body mismatch of the kind PRD-21344 had.

Everything else reviewed clean: credential handling is header-only via the shared `middleware.py`/`contextvars` path (SOP's three iron rules), with a Networking-specific concurrency-isolation test (`tests/test_middleware.py::test_concurrent_requests_do_not_leak_credentials_across_tenants`, AC15/TC17) using a distinct client and upstream path from the Apps/Kubernetes/Inference siblings' equivalent tests; error envelope and code vocabulary (`not_configured`/`unauthorized`/`not_found`/`invalid_argument`/`rate_limited`/`upstream_error`) match the shared `errors.py` exactly, including the 409→`upstream_error(retryable=False)` conflict mapping (AC11, `networking_client.py:123-130`, tested at `tests/networking/test_client.py::test_409_conflict_maps_to_non_retryable_upstream_error`); retry/backoff on 429/5xx honours `Retry-After` with a bounded budget (AC16, `networking_client.py:62-96`, `tests/networking/test_client.py`); every destructive tool (`delete_vpc`, `delete_firewall`, `delete_domain`, `delete_load_balancer`, `manage_vpc_peering`/`manage_domain_record`'s `delete` action) requires an explicit resource id, no name lookup or bulk variant; `update_vpc` (PATCH, partial) is clearly distinguished in its own docstring and tests from `update_firewall`/`update_load_balancer` (PUT, whole-object replace) per AC5/AC9/AC13; module layout follows the flat `networking_client.py` + `tools/networking_*.py` layout PRD-21338/21343/21344 already established on `main`, documented as a technical (not product) deviation from the design's assumed subpackage, consistent with the design's own fallback instruction ("whichever dev leg lands first effectively decides this").

Verified independently, not just re-read from the `[DEV]` stub:
- `uv sync && uv run pytest -q` → **111 passed**, 0 failures, 0 regressions (this review, `dev/PRD-21345 @ 0c4604c`, synced with `main @ 1688412`) — matches the Self-test claim exactly.
- Chinese-content scan (`grep -rnP '[\x{4e00}-\x{9fff}]' --exclude-dir=.git --exclude-dir=.venv .`): zero hits in any file this ticket touches; only pre-existing hits are in `docs/tickets/PRD-21338-review.md` / `PRD-21344-review.md` (unrelated tickets' review text).
- README `## MSPbots Connector` section: extracted and diffed byte-for-byte against `~/.claude/skills/vendor-mcp-development/reference/readme-connector-section.md` — **identical**, 0 diff lines.
- `gitleaks`: confirmed not installed on this machine (`command not found`), same known gap as PRD-21344's review.

Test cases: TC1-TC19 all covered by passing automated tests with real mocked-upstream evidence, each test traceable to its AC in `docs/tickets/PRD-21345.ac.json`; TC20 (AC6, the VPC-with-members precondition-failure shape and real peering lifecycle) correctly deferred as needing a real DigitalOcean account, not a blocker per `mcp-track.md` §3.

No scope creep: diff touches only the Networking tool modules, the shared `_shared.py`/`server.py`/`__init__.py` additions needed to register them, their tests, and `README.md`'s Networking section — no unrelated behavior changed, no new dependency beyond what was already declared for the sibling tickets, no schema/migration (N/A for this repo).
