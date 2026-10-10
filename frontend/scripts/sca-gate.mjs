#!/usr/bin/env node
// Software composition analysis (SCA) gate for the frontend's npm
// dependency tree.
//
// Policy: only fail CI when `npm audit` reports a fix that can be applied
// by updating a direct/top-level dependency itself (`fixAvailable: true`,
// or `fixAvailable` as an object naming a top-level package to bump — npm
// only ever uses that object form to name a *direct* dependency, never an
// isolated transitive override). Never fail CI when the only path npm
// found requires forcing an unrelated transitive (child) dependency's
// version while leaving the direct dependency unchanged — npm reports that
// case as `fixAvailable: false`, meaning it found no fix path through the
// graph without an unsupported forced override. Those are reported
// (visible, non-blocking) instead, since forcing a child dependency's
// version out from under its untested parent is a risky combination this
// project doesn't want to gate on.
//
// Exception list: some findings technically have a "direct dependency" fix
// per the rule above, but that fix has been evaluated and found unsafe to
// apply right now (e.g. it cascades into an unrelated major-framework
// migration, or the fix target is actually a downgrade). Rather than
// special-casing those in this script, `sca-exceptions.json` (next to this
// script's parent directory) is a standing, reusable override list: each
// entry names a GHSA advisory id and a documented reason, and any finding
// whose advisory chain matches an entry is reported separately as EXEMPTED
// instead of blocking. This is deliberately visible, not silent — exempted
// findings are still printed on every run, and an exception that stops
// matching anything (the finding got fixed upstream) is flagged as stale so
// it doesn't linger unreviewed.
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const EXCEPTIONS_PATH = path.join(SCRIPT_DIR, "..", "sca-exceptions.json");

function loadExceptions() {
  let raw;
  try {
    raw = readFileSync(EXCEPTIONS_PATH, "utf8");
  } catch (err) {
    if (err.code === "ENOENT") {
      return [];
    }
    throw err;
  }

  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (err) {
    throw new Error(`Failed to parse ${EXCEPTIONS_PATH}: ${err.message}`, { cause: err });
  }

  if (!Array.isArray(parsed)) {
    throw new Error(`${EXCEPTIONS_PATH} must be a JSON array of exception entries.`);
  }
  for (const entry of parsed) {
    if (!entry.id || !entry.reason) {
      throw new Error(
        `${EXCEPTIONS_PATH} has an entry missing a required "id" or "reason" field: ${JSON.stringify(entry)}`,
      );
    }
  }
  return parsed;
}

const GHSA_RE = /GHSA-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}/i;

// A vulnerability entry's `via` array either names advisory objects
// directly (leaf packages, e.g. "cookie") or names other package strings
// that are themselves keys into `vulnerabilities` (direct/intermediate
// packages, e.g. "@sveltejs/kit" -> via: ["cookie"]). Walk through string
// references to collect every GHSA id anywhere in the chain, so exempting
// one advisory exempts every package entry npm derived from it.
function collectAdvisoryIds(entry, vulnerabilities, seen = new Set()) {
  const ids = new Set();
  for (const via of entry.via ?? []) {
    if (typeof via === "string") {
      if (seen.has(via)) continue;
      seen.add(via);
      const child = vulnerabilities[via];
      if (child) {
        for (const id of collectAdvisoryIds(child, vulnerabilities, seen)) {
          ids.add(id);
        }
      }
    } else if (via?.url) {
      const match = GHSA_RE.exec(via.url);
      if (match) {
        ids.add(match[0].toUpperCase());
      }
    }
  }
  return ids;
}

function runNpmAudit() {
  // `npm audit` exits non-zero whenever it finds vulnerabilities — that's
  // normal and expected, not a failure of this script. Its JSON report is
  // still written to stdout regardless of exit code, so always parse
  // stdout and ignore the exit status here.
  const result = spawnSync("npm", ["audit", "--json"], {
    encoding: "utf8",
    maxBuffer: 1024 * 1024 * 64,
  });

  if (result.error) {
    throw result.error;
  }

  const stdout = result.stdout?.trim();
  if (!stdout) {
    const stderr = result.stderr?.trim();
    throw new Error(
      `npm audit produced no output on stdout to parse.${stderr ? ` stderr: ${stderr}` : ""}`,
    );
  }

  try {
    return JSON.parse(stdout);
  } catch (err) {
    throw new Error(`Failed to parse npm audit JSON output: ${err.message}`, { cause: err });
  }
}

