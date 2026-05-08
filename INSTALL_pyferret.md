# Installing MWOW User Tools (pyFerret)

Python bridge for loading and visualizing MWOW (Multi-sensor Worldwide
Ocean Winds) version 0.2 data products inside pyFerret. This gives you
Ferret-native access to MWOW's orbit-indexed data with proper time or Z
axis mapping, plus matplotlib-based plotting that works in all
environments.


## Prerequisites

- **Git** (to clone the repository)
- **Miniforge** or **Mambaforge** — download from
  <https://github.com/conda-forge/miniforge>.
  Do **not** use Anaconda, which requires a commercial license.
- **NASA Earthdata Login** — free account at
  <https://urs.earthdata.nasa.gov/> (required to download MWOW data)


## MWOW v0.2 data products

MWOW Level 3 data is available in four variants:

| Product | Resolution | Description | DOI |
|---------|-----------|-------------|-----|
| 6-hourly EPI | 1/8° | Low-res, all sensors including HY-2B/C | <https://doi.org/10.5067/MWOW-6H-V02E> |
| 6-hourly | 1/8° | Low-res, excludes HY-2B/C | <https://doi.org/10.5067/MWOW-6H-V02> |
| 6-hourly high-res EPI | 1/64° | High-res (SAR grid), all sensors including HY-2B/C | <https://doi.org/10.5067/MWOW-6HHR-V02E> |
| 6-hourly high-res | 1/64° | High-res (SAR grid), excludes HY-2B/C | <https://doi.org/10.5067/MWOW-6HHR-V02> |

**EPI** (Expanded Platform Inputs) products include all available
sensors, including the Chinese HY-2B and HY-2C scatterometers. Non-EPI
products exclude HY-2B and HY-2C but are otherwise identical.

**Low-res** files contain data wherever any sensor has valid
observations. SWOT (SAR) data is averaged down onto the 1/8° grid.

**High-res** files are on a 1/64° grid and only have valid pixels where
a SAR sensor (currently SWOT) has data. Non-SAR sensors are interpolated
to these points where they have valid data, but no values are reported
at locations where SAR coverage is unavailable. Both products are
observation only. No gap-filling procedure has been applied to either
product.

All products share the same file structure and work with these tools.

### Downloading data

The recommended tool for bulk downloads is **podaac-data-subscriber**:

```bash
pip install podaac-data-subscriber

# Download one day of low-res EPI data:
podaac-data-downloader -c MWOW_L3_6HOURLY_EPI_V02 -d ./mwow_data \
    --start-date 2026-03-21T00:00:00Z --end-date 2026-03-22T00:00:00Z
```

You can also browse and download interactively at
<https://podaac.jpl.nasa.gov/> (search for "MWOW").


## Install

pyFerret on conda-forge requires Python 3.10. The repository includes an
`environment.yml` that sets this up with all dependencies:

```bash
# 1. Clone the repository
git clone <repo-url>
cd mwow-user-tools

# 2. Create the conda environment (Python 3.10 + pyFerret + all deps)
conda env create -f environment.yml

# 3. Activate the environment
conda activate mwow-user-tools

# 4. Install the mwow-tools package
pip install -e .

# 5. Add the ferret/ directory to your FER_GO path
export FER_GO="$FER_GO $(pwd)/ferret"
```

Add the `FER_GO` line to your shell profile (`~/.bashrc` or `~/.zshrc`)
to make it permanent.


## Verify your install

Run this script to confirm pyFerret and the MWOW bridge are working:

```python
import pyferret
import sys
sys.path.insert(0, "ferret")
from mwow_ferret import load_mwow_point, mpl_plot_timeseries

# Initialize pyFerret
pyferret.start(quiet=True)

# Load a point time series (edit this path)
load_mwow_point("/path/to/your/mwow_data/*.nc", lat=-54, lon=90)

# List the loaded variable
pyferret.run("show data")

# Plot with matplotlib (works in all environments)
mpl_plot_timeseries()
```

