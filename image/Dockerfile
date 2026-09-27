# Prediction of host masses from GRB X-ray afterglows
# you need to pass the environment variable $TRIGGER_ID = Fermi GBM Trigger ID
# and mount /opt/output/ to a directory

# syntax=docker/dockerfile:1.7
# BuildKit multi-stage build for space-of-inference-spaces GRB production
FROM continuumio/miniconda3:latest AS builder

LABEL description="space-of-inference-spaces builder"

# ---------------------------------------------------------------------------
# 1) SYSTEM BUILD DEPENDENCIES
# ---------------------------------------------------------------------------
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update -y && \
    apt-get install -y --no-install-recommends \
        git \
        build-essential \
        gfortran \
        libblas-dev \
        liblapack-dev \
        wget \
        curl \
        ca-certificates \
        cmake && \
    rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# 2) BUILD MULTINEST (for test stage)
# ---------------------------------------------------------------------------
RUN git clone --depth 1 --branch v3.10 \
        https://github.com/JohannesBuchner/MultiNest.git && \
    cd MultiNest/build && \
    cmake .. && \
    make && \
    make install && \
    cd /root && \
    rm -rf MultiNest

RUN echo "/usr/local/lib" > /etc/ld.so.conf.d/multinest.conf && \
    ldconfig

# ---------------------------------------------------------------------------
# 3) FULL SCIENTIFIC ENVIRONMENT (for test stage)
# ---------------------------------------------------------------------------
RUN --mount=type=cache,target=/opt/conda/pkgs,sharing=locked \
    conda install -y \
        -c conda-forge \
        "python=3.12.14" \
        mamba && \
    conda clean --all -y

RUN --mount=type=cache,target=/opt/conda/pkgs,sharing=locked \
    mamba install -y \
        -c conda-forge \
        -c fermi \
        fermitools=2.5.3 && \
    mamba clean --all -y

RUN curl -LsSf https://astral.sh/uv/0.12.18/install.sh | sh

ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /root

# ---------------------------------------------------------------------------
# 4) MAIN SCIENTIFIC PYTHON STACK (full environment for test stage)
# ---------------------------------------------------------------------------
RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    conda run -n base /root/.local/bin/uv pip install --system \
        numpy==2.3.5 \
        scipy==1.16.3 \
        astropy==8.0.1 \
        matplotlib==3.11.2 \
        healpy==1.20.0 \
        "gammapy>=2.1,<2.2" \
        "regions<0.12" \
        astromodels==2.6.0 \
        threeML==2.6.1 \
        ultranest==4.5.2 \
        pymultinest \
        llvmlite \
        numba \
        h5py \
        fermipy==1.4.2

# ---------------------------------------------------------------------------
# 5) ADDITIONAL PYTHON PACKAGES (for test stage)
# ---------------------------------------------------------------------------
RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    conda run -n base /root/.local/bin/uv pip install --system \
        corner \
        getdist \
        joblib \
        mosfit \
        decorator \
        "fast-histogram>=0.10" \
        nlopt \
        iminuit \
        "pint<=0.19" \
        pandas \
        simplejson \
        tables \
        tabulate \
        uncertainties \
        py-cpuinfo \
        sympy \
        cython

# ---------------------------------------------------------------------------
# 6) FERMITOOLS ENVIRONMENT
# ---------------------------------------------------------------------------
ENV CALDB=/opt/conda/share/fermitools/data/caldb/
ENV IRF=P8R3_SOURCE_V2
ENV FERMITOOLS=/opt/conda/share/fermitools
ENV FERMI_DIR=/opt/conda/share/fermitools/
ENV PFILES=/opt/conda/share/fermitools/syspfiles/

RUN mkdir -p /refdata/fermi && \
    cd /refdata/fermi && \
    ln -s /opt/conda/share/fermitools/data/caldb/ caldb && \
    ln -s /refdata/fermi refdata

# ---------------------------------------------------------------------------
# 7) ULTRANEST SAMPLER SHIM FOR THREEML
# ---------------------------------------------------------------------------
COPY ultranest_sampler.py /tmp/

RUN /opt/conda/bin/python -c "import threeML; import os; import shutil; THREEML_PATH = os.path.dirname(threeML.__file__); dest = os.path.join(THREEML_PATH, 'bayesian', 'ultranest_sampler.py'); shutil.copy('/tmp/ultranest_sampler.py', dest); print('THREEML_PATH:', THREEML_PATH); print('Copied ultranest_sampler.py to', dest)"

