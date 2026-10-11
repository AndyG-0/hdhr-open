# Usage Guide

This page covers the web app's day-to-day features once the server is
[installed](installation.md) and running. For DVR-specific behavior (Series
IDs, fallback, commercial detection), see the [DVR Guide](dvr.md).

## First run

The first time you open HDHR Open, the setup screen walks you through
creating your household's first profile — this becomes the admin. A PIN is
optional at this step but recommended once other household members get
their own profiles.

## Signing in — "Who's watching?"

HDHR Open uses PIN-protected household profiles rather than a single login:
pick a profile, enter its PIN (if it has one), and you're in. Each browser
session is tied to one device. An admin can add further profiles from the
same screen; member profiles have reduced access compared to the admin
role (e.g. settings that affect the whole household).

## The Guide

The main navigation is **Guide**, **Discovery**, **Recordings**,
**Settings**, and **Ask AI**.

The Guide is the channel lineup with program info. Click/tap a program to
see details and tune in, or to schedule a recording (see the
[DVR Guide](dvr.md)).

## Live playback

Playback works in one of two modes, set in **Settings → Recording** (or
per-stream): `server_transcode` (the backend transcodes the raw tuner
stream to browser-playable H.264/AAC — works with any tuner but costs CPU
per concurrent viewer) or `external` (hands a raw stream link to an
external player like VLC instead of playing in-browser).

In the player:

- **Go Live** returns to the live edge of an in-progress channel or
  recording.
- A **playback stats** panel shows the active video/audio/container/track
  details.
- Single-viewer live TV automatically downgrades quality to reduce server
  load when no one else is watching.
- Captions (WebVTT) and multi-track audio switching are supported where the
  source provides them.

### Multi-View

Watch several feeds at once from the player: 2-up split, 3-up hero, or a
quad grid. Each feed consumes a physical tuner, so Multi-View is limited by
how many tuners your HDHomeRun has — the UI shows how many are currently
in use (recording vs. streaming) and warns when tuners are exhausted,
rather than silently failing. Promote any feed to "primary" (hero) or close
individual feeds to free up a tuner.

### SyncPlay (watch party)

Start a synchronized watch session — live TV or a DVR recording — with
other people on your household, across web, Apple TV, iOS, and Android. The
host creates a room and shares its 6-digit room code; others join with that
code. Playback stays in sync (buffering/ready/syncing states are shown to
everyone), and the host role can be handed off to another participant.

## Discovery

The **Discovery** tab surfaces recommended shows ("New & Notable") based on
what your household has already recorded, to help surface things worth
recording next. It needs a bit of recording history before it has anything
to suggest.

## Ask AI

If an AI provider is configured (**Settings → Integrations**), the **Ask
AI** panel lets you ask natural-language questions about the guide and —
depending on what's enabled — take actions like scheduling a recording. The
assistant asks for confirmation before any action that changes state (e.g.
creating a recording rule) rather than acting silently.

## Settings

Settings are organized into tabs:

- **Your Settings** — profile-level preferences (language, appearance/theme).
- **Household** — profiles/PINs for everyone in the household.
- **Guide** — channel lineup and guide source management (HDHomeRun Cloud,
  XMLTV, Schedules Direct).
- **Tuners** — HDHomeRun network/tuner settings, diagnostics, and the
  HDHomeRun DVR recordings-mount/SSH settings used for commercial detection
  (see [Configuration](configuration.md) and the [DVR Guide](dvr.md)).
- **Recording** — DVR engine defaults, playback mode, commercial-detection
  defaults, and hardware-acceleration settings (including **Run
  diagnostics** — see [Hardware Acceleration](hardware-acceleration.md)).
- **Integrations** — AI provider and other external integrations.
- **System** — server-level settings.

Language can be changed per-profile under **Your Settings**; HDHR Open
currently ships English, Spanish, French, and German translations.
