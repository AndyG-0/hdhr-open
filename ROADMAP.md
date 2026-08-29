# Roadmap

This document tracks the larger initiatives planned for HDHR Open beyond its
current feature set. It's a snapshot of intent and known constraints, not a
committed schedule.

## Recording

**Known risk, unverified:** when the guide is sourced from an XMLTV file
instead of HDHomeRun's own guide, the show/series IDs it produces likely
won't match what SiliconDust's DVR engine expects internally — meaning
official-DVR recording rules created from an XMLTV-sourced guide may not
actually work. This needs real-world verification against a live tuner.

## Native apps (Apple TV, iOS, Android, Android TV)

- **Apple TV (tvOS) & iOS (iPhone/iPad)**: Implemented in `apple/` using a
  shared Swift framework (`HDHROpenKit`), featuring 10-foot Siri Remote navigation,
  touch controls, live watch sessions with pause/rewind/scrub, DVR scheduling/library,
  tuner signal meters, and Bearer token auth via Keychain.
- **Android (Phone & Tablet)**: Implemented in `android/` using Jetpack Compose
  and a shared core module (`core`), featuring touch controls, 2D time-based EPG guide grid,
  live watch sessions with pause/rewind/scrub, DVR scheduling/library, tuner signal meters,
  mDNS server discovery, closed captions, and Bearer token auth via Encrypted Preferences.
- **Android TV**: Planned for a future workstream, building on the shared `core` module.