# ---------------------------------------------------------------------------
# 8) CLASS / COSMOLOGY (test stage)
# ---------------------------------------------------------------------------
RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    conda run -n base /root/.local/bin/uv pip install --system classy

RUN cd /opt/conda/lib/python3.12/site-packages/classy && \
    make libclass.a

RUN cd /opt/conda/lib/python3.12/site-packages/classy/python && \
    conda run -n base python setup.py build

RUN /opt/conda/bin/python -c "import classy; from classy import Class; cosmo = Class(); cosmo.set({'output': 'tCl,pCl,lCl,mPk', 'lensing': 'yes', 'h': 0.67, 'omega_b': 0.0224, 'omega_cdm': 0.12, 'A_s': 2.1e-9, 'n_s': 0.965, 'tau_reio': 0.06}); cosmo.compute(); print('CLASS DIRECT: OK'); cosmo.struct_cleanup(); cosmo.empty()"

# ---------------------------------------------------------------------------
# 9) PLANCK LIKELIHOOD - CLIK 15.0 (test stage)
# ---------------------------------------------------------------------------
# clik 15.0 waf has known compatibility issues with gfortran >= 13.
# This is a test-only dependency (not required for GRB production).
# The waf configure script fails to detect modern gfortran versions.
# We attempt the build; on failure we continue with a clear warning.
COPY build_clik.sh /tmp/build_clik.sh
RUN chmod +x /tmp/build_clik.sh && /tmp/build_clik.sh
# NOTE: CLIK_PATH and PATH for clik are set in TEST stage only
# to avoid corrupting builder environment

# ---------------------------------------------------------------------------
# 10) PLANCK BASELINE LIKELIHOOD DATA (test stage)
# ---------------------------------------------------------------------------
# Download before clik build to avoid environment corruption from clik build
RUN mkdir -p /opt/planck && \
    cd /opt/planck && \
    for attempt in 1 2 3; do \
        wget -q --show-progress --timeout=300 --tries=3 \
            "https://pla.esac.esa.int/pla/aio/product-action?COSMOLOGY.FILE_ID=COM_Likelihood_Data-baseline_R3.00.tar.gz" \
            -O COM_Likelihood_Data-baseline_R3.00.tar.gz && break || \
        { echo "Attempt $attempt failed, retrying..."; sleep 30; }; \
    done && \
    tar -xzf COM_Likelihood_Data-baseline_R3.00.tar.gz && \
    rm -f COM_Likelihood_Data-baseline_R3.00.tar.gz

RUN test -d /opt/planck/baseline/plc_3.0 && \
    test -d /opt/planck/baseline/plc_3.0/hi_l/plik/plik_rd12_HM_v22b_TTTEEE.clik && \
    test -d /opt/planck/baseline/plc_3.0/low_l/simall/simall_100x143_offlike5_EE_Aplanck_B.clik && \
    test -d /opt/planck/baseline/plc_3.0/low_l/commander/commander_dx12_v3_2_29.clik

# ---------------------------------------------------------------------------
# 11) MONTEPYTHON (test stage)
# ---------------------------------------------------------------------------
RUN for attempt in 1 2 3; do \
        git clone --depth 1 \
            https://github.com/JohannesBuchner/montepython_public/ && break || \
        { echo "Attempt $attempt failed, retrying..."; sleep 30; }; \
    done

RUN printf '%s\n' \
    "root = '/opt/conda/lib/python3.12/site-packages'" \
    "" \
    "path['cosmo'] = root + '/classy'" \
    "path['clik'] = '/opt/planck/code/plc_3.0/plc-3.01/'" \
    > /root/montepython_public/default.conf

COPY fix_montepython.py /tmp/fix_montepython.py

RUN cd /root/montepython_public && python /tmp/fix_montepython.py

RUN cd /root/montepython_public && \
    conda run -n base python montepython/MontePython.py --help && \
    cd -

# ---------------------------------------------------------------------------
# 12) PISA / PYCBC / COBAYA / SNOWLINE / JULIET (test stage)
# ---------------------------------------------------------------------------
RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    conda run -n base /root/.local/bin/uv pip install --system \
        git+https://github.com/icecube/pisa \
        pycbc \
        snowline \
        cobaya \
        juliet

RUN --mount=type=cache,target=/root/.cache/uv,sharing=locked \
    conda run -n base /root/.local/bin/uv pip install --system \
        "gammapy>=2.1,<2.2" \
        "regions<0.12"

