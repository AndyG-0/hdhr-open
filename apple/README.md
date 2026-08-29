# HDHR Open — Apple TV (tvOS) & iOS Client Apps

Native Apple TV (tvOS) and iOS/iPadOS client applications for **HDHR Open**. Connects directly over your local network to the HDHR Open self-hosted DVR recording server and HDHomeRun tuners.

## Features

- **Live TV Guide (EPG)**
  - 10-foot FocusEngine timeline grid on Apple TV, touch-scrollable timeline & search on iOS.
  - Now & Next program cards with progress bars and "Live" indicators.
  - Channel favoriting with instant filter toggles.
- **Live Playback with Watch Sessions**
  - Instant live streaming with backend watch sessions (`/api/watch/{channel}/start`).
  - Pause, rewind, and scrub live TV with thumbnail preview boxes.
  - One-click promotion to permanent DVR recording while watching.
  - Automatic 20-second background heartbeat and clean tuner release on exit.
- **DVR Library & Scheduling**
  - Browse completed and in-progress recordings grouped by Shows, Movies, Sports.
  - Rich metadata (synopsis, episode/season badges, duration, file size, thumbnail posters).
  - Schedule Single Episode or Full Series recording rules with custom padding and keep limits.
  - Manage and delete scheduled rules and recordings.
  - Real-time DVR storage gauge (Free vs Used space).
- **Tuner Diagnostics**
  - Real-time polling of all HDHomeRun tuners.
  - Signal Strength %, Signal Quality %, Symbol Quality %, and Network Rate Mbps.
- **Household Profiles & PINs**
  - Living-room profile picker with PIN pad authentication.
  - Secure Bearer token storage in the Apple Keychain (`POST /api/users/{id}/login`).
- **Server Discovery**
  - Automatic LAN discovery via Bonjour (`_http._tcp`) and manual IP fallback.

## Project Architecture

The Apple client suite is structured with a shared multiplatform Swift Package (`HDHROpenKit`) and dedicated platform applications:

```
apple/
├── HDHROpenKit/                 # Shared Swift Package (tvOS + iOS + macOS)
│   ├── Sources/HDHROpenKit/
│   │   ├── Models/             # Channel, GuideEntry, Recording, Rule, Profile, Tuner
│   │   ├── Networking/         # APIClient, AuthManager, ServerDiscovery, WatchSession
│   │   ├── Playback/           # PlayerEngine, VTTParser, CaptionController, StreamURLBuilder
│   │   ├── ViewModels/         # GuideViewModel, RecordingsViewModel, PlayerViewModel, TunerViewModel, etc.
│   │   └── Utilities/          # Logger, TimeFormatting, RuleMatcher
│   └── Tests/HDHROpenKitTests/ # Unit test suite
├── HDHROpenTV/                  # Apple TV App (tvOS 17+)
│   ├── App/                    # HDHROpenTVApp, RootTVView
│   ├── Views/                  # 10-foot Focus-optimized Guide, Player, Recordings, Tuners, Settings
│   └── Resources/Info.plist
└── HDHROpeniOS/                 # iOS / iPadOS App (iOS 17+)
    ├── App/                    # HDHROpeniOSApp, RootiOSView
    ├── Views/                  # Touch Guide, Gesture Player, Recordings, Tuners, Settings
    └── Resources/Info.plist
```

## Running & Testing

### Running Shared Unit Tests
```bash
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swift test --package-path apple/HDHROpenKit
```

### Opening in Xcode
Open the `apple/` folder or `apple/HDHROpenKit` in Xcode 15+. Select the **HDHROpenTV** or **HDHROpeniOS** scheme and choose your Apple TV or iPhone simulator.