function describeFixTarget(fixAvailable) {
  if (fixAvailable === true) {
    return "automatic (npm audit fix)";
  }
  if (fixAvailable && typeof fixAvailable === "object") {
    const { name, version, isSemVerMajor } = fixAvailable;
    const majorNote = isSemVerMajor ? ", semver-major" : "";
    return `update ${name}@${version}${majorNote}`;
  }
  return "none";
}

function main() {
  const audit = runNpmAudit();
  const vulnerabilities = audit.vulnerabilities ?? {};
  const exceptions = loadExceptions();
  const exceptionsById = new Map(exceptions.map((e) => [e.id.toUpperCase(), e]));
  const usedExceptionIds = new Set();

  const blocking = [];
  const reportOnly = [];
  const exempted = [];

  for (const [pkgName, info] of Object.entries(vulnerabilities)) {
    const { severity, fixAvailable } = info;
    const entry = { name: pkgName, severity, fixAvailable };

    const advisoryIds = collectAdvisoryIds(info, vulnerabilities);
    const matchedException = [...advisoryIds]
      .map((id) => exceptionsById.get(id))
      .find((e) => e !== undefined);

    if (matchedException) {
      usedExceptionIds.add(matchedException.id.toUpperCase());
      exempted.push({ ...entry, exception: matchedException });
      continue;
    }

    // fixAvailable === false => npm itself found no fix path through the
    // dependency graph without an unsupported forced override of a
    // transitive dependency. Anything else (true, or the top-level-naming
    // object form) is a real, safe fix path through a direct dependency.
    if (fixAvailable !== false) {
      blocking.push(entry);
    } else {
      reportOnly.push(entry);
    }
  }

  console.log("=== SCA Gate: frontend (npm audit) ===\n");

  console.log(`BLOCKING (direct fix available) — ${blocking.length} package(s)`);
  if (blocking.length === 0) {
    console.log("  (none)");
  } else {
    for (const { name, severity, fixAvailable } of blocking) {
      console.log(`  - ${name} [${severity}] -> fix: ${describeFixTarget(fixAvailable)}`);
    }
  }

  console.log(
    `\nREPORT ONLY (no safe fix without forcing a child dependency) — ${reportOnly.length} package(s)`,
  );
  if (reportOnly.length === 0) {
    console.log("  (none)");
  } else {
    for (const { name, severity } of reportOnly) {
      console.log(`  - ${name} [${severity}] -> no fix available through the dependency graph`);
    }
  }

  console.log(`\nEXEMPTED (covered by sca-exceptions.json) — ${exempted.length} package(s)`);
  if (exempted.length === 0) {
    console.log("  (none)");
  } else {
    for (const { name, severity, exception } of exempted) {
      console.log(`  - ${name} [${severity}] -> exempted by ${exception.id} (added ${exception.addedDate} by ${exception.addedBy})`);
      console.log(`      reason: ${exception.reason}`);
    }
  }

  const staleExceptions = exceptions.filter((e) => !usedExceptionIds.has(e.id.toUpperCase()));
  if (staleExceptions.length > 0) {
    console.log(`\nWARNING: ${staleExceptions.length} exception(s) in sca-exceptions.json matched no current finding — the underlying issue may already be fixed upstream. Consider removing:`);
    for (const e of staleExceptions) {
      console.log(`  - ${e.id} (${e.package})`);
    }
  }

  console.log("");

  if (blocking.length > 0) {
    console.error(
      `SCA gate FAILED: ${blocking.length} package(s) have a fix available by updating a direct dependency.`,
    );
    process.exit(1);
  }

  console.log("SCA gate passed (report-only and exempted findings, if any, do not block CI).");
  process.exit(0);
}

main();
