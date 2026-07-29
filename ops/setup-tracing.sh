#!/usr/bin/env bash
# Install and configure the in-region tracing stack (otelcol + Jaeger).
# Idempotent — safe to run on an already-instrumented box.
set -euo pipefail

JAEGER_VER="1.67.0"
OTELCOL_VER="0.127.0"
ARCH="linux_amd64"

echo "=== Setting up in-region tracing ==="

# --- Jaeger all-in-one ---
if [ ! -x /opt/saathi-jaeger/jaeger-all-in-one ]; then
    echo "Installing Jaeger ${JAEGER_VER}..."
    sudo mkdir -p /opt/saathi-jaeger/data /opt/saathi-jaeger/key
    curl -fsSL "https://github.com/jaegertracing/jaeger/releases/download/v${JAEGER_VER}/jaeger-${JAEGER_VER}-${ARCH}.tar.gz" \
        -o /tmp/jaeger.tgz
    tar xzf /tmp/jaeger.tgz -C /tmp
    sudo cp "/tmp/jaeger-${JAEGER_VER}-${ARCH}/jaeger-all-in-one" /opt/saathi-jaeger/
    sudo chmod +x /opt/saathi-jaeger/jaeger-all-in-one
    sudo chown -R ubuntu:ubuntu /opt/saathi-jaeger
    rm -rf /tmp/jaeger.tgz "/tmp/jaeger-${JAEGER_VER}-${ARCH}"
    echo "Jaeger installed."
else
    echo "Jaeger already installed."
fi

# --- OTel Collector (contrib) ---
if [ ! -x /opt/saathi-otelcol/otelcol ]; then
    echo "Installing OTel Collector ${OTELCOL_VER}..."
    sudo mkdir -p /opt/saathi-otelcol
    curl -fsSL "https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v${OTELCOL_VER}/otelcol_${OTELCOL_VER}_${ARCH}.tar.gz" \
        -o /tmp/otelcol.tgz
    tar xzf /tmp/otelcol.tgz -C /tmp
    sudo cp /tmp/otelcol /opt/saathi-otelcol/otelcol
    sudo chmod +x /opt/saathi-otelcol/otelcol
    sudo chown -R ubuntu:ubuntu /opt/saathi-otelcol
    rm -rf /tmp/otelcol.tgz /tmp/otelcol
    echo "OTel Collector installed."
else
    echo "OTel Collector already installed."
fi

# --- Collector config ---
sudo tee /opt/saathi-otelcol/config.yaml > /dev/null << CONFEOF
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 127.0.0.1:4317

processors:
  batch:
    timeout: 5s
    send_batch_size: 100

exporters:
  otlp/jaeger:
    endpoint: 127.0.0.1:4318
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp/jaeger]
CONFEOF
sudo chown ubuntu:ubuntu /opt/saathi-otelcol/config.yaml
echo "Collector config written."

# --- Install systemd units ---
sudo cp ops/saathi-otelcol.service /etc/systemd/system/
sudo cp ops/saathi-jaeger.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable saathi-jaeger saathi-otelcol
sudo systemctl restart saathi-jaeger saathi-otelcol

echo "=== Tracing stack installed and started ==="
echo "Jaeger UI: ssh -L 16686:localhost:16686 saathi-ai → http://localhost:16686"