RUN /opt/conda/bin/python -c "import gammapy, regions; print('Final Gammapy:', gammapy.__version__); print('Final regions:', regions.__version__); from gammapy.maps import Map; print('Final Gammapy import: OK')"

# ---------------------------------------------------------------------------
# 13) POSTERIORSTACKER (test stage)
# ---------------------------------------------------------------------------
RUN for attempt in 1 2 3; do \
        git clone --depth 1 \
            https://github.com/JohannesBuchner/PosteriorStacker && break || \
        { echo "Attempt $attempt failed, retrying..."; sleep 30; }; \
    done

RUN cd PosteriorStacker && \
    conda run -n base python posteriorstacker.py --help && \
    cd -

# ---------------------------------------------------------------------------
# 14) CIAO / SHERPA / BXA (test stage)
# ---------------------------------------------------------------------------
RUN --mount=type=cache,target=/opt/conda/pkgs,sharing=locked \
    for attempt in 1 2 3; do \
        mamba create -n ciao -y \
            -c https://cxc.cfa.harvard.edu/conda/ciao \
            -c conda-forge \
            "numpy<=2.3.5" \
            ciao \
            sherpa \
            bxa && break || \
        { echo "Attempt $attempt failed, retrying..."; sleep 30; }; \
    done && \
    mamba clean --all -y

RUN conda run -n ciao python -c "import numpy; print('CIAO NumPy:', numpy.__version__)"
RUN conda run -n ciao python -c "import sherpa; print('Sherpa: OK')"

# ---------------------------------------------------------------------------
# 15) BXA REPOSITORY (test stage)
# ---------------------------------------------------------------------------
RUN for attempt in 1 2 3; do \
        git clone --depth 1 \
            https://github.com/JohannesBuchner/BXA.git && break || \
        { echo "Attempt $attempt failed, retrying..."; sleep 30; }; \
    done

# ---------------------------------------------------------------------------
# 16) DOWNLOAD BXA EXAMPLE FITS DATA (test stage)
# ---------------------------------------------------------------------------
RUN mkdir -p BXA/examples/sherpa && \
    for attempt in 1 2 3; do \
        wget -q --show-progress --timeout=300 --tries=3 \
            "https://zenodo.org/records/1169181/files/uxclumpy-cutoff.fits?download=1" \
            -O BXA/examples/sherpa/uxclumpy-cutoff.fits && break || \
        { echo "Attempt $attempt failed, retrying..."; sleep 30; }; \
    done && \
    for attempt in 1 2 3; do \
        wget -q --show-progress --timeout=300 --tries=3 \
            "https://zenodo.org/records/1169181/files/uxclumpy-cutoff-omni.fits?download=1" \
            -O BXA/examples/sherpa/uxclumpy-cutoff-omni.fits && break || \
        { echo "Attempt $attempt failed, retrying..."; sleep 30; }; \
    done && \
    echo "9bdffd414a74f6c327032fb5274d8406  BXA/examples/sherpa/uxclumpy-cutoff.fits" | \
        md5sum -c - && \
    echo "6dc751d3e4a9da2a41c5f01beca5bd91  BXA/examples/sherpa/uxclumpy-cutoff-omni.fits" | \
        md5sum -c -

RUN mkdir -p BXA/examples/sherpa/chandra && \
    echo "179.pi  0.5 8" > BXA/examples/sherpa/chandra/filenames.txt

# ---------------------------------------------------------------------------
# 17) MOSFIT PATCH
# ---------------------------------------------------------------------------
RUN sed -i 's/kilonova\.space/tde.space/g' /opt/conda/lib/python3.12/site-packages/mosfit/fetcher.py

# ---------------------------------------------------------------------------
# 18) COPY REPOSITORY FILES (test stage)
# ---------------------------------------------------------------------------
COPY exoplanet exoplanet
COPY juliet juliet
COPY *.py ./
COPY *.sh ./

# ---------------------------------------------------------------------------
# 19) COMPATIBILITY FIXES
# ---------------------------------------------------------------------------
COPY fix_gammaln.py /tmp/fix_gammaln.py
RUN python /tmp/fix_gammaln.py

RUN sed -i '/runreal \$s transit exoplanet-transit\.py/d' /root/runreal.sh

