#!/bin/bash
set -euo pipefail

# Validate required environment
if [[ -z "${TRIGGER_ID:-}" ]]; then
    echo "ERROR: TRIGGER_ID environment variable is required" >&2
    echo "Usage: docker run -e TRIGGER_ID=<Fermi GBM Trigger ID (e.g. bn080916009)> -v /host/output:/opt/output <image>" >&2
    exit 2
fi

# Validate Fermi GBM trigger ID format: bnYYMMDDNNN
if [[ ! "${TRIGGER_ID}" =~ ^bn[0-9]{6}[0-9]{3}$ ]]; then
    echo "ERROR: TRIGGER_ID must be a valid Fermi GBM trigger ID (format: bnYYMMDDNNN, e.g. bn080916009)" >&2
    exit 4
fi

# Validate output directory
if [[ ! -d "/opt/output" ]]; then
    echo "ERROR: /opt/output directory not found. Mount a volume to /opt/output" >&2
    exit 3
fi
# Ensure writable by current user
if [[ ! -w "/opt/output" ]]; then
    # Try to fix permissions if we're root
    if [[ "$(id -u)" == "0" ]]; then
        chown -R "$(id -u):$(id -g)" /opt/output 2>/dev/null || true
    else
        # Not root - try to make it writable using chmod if we have permission
        chmod u+w /opt/output 2>/dev/null || true
    fi
    # Final check
    if [[ ! -w "/opt/output" ]]; then
        echo "ERROR: /opt/output is not writable by current user ($(id -un))" >&2
        echo "Try running with: docker run --user root ..." >&2
        exit 3
    fi
fi

# Export for Python
export TRIGGER_ID
export OUTPUT_DIR="/opt/output"
export PYTHONUNBUFFERED=1
export MPLBACKEND=Agg

# exec "$@" allows CMD to specify the command
exec "$@"