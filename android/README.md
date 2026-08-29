# HDHR Open — Android Mobile Client App

Native Android phone and tablet client application for **HDHR Open**. Connects directly over your local network to the HDHR Open self-hosted DVR recording server and HDHomeRun tuners.

## Features

- **Live TV Guide (EPG)**
  - 2D time-based horizontal scrolling grid with fixed leading channel column.
  - Day headers and hourly ruler markings with real-time "Now" indicator line.
  - Channel favoriting with instant filter toggle and text search.
  - Bottom sheet program details with episode info, synopsis, and instant tune.
- **Live Playback with Watch Sessions**
  - Instant live streaming with backend watch sessions (`/api/watch/{channel}/start`).
  - Pause, rewind, and scrub live TV with thumbnail preview cues.
  - One-click promotion to permanent DVR recording while watching.
  - Automatic 20-second background heartbeat and clean tuner release on exit.
  - WebVTT closed captions overlay with toggle.
  - Multi-track audio stream switcher.
- **DVR Library & Scheduling**
  - Browse completed and in-progress recordings grouped by Shows, Movies, Sports.
  - Rich metadata (synopsis, episode/season badges, duration, file size).
  - Schedule Single Episode or Full Series recording rules with custom padding and keep limits.
  - Manage and delete scheduled rules and recordings.
  - Real-time DVR storage gauge (Free vs Used space).
- **Tuner Diagnostics**
  - Real-time polling (every 3s) of all HDHomeRun tuners.
  - Signal Strength %, Signal Quality %, Symbol Quality %, and Network Rate Mbps.
- **Household Profiles & PINs**
  - Living-room profile picker with 4-digit PIN pad authentication.
  - Secure Bearer token storage in Android Encrypted Preferences.
- **Server Discovery**
  - Automatic LAN discovery via Android `NsdManager` (mDNS `_http._tcp`) and manual IP fallback.

## Project Architecture

The Android client suite is structured with a shared multiplatform core module (`core`) and a modern Jetpack Compose application (`app`):

```
android/
├── core/                                     # Shared Engine & Logic
│   └── src/
│       ├── main/kotlin/org/hdhropen/kit/
│       │   ├── models/                       # Channel, GuideEntry, Recording, Rule, Profile, Tuner
│       │   ├── networking/                   # APIClient, AuthManager, ServerDiscovery, WatchSession
│       │   ├── playback/                     # PlayerEngine, VTTParser, CaptionController, StreamURLBuilder
│       │   ├── utilities/                    # Logger, TimeFormatting, RecordingRuleMatcher
│       │   └── viewmodels/                   # GuideViewModel, RecordingsViewModel, PlayerViewModel, TunerViewModel, etc.
│       └── test/kotlin/org/hdhropen/kit/     # Unit test suite
├── app/                                      # Android Mobile App (Jetpack Compose & Material 3)
│   └── src/
│       └── main/
│           ├── AndroidManifest.xml
│           ├── kotlin/org/hdhropen/app/
│           │   ├── MainActivity.kt
│           │   └── ui/
│           │       ├── theme/                # Theme.kt, Color.kt, Type.kt
│           │       ├── navigation/           # RootMobileScreen.kt, AppNavigation.kt
│           │       └── screens/              # Auth, Guide, Player, Recordings, Tuners, Settings
│           └── res/                          # Strings, Colors, Themes
├── gradle/
│   └── libs.versions.toml                    # Version Catalog
├── build.gradle.kts                          # Root build script
├── settings.gradle.kts                       # Multi-module settings
└── README.md
```

## Running & Building

### Opening in Android Studio
1. Open Android Studio (Hedgehog / Iguana / Jellyfish / Koala or newer).
2. Select **Open** and choose the `android/` directory.
3. Allow Gradle to sync dependencies.
4. Select the `app` run configuration and target an Android Phone/Tablet emulator (API 26+) or physical device.

### Running Unit Tests via Gradle
```bash
./gradlew :core:test
```