# ---------------------------------------------------------------------------
# 20) IMPORT TEST (test stage)
# ---------------------------------------------------------------------------
RUN conda run -n base python importtester.py
RUN conda run -n base python -c "import problems; import scipy.stats; print('problems + scipy.stats: OK')"
RUN grep -n "transit" /root/runreal.sh || echo "stale transit invocation removed"

# ---------------------------------------------------------------------------
# 21) CREATE PRODUCTION-ONLY CONDA ENVIRONMENT (/opt/grb-env) in BUILDER
# ---------------------------------------------------------------------------
# Accept conda TOS for anaconda.org channels (required since 2024)
RUN conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main && \
    conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r

RUN --mount=type=cache,target=/opt/conda/pkgs,sharing=locked \
    conda install -y -c conda-forge mamba && \
    mamba create -y -n grb-env \
        -c conda-forge \
        "python=3.12.14" \
        "numpy=2.3.5" \
        "scipy=1.16.3" \
        "astropy=8.0.1" \
        "matplotlib=3.11.2" \
        "healpy=1.20.0" \
        "fermipy=1.4.2" \
        "ultranest=4.5.2" \
        && \
    mamba clean --all -y

RUN --mount=type=cache,target=/opt/conda/pkgs,sharing=locked \
    mamba install -y -n grb-env \
        -c conda-forge \
        threeML==2.6.1 \
        astromodels==2.6.0 \
        ultranest==4.5.2 \
        && \
    mamba clean --all -y

# Verify the production environment
RUN /opt/conda/envs/grb-env/bin/python -c "import threeML, astromodels, ultranest, numpy, scipy, astropy, matplotlib, healpy, fermipy; print('threeML:', threeML.__version__); print('astromodels:', astromodels.__version__); print('ultranest:', ultranest.__version__); print('numpy:', numpy.__version__); print('scipy:', scipy.__version__); print('astropy:', astropy.__version__); print('matplotlib:', matplotlib.__version__); print('healpy:', healpy.__version__); print('fermipy:', fermipy.__version__)"

# Install ultranest shim into production environment
COPY ultranest_sampler.py /tmp/
RUN /opt/conda/envs/grb-env/bin/python -c "import threeML; import os; import shutil; THREEML_PATH = os.path.dirname(threeML.__file__); dest = os.path.join(THREEML_PATH, 'bayesian', 'ultranest_sampler.py'); shutil.copy('/tmp/ultranest_sampler.py', dest); print('Installed ultranest_sampler.py to', dest)"

# ============================================================================
# RUNTIME STAGE - Production GRB only
# ============================================================================
FROM continuumio/miniconda3:latest AS runtime

LABEL description="space-of-inference-spaces GRB production runtime"

# ---------------------------------------------------------------------------
# 1) RUNTIME SYSTEM DEPENDENCIES
# ---------------------------------------------------------------------------
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update -y && \
    apt-get install -y --no-install-recommends \
        tini && \
    rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# 2) COPY PRODUCTION-ONLY CONDA ENVIRONMENT FROM BUILDER
# ---------------------------------------------------------------------------
COPY --from=builder /opt/conda/envs/grb-env /opt/grb-env

# ---------------------------------------------------------------------------
# 3) COPY FERMITOOLS REFERENCE DATA (data only, no executables)
# ---------------------------------------------------------------------------
COPY --from=builder /opt/conda/share/fermitools/data /opt/grb-env/share/fermitools/data

# ---------------------------------------------------------------------------
# 4) SET UP CLIK PATH (test-only, but needed for test stage)
# ---------------------------------------------------------------------------
ENV CLIK_PATH="/opt/planck/code/plc_3.0/plc-3.01"
ENV PATH="/opt/planck/code/plc_3.0/plc-3.01/bin:${PATH}"

# ---------------------------------------------------------------------------
# 4) CREATE NON-ROOT USER
# ---------------------------------------------------------------------------
RUN groupadd -r appuser && useradd -r -g appuser -d /home/appuser -m appuser

# ---------------------------------------------------------------------------
# 5) COPY PRODUCTION FILES
# ---------------------------------------------------------------------------
COPY --chown=appuser:appuser grb.py /home/appuser/
COPY --chown=appuser:appuser entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# ---------------------------------------------------------------------------
# 5) ENVIRONMENT VARIABLES
# ---------------------------------------------------------------------------
ENV PATH="/opt/grb-env/bin:${PATH}"
ENV CALDB="/opt/grb-env/share/fermitools/data/caldb/"
ENV IRF="P8R3_SOURCE_V2"
ENV FERMITOOLS="/opt/grb-env/share/fermitools"
ENV FERMI_DIR="/opt/grb-env/share/fermitools/"
ENV PFILES="/opt/grb-env/share/fermitools/syspfiles/"
ENV OUTPUT_DIR="/opt/output"
ENV MPLBACKEND="Agg"
ENV PYTHONUNBUFFERED="1"

