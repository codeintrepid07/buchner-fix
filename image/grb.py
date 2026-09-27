import warnings
import os
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

warnings.simplefilter("ignore")

import matplotlib
matplotlib.use('Agg')  # Must be before pyplot import
import matplotlib.pyplot as plt
import numpy as np

np.seterr(all="ignore")

# REQUIRED: TRIGGER_ID from environment (Fermi GBM format: bnYYMMDDNNN)
TRIGGER_ID = os.environ.get("TRIGGER_ID")
if not TRIGGER_ID:
    raise RuntimeError("TRIGGER_ID environment variable is required (e.g., bn080916009)")

# Validate Fermi GBM trigger ID format: bnYYMMDDNNN
if not (TRIGGER_ID.startswith("bn") and len(TRIGGER_ID) == 11 and TRIGGER_ID[2:].isdigit()):
    raise RuntimeError(f"Invalid TRIGGER_ID format: {TRIGGER_ID}. Expected Fermi GBM format: bnYYMMDDNNN (e.g., bn080916009)")

# Derive catalog source name: bn080916009 -> GRB080916009
CATALOG_NAME = "GRB" + TRIGGER_ID[2:]

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/opt/output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

from threeML import *
from threeML.io.package_data import get_path_of_data_file

silence_warnings()

print("=== Examining the catalog")

gbm_catalog = FermiGBMBurstCatalog()
print(gbm_catalog.query_sources(CATALOG_NAME))

grb_info = gbm_catalog.get_detector_information()[CATALOG_NAME]

gbm_detectors = grb_info["detectors"]
source_interval = grb_info["source"]["fluence"]
background_interval = grb_info["background"]["full"]
best_fit_model = grb_info["best fit model"]["fluence"]
model = gbm_catalog.get_model(best_fit_model, "fluence")[CATALOG_NAME]

print(model)

print("=== Downloading the data")
dload = download_GBM_trigger_data(TRIGGER_ID, detectors=gbm_detectors)


fluence_plugins = []
time_series = {}
for det in gbm_detectors:

    ts_cspec = TimeSeriesBuilder.from_gbm_cspec_or_ctime(
        det, cspec_or_ctime_file=dload[det]["cspec"], rsp_file=dload[det]["rsp"]
    )

    ts_cspec.set_background_interval(*background_interval.split(","))
    ts_cspec.save_background(f"{det}_bkg.h5", overwrite=True)

    ts_tte = TimeSeriesBuilder.from_gbm_tte(
        det,
        tte_file=dload[det]["tte"],
        rsp_file=dload[det]["rsp"],
        restore_background=f"{det}_bkg.h5",
    )

    time_series[det] = ts_tte

    ts_tte.set_active_time_interval(source_interval)
    ts_tte.view_lightcurve(-40, 100)

    fluence_plugin = ts_tte.to_spectrumlike()

    if det.startswith("b"):
        fluence_plugin.set_active_measurements("250-30000")
    else:
        fluence_plugin.set_active_measurements("9-900")

    fluence_plugin.rebin_on_background(1.0)
    fluence_plugins.append(fluence_plugin)

print("=== Set priors for the model")
model.GRB080916009.spectrum.main.shape.alpha.prior = Truncated_gaussian(
    lower_bound=-1.5, upper_bound=1, mu=-1, sigma=0.5
)
model.GRB080916009.spectrum.main.shape.beta.prior = Truncated_gaussian(
    lower_bound=-5, upper_bound=-1.6, mu=-2.25, sigma=0.5
)
model.GRB080916009.spectrum.main.shape.break_energy.prior = Log_normal(mu=2, sigma=1)
model.GRB080916009.spectrum.main.shape.break_energy.bounds = (None, None)
model.GRB080916009.spectrum.main.shape.K.prior = Log_uniform_prior(
    lower_bound=1e-3, upper_bound=1e1
)
model.GRB080916009.spectrum.main.shape.break_scale.prior = Log_uniform_prior(
    lower_bound=1e-4, upper_bound=10
)

"""
new_model = clone_model(model)

bayes = BayesianAnalysis(new_model, DataList(*fluence_plugins))

# share spectrum gives a linear speed up when
# spectrumlike plugins have the same RSP input energies
bayes.set_sampler("ultranest", share_spectrum=True)

bayes.sampler.setup(n_live_points=400)
bayes.sample()

bayes.restore_median_fit()
fig = display_spectrum_model_counts(bayes, min_rate=20)
"""

print("=== Time Resolved Analysis")

n3 = time_series["n3"]
n3.create_time_bins(0, 60, method="bayesblocks", use_background=True, p0=0.2)

fig = n3.view_lightcurve(use_binner=True)

bad_bins = []
for i, w in enumerate(n3.bins.widths):
    if w < 5e-2:
        bad_bins.append(i)

