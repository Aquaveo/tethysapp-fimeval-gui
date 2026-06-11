#!/usr/bin/env bash
# Build the React SPA into tethysapp/fimeval_gui/public/frontend.
# Invoked by install.yml's `post:` hook on `tethys install`, which runs this via
# Popen(path, shell=True) with no working directory — so locate ourselves and
# never rely on cwd.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/../reactapp"

npm ci
npm run build
