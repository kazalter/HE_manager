#!/usr/bin/with-contenv bash
set -euo pipefail

pulse_config=/config/.config/pulse
if [[ -d "$pulse_config" ]]; then
  chown -R abc:abc -- "$pulse_config"
fi
