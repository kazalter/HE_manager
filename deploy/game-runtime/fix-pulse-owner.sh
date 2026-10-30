#!/usr/bin/with-contenv bash
set -euo pipefail

pulse_config=/config/.config/pulse
if [[ -d "$pulse_config" ]]; then
  chown -R abc:abc -- "$pulse_config"
fi

if [[ -d /defaults ]]; then
  chmod 755 /defaults
fi
