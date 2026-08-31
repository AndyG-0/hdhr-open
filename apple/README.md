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

## Sideloading

Both app targets use `CODE_SIGN_STYLE = Automatic` with no team/certificate/
provisioning profile baked into the project, so they'll build and sign with
whatever Apple ID you have configured in Xcode — including a free-tier
**Personal Team**, no paid Apple Developer Program membership required.

### Free-tier (Personal Team) install

1. In Xcode, go to **Settings → Accounts** and sign in with your Apple ID if
   you haven't already. This adds a "(Personal Team)" team you can select
   per-target.
2. Open `apple/HDHROpen.xcodeproj`. For each target you want to install
   (**HDHROpenTV**, **HDHROpeniOS**), select it in the project navigator,
   go to **Signing & Capabilities**, and pick your Personal Team from the
   **Team** dropdown. Xcode will generate a personal provisioning profile
   automatically.
3. Connect your device (iPhone/iPad over USB, or an Apple TV on the same
   network paired via **Xcode → Window → Devices and Simulators**) and
   register it: select the device as the run destination and build — Xcode
   prompts to register the device's UDID against your account the first
   time.
4. On the device, trust the developer certificate once: **Settings →
   General → VPN & Device Management** (iOS) and the equivalent under
   **Settings → General** on tvOS, then select your Apple ID and tap
   **Trust**.
5. Build and run (⌘R) from Xcode to install.

**Limitations of a Personal Team build**, all inherent to free-tier signing
(not specific to this app):
- **Apps expire after 7 days.** A free-tier provisioning profile is only
  valid for a week; after that the app refuses to launch until you rebuild
  and reinstall from Xcode. There's no way around this without a paid
  account — plan on a weekly `⌘R` from a machine with the project open.
- **Up to 3 apps at a time** can be signed with a single free Apple ID
  across all your devices (an Xcode/App Store limit, not an HDHR Open one).
- **Device registration is manual and per-device** — each new iPhone, iPad,
  or Apple TV you want to install on has to go through step 3 above.
- This is a local-only workflow: there's no CI involvement, and nothing here
  produces a distributable build artifact — each install is built straight
  from your own Xcode.

### With a paid Apple Developer Program account

A paid membership ($99/year) removes the 7-day expiry (profiles last a
year) and the 3-app cap, and unlocks ad-hoc/TestFlight distribution so
installs don't require Xcode connected to the device at all. None of this
is wired up yet — the notes below are what a future session would need to
add it, mirroring `android/`'s planned signed-release-build shape
([BUILD-1](../TODO.md)):

- Switch `CODE_SIGN_STYLE` to `Manual` (or keep `Automatic` but pin a
  `DEVELOPMENT_TEAM`) once a paid team ID exists, and add an ad-hoc (or
  App Store) export options plist per target.
- Store the distribution certificate, provisioning profiles, and team ID as
  GitHub Actions secrets rather than relying on a developer's local
  Xcode keychain.
- Add a CI job (parallel to the existing `apple` test job in
  `.github/workflows/ci.yml`) that runs `xcodebuild archive` +
  `xcodebuild -exportArchive` to produce a signed `.ipa`, then publishes it
  to a GitHub Release the same way a future Android release workflow would
  publish a signed `.apk`.
- Decide on TestFlight vs. plain ad-hoc `.ipa` distribution for testers who
  aren't running Xcode themselves.
