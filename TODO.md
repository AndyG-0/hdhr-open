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
2026-08-24. The `routes/settings/+page.svelte` split (14 sections into
per-component subfiles sharing new `loadOnceWhen`/`SaveState`
composables) and the `HDHomeRunGuideGrid.svelte` virtualization
(memoized recording-rule lookups, a stabilized `windowBounds`
derivation, and windowed channel-row rendering) — the two remaining
Frontend items — were also fixed directly — see the frontend-split
session on 2026-08-24.
