#!/bin/bash
set -euo pipefail

curl --location \
  https://raw.githubusercontent.com/sigstore/root-signing/refs/heads/main/targets/trusted_root.json \
  --output trusted_root.json

curl --location \
  https://github.com/sigstore/cosign/releases/download/v3.1.3/cosign-linux-amd64 \
  --output cosign

chmod a+x cosign
