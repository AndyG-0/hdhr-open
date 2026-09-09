# TODO

Forward-looking roadmap, broken into single-session/feature-sized iterations.
Each item names the files it touches so a future session can pick it up and
go without re-deriving context. Earlier completed review/hardening passes
and shipped features are documented in the commit history rather than repeated here.

## Closed Captioning

- [ ] **CC-10 — Web: simplify live-caption lag-compensation logic once CC-8/CC-9 are verified on real hardware.**
  `caption-controller.ts` and `HDHomeRunPlayer.svelte` currently stretch/align live cues
  (`LIVE_CUE_MIN_DISPLAY_SECONDS`, `alignLiveCues`, `baseOffsetSeconds` drift
  correction) specifically to paper over cues arriving several seconds late
  in batches. CC-8's `ccextractor` swap should make that arrival pattern
  mostly go away — once verified against a real physical tuner (CC-8's testing
  constraint), revisit whether this logic can be trimmed down or removed.
  Don't start this before that real-tuner verification, since the whole
  premise depends on it.
  - **Files**:
    - `frontend/src/lib/caption-controller.ts` (MODIFY: simplify or remove artificial stretch slots & drift correction)
    - `frontend/src/lib/components/HDHomeRunPlayer.svelte` (MODIFY: update caption event bindings)

