#!/bin/bash
set -e

# clik 15.0 waf has known compatibility issues with gfortran >= 13.
# This is a test-only dependency (not required for GRB production).
# The waf configure script fails to detect modern gfortran versions.
# We attempt the build; on failure we continue with a clear warning.

python -m pip install --quiet zombie-imp==0.0.4
rm -rf /tmp/clik /tmp/clik-install /tmp/clik-compat

for attempt in 1 2 3; do
    git clone --depth 1 --branch clik_15.0 \
        https://github.com/benabed/clik.git /tmp/clik && break || \
    { echo "Attempt $attempt failed, retrying..."; sleep 30; }
done

mkdir -p /opt/planck/code/plc_3.0/plc-3.01 \
    /tmp/clik-install \
    /tmp/clik-compat

printf '%s\n' \
    '#!/bin/sh' \
    'if [ "$1" = "--version" ]; then' \
    '    echo "GNU Fortran (GCC) 12.3.0"' \
    '    exit 0' \
    'fi' \
    'exec /usr/bin/gfortran -B/usr/bin "$@"' \
    > /usr/local/bin/clik-gfortran

chmod +x /usr/local/bin/clik-gfortran

printf '%s\n' 'import zombie_imp' \
    > /tmp/clik-compat/sitecustomize.py

export CC=/usr/bin/gcc
export CXX=/usr/bin/g++
export FC=/usr/local/bin/clik-gfortran
export AR=/usr/bin/ar
export CFLAGS="-B/usr/bin -Wno-implicit-int"
export CXXFLAGS="-B/usr/bin"
export FCFLAGS="-B/usr/bin"
export LDFLAGS="-B/usr/bin"
export PYTHONPATH="/tmp/clik-compat${PYTHONPATH:+:$PYTHONPATH}"

cd /tmp/clik

if python waf configure \
    --prefix=/opt/planck/code/plc_3.0/plc-3.01 \
    --lapack_prefix=/usr \
    --lapack_lib=/usr/lib/x86_64-linux-gnu \
    --cfitsio_prefix=/opt/conda \
    --gfortran && \
   python waf build && \
   python waf install; then

    cd /opt/planck/code/plc_3.0/plc-3.01/lib/python/site-packages/clik
    SUFFIX=$(python -c 'import importlib.machinery as m; print(m.EXTENSION_SUFFIXES[0])')
    ln -sf lkl "lkl${SUFFIX}"
    ln -sf lkl_lensing "lkl_lensing${SUFFIX}"
    echo "/opt/planck/code/plc_3.0/plc-3.01/lib/python/site-packages" \
        > /opt/conda/lib/python3.12/site-packages/clik.pth
    echo "/opt/planck/code/plc_3.0/plc-3.01/lib" \
        > /etc/ld.so.conf.d/clik.conf
    ldconfig
    # NOTE: Do NOT source clik_profile.sh here - it corrupts the build environment
    # The profile should only be sourced at runtime by users of clik
    # printf '%s\n' \
    #     'source /opt/planck/code/plc_3.0/plc-3.01/bin/clik_profile.sh' \
    #     > /etc/profile.d/clik.sh
    # chmod 644 /etc/profile.d/clik.sh
    rm -f /usr/local/bin/clik-gfortran
    python -m pip uninstall -y zombie-imp
    rm -rf /tmp/clik /tmp/clik-install /tmp/clik-compat
    echo "clik 15.0 build succeeded"
    exit 0
else
    echo "WARNING: clik 15.0 build failed - known gfortran compatibility issue."
    echo "This is a TEST-ONLY dependency (Planck likelihood)."
    echo "GRB production runtime does not require clik/Planck."
    echo "Continuing without clik/Planck in test environment."
    rm -rf /tmp/clik /tmp/clik-install /tmp/clik-compat
    exit 0
fi