# ---------------------------------------------------------------------------
# 6) WORKDIR AND USER
# ---------------------------------------------------------------------------
WORKDIR /home/appuser
USER appuser

# ---------------------------------------------------------------------------
# 7) ENTRYPOINT / CMD
# ---------------------------------------------------------------------------
ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
CMD ["python", "/home/appuser/grb.py"]


# ============================================================================
# TEST STAGE - Full test environment
# ============================================================================
# NOTE: Test stage uses its own base to avoid inheriting runtime's ENTRYPOINT/CMD
# when building with --target runtime (BuildKit bug workaround)
FROM continuumio/miniconda3:latest AS test

USER root

# ---------------------------------------------------------------------------
# 1) ADD FULL CONDA ENVIRONMENT
# ---------------------------------------------------------------------------
COPY --from=builder /opt/conda /opt/conda

# ---------------------------------------------------------------------------
# 2) ADD TEST ARTIFACTS
# ---------------------------------------------------------------------------
COPY --from=builder --chown=appuser:appuser /root/exoplanet /home/appuser/exoplanet
COPY --from=builder --chown=appuser:appuser /root/juliet /home/appuser/juliet
COPY --from=builder --chown=appuser:appuser /root/problems.py /home/appuser/
COPY --from=builder --chown=appuser:appuser /root/autosampler.py /home/appuser/
COPY --from=builder --chown=appuser:appuser /root/runtoy.sh /home/appuser/
COPY --from=builder --chown=appuser:appuser /root/runreal.sh /home/appuser/
COPY --from=builder --chown=appuser:appuser /root/crab.py /home/appuser/
COPY --from=builder --chown=appuser:appuser /root/ligo.py /home/appuser/
COPY --from=builder --chown=appuser:appuser /root/icecube.py /home/appuser/
COPY --from=builder --chown=appuser:appuser /root/exoplanet.py /home/appuser/
COPY --from=builder --chown=appuser:appuser /root/bixrayspectrum.py /home/appuser/
COPY --from=builder --chown=appuser:appuser /root/xrayspectrum.py /home/appuser/
COPY --from=builder --chown=appuser:appuser /root/xrayspectrum2.py /home/appuser/
COPY --from=builder --chown=appuser:appuser /root/timeseries.py /home/appuser/
COPY --from=builder --chown=appuser:appuser /root/logistic.py /home/appuser/
COPY --from=builder --chown=appuser:appuser /root/LJ6.py /home/appuser/
COPY --from=builder --chown=appuser:appuser /root/importtester.py /home/appuser/
COPY --from=builder --chown=appuser:appuser /root/montepython_public /home/appuser/montepython_public
COPY --from=builder --chown=appuser:appuser /root/PosteriorStacker /home/appuser/PosteriorStacker
COPY --from=builder --chown=appuser:appuser /root/BXA /home/appuser/BXA

# ---------------------------------------------------------------------------
# 3) ADD CIAO ENV
# ---------------------------------------------------------------------------
COPY --from=builder /opt/conda/envs/ciao /opt/conda/envs/ciao

# ---------------------------------------------------------------------------
# 3) ADD PLANCK/CLASS/CLIK
# ---------------------------------------------------------------------------
COPY --from=builder /opt/planck /opt/planck
COPY --from=builder /etc/ld.so.conf.d/clik.conf /etc/ld.so.conf.d/clik.conf
# NOTE: clik.sh is not created by build_clik.sh (it's intentionally omitted to avoid corrupting build env)
# Create an empty one for compatibility
RUN touch /etc/profile.d/clik.sh && chmod 644 /etc/profile.d/clik.sh
RUN ldconfig

# ---------------------------------------------------------------------------
# 4) TEST ENTRYPOINT OVERRIDE
# ---------------------------------------------------------------------------
WORKDIR /home/appuser
USER appuser
ENTRYPOINT ["/usr/bin/tini", "--", "/bin/bash", "-c"]
CMD ["runtoy.sh testsampler && runreal.sh testsampler"]