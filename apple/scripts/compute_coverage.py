#!/usr/bin/env python3
"""Combine HDHROpenKit + HDHROpeniOS + HDHROpenTV line coverage and gate at a threshold.

Reads three independently-produced coverage reports and sums covered/executable
lines across all of them (weighted by line count, not an average of percentages),
so that Kit's larger source tree carries proportionally more weight than either
thin app target. Prints a per-target breakdown plus the combined result, and
exits non-zero if the combined percentage is below --threshold.

Inputs:
  --kit-json      llvm-cov export JSON for HDHROpenKit (from `xcrun llvm-cov export`)
  --ios-json      xccov report JSON for the HDHROpeniOS scheme (from `xcrun xccov view --report --json`)
  --tv-json       xccov report JSON for the HDHROpenTV scheme (same tool)
  --ios-target    name of the app target inside the iOS xccov report (default: HDHROpeniOS.app)
  --tv-target     name of the app target inside the tvOS xccov report (default: HDHROpenTV.app)
  --threshold     minimum combined line-coverage percentage required (default: 80.0)
"""

import argparse
import json
import sys


def kit_totals(kit_json_path):
    with open(kit_json_path) as f:
        data = json.load(f)
    files = data["data"][0]["files"]
    covered = 0
    executable = 0
    per_file = []
    for f in files:
        if "/Sources/HDHROpenKit/" not in f["filename"]:
            continue
        lines = f["summary"]["lines"]
        covered += lines["covered"]
        executable += lines["count"]
        per_file.append((f["filename"].rsplit("/Sources/HDHROpenKit/", 1)[-1], lines["covered"], lines["count"]))
    return covered, executable, per_file


def xccov_target_totals(xccov_json_path, target_name):
    with open(xccov_json_path) as f:
        data = json.load(f)
    for target in data["targets"]:
        if target["name"] == target_name:
            per_file = [(f["name"], f["coveredLines"], f["executableLines"]) for f in target["files"]]
            return target["coveredLines"], target["executableLines"], per_file
    available = ", ".join(t["name"] for t in data["targets"])
    raise SystemExit(f"target '{target_name}' not found in {xccov_json_path} (available: {available})")


def pct(covered, executable):
    return (covered / executable * 100.0) if executable else 100.0


def print_breakdown(label, covered, executable, per_file, show_lowest=5):
    print(f"\n{label}: {covered}/{executable} lines ({pct(covered, executable):.2f}%)")
    lowest = sorted(per_file, key=lambda t: pct(t[1], t[2]))[:show_lowest]
    for name, c, e in lowest:
        print(f"    lowest: {name:<45s} {pct(c, e):6.2f}%  ({c}/{e})")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--kit-json", required=True)
    parser.add_argument("--ios-json", required=True)
    parser.add_argument("--tv-json", required=True)
    parser.add_argument("--ios-target", default="HDHROpeniOS.app")
    parser.add_argument("--tv-target", default="HDHROpenTV.app")
    parser.add_argument("--threshold", type=float, default=80.0)
    args = parser.parse_args()

    kit_covered, kit_exec, kit_files = kit_totals(args.kit_json)
    ios_covered, ios_exec, ios_files = xccov_target_totals(args.ios_json, args.ios_target)
    tv_covered, tv_exec, tv_files = xccov_target_totals(args.tv_json, args.tv_target)

    print_breakdown("HDHROpenKit", kit_covered, kit_exec, kit_files)
    print_breakdown("HDHROpeniOS", ios_covered, ios_exec, ios_files)
    print_breakdown("HDHROpenTV", tv_covered, tv_exec, tv_files)

    total_covered = kit_covered + ios_covered + tv_covered
    total_exec = kit_exec + ios_exec + tv_exec
    combined = pct(total_covered, total_exec)

    print(f"\nCombined: {total_covered}/{total_exec} lines ({combined:.2f}%)")
    print(f"Threshold: {args.threshold:.2f}%")

    if combined < args.threshold:
        print(f"\nFAIL: combined coverage {combined:.2f}% is below the {args.threshold:.2f}% threshold.")
        return 1

    print(f"\nPASS: combined coverage {combined:.2f}% meets the {args.threshold:.2f}% threshold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
