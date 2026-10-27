# Meta Dev test readiness — 2026-10-27

## Scope

- Rebuilt `api` and `worker` so the image-contained test corpus matches the
  workspace. Runtime `src`, `apps` and `config` are bind-mounted; the stale
  artifact was the non-mounted test file, not an assertion that all runtime
  source was stale.
- Cleared only the configured CFC Meta Developer recipient's transient
  conversation state: inbox, messages, slots, batches, outbox and handoff.
- Preserved CRM snapshots, approved data, FAQ and audit data.
- CFC delivery is recipient-restricted canary at 100% with every CFC workflow
  included. `LIVE_SEND_APPROVED` remains false.
- Restored CFC from Redis `pause` state and isolated operations-route tests so
  test execution cannot pause the live development control store.

## Verification

| Check | Result |
| --- | --- |
| API health | healthy |
| Worker Ollama readiness | ready (`qwen2.5:7b`) |
| CFC test state after reset | 0 conversations, 0 inbox, 0 outbox, 0 handoffs |
| F1–F8 selected gates plus reset test | 91 passed, 4 intentional opt-in skips |
| Intent/workflow plus T01–T12 regression | 74 passed |
| Default full suite | 190 passed, 137 intentional opt-in skips |
| Full FAQ-enabled suite | 309 passed, 18 intentional skips |
| Live Qwen intent gate | 20 passed |

## Meta incident: greeting and image caption

The clean Meta conversation reproduced two independent routing failures:

- `Xin chào` was accepted from Qwen as `HUMAN_REQUEST`, which created a real
  pending handoff even though no human-request evidence existed.
- Meta delivered the caption plus two images inside one debounced batch, but
  the pipeline only selected the image response when text was empty. The
  caption therefore entered `PRODUCT_INQUIRY` and produced a catalog no-match.

The remediation is category-based rather than tied to those two sentences:

- configurable evidence requirements protect high-impact model intents;
- attachment types are supplied to structured understanding without image URLs;
- configurable attachment routing handles captions, multiple images and Page
  differences while preserving explicit price/dealer/order/contact/human flows;
- named product references remain product inquiries;
- crop candidates use configurable discourse boundaries and rejection terms;
- switched workflows trust the analyzer's filtered slots instead of restoring
  stale slots in the pipeline.

The bad test conversation and its pending handoff were removed after the new
worker passed all gates.

## Notes

Old `SUPPRESSED` outbox rows are intentionally not replayed. Send a fresh Meta
message after this readiness check and wait for the configured debounce window.
The manual test procedure is in `docs/META_DEV_SELF_TEST.md`.
