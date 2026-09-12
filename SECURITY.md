# Security Policy

## Supported versions

Only the latest [release](https://github.com/AndyG-0/hdhr-open/releases) is
supported. There are no LTS branches — update to the newest tag to pick up
security fixes.

## Reporting a vulnerability

Please report security issues privately using
[GitHub's private vulnerability reporting](https://github.com/AndyG-0/hdhr-open/security/advisories/new)
(Security tab → "Report a vulnerability") rather than opening a public issue.

## Known, by-design security posture

The README's [Network exposure](README.md#network-exposure) section
documents caveats that are known and intentional trade-offs for a
self-hosted LAN app, not bugs to report:

- There is no authentication in front of the HTTP server beyond the app's
  own PIN-based profile login.
- The optional DVR SSH connection does not pin host keys.

If you believe either of these has a concrete exploitable impact beyond
what's described there, or you've found something else, please still report
it — but read that section first.
