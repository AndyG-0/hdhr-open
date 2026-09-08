#!/usr/bin/env python3
"""Resolve an `xcodebuild -destination` simulator argument for a given platform.

Never hardcode a simulator name in CI/check.sh: the exact device inventory on a
given macOS runner image can differ from a local machine. This script queries
`xcrun simctl list devices available -j`, prefers a named device if available,
and otherwise falls back to any available, non-shutdown-incapable simulator for
the requested platform's runtime family.

Usage:
  resolve_destination.py ios [--prefer "iPhone 17 Pro"]
  resolve_destination.py tvos [--prefer "Apple TV 4K (3rd generation)"]

Prints a ready-to-use `platform=...,name=...` destination string to stdout.
"""

import argparse
import json
import subprocess
import sys

PLATFORM_RUNTIME_PREFIX = {
    "ios": "com.apple.CoreSimulator.SimRuntime.iOS",
    "tvos": "com.apple.CoreSimulator.SimRuntime.tvOS",
}

PLATFORM_LABEL = {
    "ios": "iOS Simulator",
    "tvos": "tvOS Simulator",
}

DEFAULT_PREFER = {
    "ios": "iPhone 17 Pro",
    "tvos": "Apple TV 4K (3rd generation)",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("platform", choices=["ios", "tvos"])
    parser.add_argument("--prefer", default=None, help="preferred device name; falls back if unavailable")
    args = parser.parse_args()

    prefer = args.prefer or DEFAULT_PREFER[args.platform]
    runtime_prefix = PLATFORM_RUNTIME_PREFIX[args.platform]

    result = subprocess.run(
        ["xcrun", "simctl", "list", "devices", "available", "-j"],
        capture_output=True, text=True, check=True,
    )
    devices_by_runtime = json.loads(result.stdout)["devices"]

    candidates = []
    for runtime, devices in devices_by_runtime.items():
        if not runtime.startswith(runtime_prefix):
            continue
        for device in devices:
            if device.get("isAvailable", False):
                candidates.append(device["name"])

    if not candidates:
        print(f"error: no available {args.platform} simulators found", file=sys.stderr)
        return 1

    chosen = prefer if prefer in candidates else candidates[0]
    print(f"platform={PLATFORM_LABEL[args.platform]},name={chosen}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
