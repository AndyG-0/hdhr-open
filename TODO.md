# TODO

Architecturally larger findings from a full repository review, deferred
here rather than fixed inline. Track A (small/mechanical/low-risk) items
from the same review were already fixed directly — see commits `f856635`,
`22c3767`, `13600a9`. A further batch of small/mechanical Track B items
(CI, auth lockout-dict sweep, `watch.py` locking + one encapsulation fix,
remaining `asyncio.to_thread` wrapping, `db.py` column allow-lists, the
`SECRET_KEY_PATH` startup check) was also fixed directly — see the backend
hardening pass session on 2026-08-23.

## Backend

- **Consolidate the duplicated ffmpeg-streaming pipeline** between
  `app/api/streaming.py` and `app/api/dvr.py` — stderr-tail buffering,
  startup-timeout-then-502 logic, and background-task tracking are
  implemented nearly line-for-line twice. Why: any bugfix or behavior
  change to live streaming currently has to be made (and can drift) in two
  places.
- **Consolidate the 4x duplicated "spawn subprocess with timeout, kill on
  timeout" pattern** across `app/hwaccel.py`, `app/media_probe.py`,
  `app/dvr/media_cache.py`, and inline in `app/dvr/builtin/capture.py` into
  one shared async helper. Why: same subprocess-lifecycle logic
  re-implemented four times is a maintenance and correctness risk (each
  copy can diverge in timeout/kill handling).
- **Split `app/storage/db.py`** (1085 lines, ~70 functions spanning users/
  sessions/auth, app settings/network integrations, guide/channels, and DVR
  rules/recordings) into per-domain modules behind a shared connection
  helper. Why: a single file covering four unrelated domains makes the data
  layer hard to navigate and grow.
- **Fix remaining encapsulation breaks** where `capture.py`/`engine.py`
  reach into `db._connect()` directly to hand-write ad hoc SQL instead of
  adding named `db.py` functions, and where `api/watch.py` reaches into
  `watch._sessions` (a private module dict) from the API layer. Why: these
  bypass the module boundaries that make the rest of the codebase easy to
  reason about, and make future refactors of `db.py`/`watch.py` riskier.
  (The one instance of this in `watch.py` — hand-written SQL in
  `promote_existing_capture_for_schedule` — was already fixed via
  `db.mark_scheduled_recording_in_progress`.)
- **Rewrite `retention.py`/`rule_expander.py`'s Python-side
  fetch-everything-then-filter into SQL `WHERE` clauses** (now that the
  indices added in the Track A fix — `idx_recordings_status`,
  `idx_recording_rules_provider`, `idx_scheduled_recordings_rule_id` —
  support this), and replace `rule_expander`'s O(rules × programs ×
  existing) linear rescan with a dict-keyed lookup. Why: performance —
  currently scales linearly with full-table scans that the new indices
  could otherwise make cheap.

## Frontend

- **Split `routes/settings/+page.svelte`** (2621 lines, ~14 independent
  settings sections in one file/script scope) into per-section
  subcomponents. In the process, dedupe: the repeated admin-gated
  load-effect boilerplate (4x), the repeated `saving/saved/error`
  save-flow triad (12x), the identical `moveGuidePriorityUp/Down` vs
  `moveDvrPriorityUp/Down` reorder logic, and the duplicated priority-list
  reorder markup block. Why: one file covering 14 unrelated settings
  sections is hard to navigate, and the duplicated patterns mean a fix to
  one save-flow/reorder implementation doesn't propagate to its siblings.
- **Split `HDHomeRunPlayer.svelte`** (1602 lines) — mpegts.js lifecycle
  wiring, hand-rolled VTT parsing (captions + thumbnails, ~80 lines
  duplicating what a native `<track>`/`TextTrack` could do), the
  live-delay caption-resync heuristic, and the record-menu/rule UI are all
  one component. Also share the `currentRule`/`isPending`/`canRecord`
  derivations, currently reimplemented here and separately in
  `HDHomeRunGuideGrid.svelte`/`HDHomeRunGuideCellMenu.svelte`. Why: one
  component mixing playback engine wiring with recording-rule UI logic is
  hard to test and modify in isolation, and the derivation logic can drift
  between its three copies.
- **Add virtualization to `HDHomeRunGuideGrid.svelte`** for large channel
  lineups (currently renders every channel × every cell unconditionally —
  hundreds to low-thousands of DOM nodes for a full cable lineup); memoize
  `findExistingRule` into a lookup map instead of an O(cells × rules) scan
  recomputed on every render (including the 30s tick). Why: performance —
  full lineups on real cable/satellite systems can be large enough for
  this to visibly lag, especially on lower-powered client devices.
- **Decide the fate of `polling.ts`'s intended pattern more broadly.** Even
  after removing the dead `pollWidget` export, the 3 places that pattern
  was meant to replace (`HDHomeRunGuideGrid.svelte`'s `nowSeconds` ticker,
  `HDHomeRunPlayer.svelte`'s detail/caption polling, `+page.svelte`'s
  watch heartbeat) still hand-roll `setInterval`/`clearInterval`
  independently. Why: either adopt a shared helper for consistency, or
  explicitly accept the current hand-rolled approach as intentional so a
  future contributor doesn't reintroduce a similarly-dead abstraction.
- **Minor/style, low priority:**
  - `breakpoint.ts`'s module-level `resize` listener is never removed
    (harmless — the singleton store lives for the app's lifetime, but
    inconsistent with "own your cleanup" elsewhere in the codebase).
  - `network.ts` is a misleading name for what's actually an
    insecure-origin/mic-permission utility, not an HTTP layer.
  - `routes/+page.svelte` uses a dependency-free `$effect` instead of
    `onMount` for its one-time initial load — the only place in the app
    doing it that way.