You should see Ferret report a loaded dataset with `MWOW_WIND_SPEED_POINT`
on a T axis, followed by a matplotlib scatter plot of wind speed vs time.

Also verify the Python tools and CLI:

```bash
python -c "from mwow_tools import open_mwow_files; print('OK')"
mwow-tools --help
```


## How it works

The pyFerret bridge (`ferret/mwow_ferret.py`) loads MWOW data into
Ferret variables with proper axis definitions:

| Function | Axis mapping | Use case |
|----------|-------------|----------|
| `load_mwow_point` | Orbit → **T (time)** | Point time series with time-based subsetting |
| `load_mwow_region` | Orbit → **T (time)** | Regional data with time-based subsetting |
| `load_mwow` | Orbit → **Z** | Full-file browsing by orbit number |
| `*_z` variants | Orbit → **Z** | When time overlap makes T axis unreliable |

Once loaded, you can use standard Ferret qualifiers (`/T=`, `/K=`,
`/X=`, `/Y=`) to subset and analyze the data.


## Plotting

Two approaches are available:

### Matplotlib (recommended)

```python
from mwow_ferret import mpl_plot_timeseries, mpl_plot_region

# After load_mwow_point:
mpl_plot_timeseries()
mpl_plot_timeseries(output="timeseries.png")  # save to file

# After load_mwow_region:
mpl_plot_region()
mpl_plot_region(orbit=3, output="region_orbit3.png")
```

### Native Ferret commands

```python
# After load_mwow_point:
pyferret.run("plot MWOW_WIND_SPEED_POINT")

# After load_mwow_region:
pyferret.run("shade/k=1/palette=viridis MWOW_WIND_SPEED_REGION")

# Time subsetting:
pyferret.run('list MWOW_WIND_SPEED_POINT[T="18-APR-2026 00:00":"18-APR-2026 06:00"]')
```

> **Known issue:** pyFerret 7.6.5 on conda-forge has a Fortran runtime
> bug that crashes native `plot`/`shade` commands. Use the `mpl_plot_*`
> functions until a fixed build is released. See
> <https://github.com/NOAA-PMEL/PyFerret/issues/145> for status.


## Next steps

- **Worked examples:** `ferret/mwow_pyferret_examples.py` — five
  workflows covering point, region, full-file, analysis, and plotting
- **Pure Python tools:** all functions in `mwow_tools` (reader,
  collocation, comparison, video) also work in this environment — see
  `INSTALL_python.md` for usage
- **Jupyter notebook:** `examples/mwow_example_scripts.ipynb`
- **Full API reference:** see `README.md`


## Troubleshooting

**`conda env create` fails or is very slow:**
Make sure conda-forge is your default (and only) channel:
```bash
conda config --show channels
# Should show:  - conda-forge
```

**`import pyferret` fails:**
pyFerret requires Python 3.10. Verify you are in the correct
environment:
```bash
conda activate mwow-user-tools
python --version   # Should show 3.10.x
```

**`from mwow_ferret import ...` fails with ModuleNotFoundError:**
The bridge module lives in the `ferret/` directory, not in the installed
package. Either run Python from the repo root, or add `ferret/` to your
path:
```python
import sys
sys.path.insert(0, "/path/to/mwow-user-tools/ferret")
```

**Native Ferret plot/shade crashes with "Fortran runtime error":**
This is the known getsym.F bug in pyferret 7.6.5. Use `mpl_plot_*`
functions instead. The bug is fixed in
<https://github.com/NOAA-PMEL/PyFerret/pull/149> (pending release).

**`mwow-tools` command not found:**
Make sure you ran `pip install -e .` from the repo directory with the
`mwow-user-tools` environment active.

**FER_GO not set (journal scripts not found):**
```bash
export FER_GO="$FER_GO /path/to/mwow-user-tools/ferret"
```
