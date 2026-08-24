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

## Native apps (iPhone, Android, Apple TV, Android TV)

None of these exist yet — there's no scaffolding of any kind in this repo
today. This should be scoped as a separate future workstream once the web
client and REST API are stable. Native clients would consume the same
backend API as the web client, gated behind the bearer-token auth path
already in place (`app/auth.py`, `app/api/users.py`). Whether to build fully
native apps per platform or lean on cross-platform tooling is an open
question, not yet decided.
