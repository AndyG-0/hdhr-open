# HDHR Open

A self-hosted server and web client for watching and recording live TV
through an [HDHomeRun](https://www.silicondust.com/) network tuner. Point it
at your tuner, get a channel guide and live player in your browser, and
(optionally) record shows through a self-hosted DVR engine or SiliconDust's
official DVR service.

This is not a general-purpose dashboard — it does one thing: HDHomeRun
guide, playback, and recording.

New here? Start with **[Installation](installation.md)**.

## Features

- **Live guide + player** — channel lineup with program info, tune in with
  one click. Playback works either by transcoding server-side to H.264
  (works with any tuner but costs CPU per viewer) or by handing a raw stream
  link to an external player like VLC. See [Usage](usage.md).
- **Live playback controls** — a Go Live button returns to the live edge of
  an in-progress channel or recording, with live-edge join, a playback stats
  panel, and automatic quality downgrade for single-viewer live TV.
- **Commercial detection** — marks commercial breaks in completed
  recordings, with an opt-in auto-skip in the player. See
  [DVR Guide → Commercial detection](dvr.md#commercial-detection).
- **Optional hardware-accelerated transcoding** — VAAPI/Quick Sync/NVENC
  support with a built-in diagnostics page to verify GPU access before
  relying on it. See [Hardware Acceleration](hardware-acceleration.md).
- **DVR** — dual-engine recording support with either HDHR Open's built-in
  self-hosted DVR or SiliconDust's official HDHomeRun DVR engine, with
  automatic fallback and guide-matching across providers. See
  [DVR Guide](dvr.md).
- **Multi-user profiles** — PIN-protected household profiles with
  admin/member roles, one browser session per device.
- **Multi-language UI** — English, Spanish, French, German.

## Project links

- [Source code on GitHub](https://github.com/AndyG-0/hdhr-open)
- [Latest release](https://github.com/AndyG-0/hdhr-open/releases/latest)
- [Native apps (Android / iOS / tvOS) status](native-apps.md)
- [Security policy](https://github.com/AndyG-0/hdhr-open/blob/main/SECURITY.md)

## License

MIT — see
[LICENSE](https://github.com/AndyG-0/hdhr-open/blob/main/LICENSE).
