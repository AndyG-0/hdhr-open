# TODO

Architecturally larger findings from a full repository review, deferred
here rather than fixed inline. Track A (small/mechanical/low-risk) items
from the same review were already fixed directly — see commits `f856635`,
`22c3767`, `13600a9`. A further batch of small/mechanical Track B items
(CI, auth lockout-dict sweep, `watch.py` locking + one encapsulation fix,
remaining `asyncio.to_thread` wrapping, `db.py` column allow-lists, the
`SECRET_KEY_PATH` startup check) was also fixed directly — see the backend
hardening pass session on 2026-08-23. The `db.py` split/encapsulation
fixes, the `HDHomeRunPlayer.svelte` split, and the ffmpeg-streaming-pipeline
+ subprocess-spawn consolidations were also fixed directly — see the
architecture-cleanup session on 2026-08-24. The `retention.py`/
`rule_expander.py` SQL-ification and dict-keyed dedup rewrite (the sole
Backend item) was also fixed directly — see the SQL-rewrite session on
2026-08-24.

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