edges = [n3.bins.starts[0]]

for i, b in enumerate(n3.bins):
    if i not in bad_bins:
        edges.append(b.stop)

starts = edges[:-1]
stops = edges[1:]

n3.create_time_bins(starts, stops, method="custom")

fig = n3.view_lightcurve(use_binner=True)

time_resolved_plugins = {}

for k, v in time_series.items():
    v.read_bins(n3)
    time_resolved_plugins[k] = v.to_spectrumlike(from_bins=True)

print("=== Setting up the model")

band = Band()
band.alpha.prior = Truncated_gaussian(lower_bound=-1.5, upper_bound=1, mu=-1, sigma=0.5)
band.beta.prior = Truncated_gaussian(lower_bound=-5, upper_bound=-1.6, mu=-2, sigma=0.5)
band.xp.prior = Log_normal(mu=2, sigma=1)
band.xp.bounds = (1e-10, None)
band.K.prior = Log_uniform_prior(lower_bound=1e-10, upper_bound=1e3)
ps = PointSource("grb", 0, 0, spectral_shape=band)
band_model = Model(ps)

print("=== Perform the fits")

models = []
results = []
analysis = []
intervals_analyzed = []
for interval in [2]:  # range(12):
    print("Interval %d ..." % interval)

    # clone the model above so that we have a separate model
    # for each fit

    this_model = clone_model(band_model)

    # for each detector set up the plugin
    # for this time interval

    this_data_list = []
    for k, v in time_resolved_plugins.items():
        pi = v[interval]

        if k.startswith("b"):
            pi.set_active_measurements("250-30000")
        else:
            pi.set_active_measurements("9-900")

        pi.rebin_on_background(1.0)
        this_data_list.append(pi)

    # create a data list

    dlist = DataList(*this_data_list)

    # set up the sampler and fit

    bayes = BayesianAnalysis(this_model, dlist)

    # get some speed with share spectrum
    bayes.set_sampler("ultranest", share_spectrum=True)
    bayes.sampler.setup(
        min_num_live_points=400, frac_remain=0.5,
        chain_name=str(OUTPUT_DIR / f'grb-{interval}-ultranest'),
    )
    res = bayes.sample()

    bayes.sampler._sampler.plot()

    # at this stage we coudl also
    # save the analysis result to
    # disk but we will simply hold
    # onto them in memory

    analysis.append(bayes)
    intervals_analyzed.append(interval)


def _extract_parameter_summary(bayes_result):
    """Extract parameter posterior summaries from a threeML BayesianAnalysis result."""
    params = {}
    try:
        # Get all free parameter names from the model
        for param_name in bayes_result.analysis_results.free_parameters.keys():
            try:
                variate = bayes_result.get_variates(param_name)
                median_val = float(variate.median())
                hdi_68 = variate.highest_posterior_density_interval(cl=0.68)
                hdi_95 = variate.highest_posterior_density_interval(cl=0.95)
                params[param_name] = {
                    "median": median_val,
                    "hdi_68": [float(hdi_68[0]), float(hdi_68[1])],
                    "hdi_95": [float(hdi_95[0]), float(hdi_95[1])],
                }
            except Exception as e:
                params[param_name] = {"error": str(e)}
    except Exception as e:
        params["_extraction_error"] = str(e)
    return params


def write_production_output(trigger_id, catalog_name, analysis_list, intervals, output_dir):
    """Write analysis results to JSON files in output directory."""
    
    # Provenance
    provenance = {
        "trigger_id": trigger_id,
        "catalog_name": catalog_name,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "intervals_analyzed": intervals,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    }
    
    # Try to get threeML version
    try:
        import threeML
        provenance["threeML_version"] = threeML.__version__
    except Exception:
        provenance["threeML_version"] = "unknown"
    
    # Try to get ultranest version
    try:
        import ultranest
        provenance["ultranest_version"] = ultranest.__version__
    except Exception:
        provenance["ultranest_version"] = "unknown"
    
    # Write provenance.json
    with open(output_dir / "provenance.json", "w") as f:
        json.dump(provenance, f, indent=2)
    
    # Analysis results summary
    results = {
        "trigger_id": trigger_id,
        "catalog_name": catalog_name,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "intervals": []
    }
    
    for bayes, interval in zip(analysis_list, intervals):
        interval_result = {
            "interval": interval,
            "chain_directory": str(output_dir / f'grb-{interval}-ultranest'),
            "parameters": _extract_parameter_summary(bayes)
        }
        results["intervals"].append(interval_result)
    
    with open(output_dir / "analysis.json", "w") as f:
        json.dump(results, f, indent=2)


# === Write structured output ===
write_production_output(TRIGGER_ID, CATALOG_NAME, analysis, intervals_analyzed, OUTPUT_DIR)

print("=== Analysis complete. Output written to", OUTPUT_DIR)