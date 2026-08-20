#!/usr/bin/with-contenv bashio
set -e

MEDIAHUB_AUTH_MODE=ingress uvicorn app.runtime:app \
  --host 0.0.0.0 \
  --port 8099 \
  --no-proxy-headers &
ingress_pid=$!

MEDIAHUB_AUTH_MODE=external uvicorn app.runtime:app \
  --host 0.0.0.0 \
  --port 8100 \
  --no-proxy-headers &
external_pid=$!

shutdown() {
  kill "${ingress_pid}" "${external_pid}" 2>/dev/null || true
  wait "${ingress_pid}" "${external_pid}" 2>/dev/null || true
}

trap shutdown EXIT INT TERM
wait -n "${ingress_pid}" "${external_pid}"
