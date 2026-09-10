#!/usr/bin/env bash
# HDHR Open self-restart wrapper.  Granted to the hdhr-open service user via
# /etc/sudoers.d/hdhr-open-restart (written by deploy/install.sh) so that
# the backend process can trigger a service restart without broad sudo
# access.  Only allowed by the exact sudoers rule — do not add any
# functionality here; keep this as a one-liner.
exec systemctl restart hdhr-open-backend.service hdhr-open-frontend.service
