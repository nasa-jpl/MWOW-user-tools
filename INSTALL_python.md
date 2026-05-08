# Installing MWOW User Tools (Python)

Python tools for accessing and visualizing MWOW (Multi-sensor Worldwide
Ocean Winds) version 0.2 data products. These tools let you open MWOW
NetCDF files, extract point time series, match ship tracks, select
geographic regions, perform inter-sensor collocation and comparison, and
generate time-lapse videos of wind fields.


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
at locations where SAR coverage is unavailable. Both products are observation only. No gap-filling procedure has been
applied to either product.

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


## Install with conda (recommended)

```bash
# 1. Clone the repository
git clone https://github-fn.jpl.nasa.gov/MWOW/mwow-user-tools.git
cd mwow-user-tools

# 2. Create a Python environment with all dependencies
conda create -n mwow python=3.10 numpy xarray netCDF4 dask \
    matplotlib pandas cartopy ffmpeg jupyter -c conda-forge

# 3. Activate the environment
conda activate mwow

# 4. Install the mwow-tools package
pip install -e .
```

> **Note:** The repository also contains an `environment.yml` that
> includes pyFerret (for NOAA Ferret users) and pins Python 3.10.
> The instructions above create a lighter environment without pyFerret.


## Install with pip + venv (alternative)

If you prefer not to use conda:

```bash
# 1. Clone the repository
git clone https://github-fn.jpl.nasa.gov/MWOW/mwow-user-tools.git
cd mwow-user-tools

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# 3. Install the package with all dependencies
pip install -e ".[cli]"
pip install cartopy dask jupyter

# 4. Install ffmpeg (needed only for video generation)
#    On macOS:  brew install ffmpeg
#    On Ubuntu: sudo apt install ffmpeg
#    On RHEL/CentOS: sudo dnf install ffmpeg
```

> **Note:** Cartopy requires the GEOS and PROJ system libraries. If
> `pip install cartopy` fails, install them first:
> - macOS: `brew install geos proj`
> - Ubuntu/Debian: `sudo apt install libgeos-dev libproj-dev`
> - RHEL/CentOS: `sudo dnf install geos-devel proj-devel`


## Verify your install

After installation, run this script to confirm everything works:

```python
from mwow_tools import open_mwow_files, select_point
import matplotlib.pyplot as plt

# Open one or more MWOW files (edit this path)
ds = open_mwow_files("/path/to/your/mwow_data/*.nc")

# Extract a time series at a single point
ds_point = select_point(ds, lat=-54, lon=90)

# Plot wind speed across orbits
ws = ds_point["wind_speed"].values.flatten()
times = ds_point["time"].values.flatten()

# Drop NaN values (orbits with no data at this point)
import numpy as np
mask = ~np.isnan(ws)

plt.figure(figsize=(10, 4))
plt.scatter(times[mask], ws[mask], s=10)
plt.xlabel("Time")
plt.ylabel("Wind speed (m/s)")
plt.title("MWOW wind speed time series at 54°S, 90°E")
plt.tight_layout()
plt.show()
```

Also verify the command-line tool:

```bash
mwow-tools --help
```

You should see usage information for the `timeseries`, `ship-track`, and
`region` subcommands.


## Next steps

- **Jupyter notebook:** `examples/mwow_example_scripts.ipynb` — three
  worked examples with inline plots (edit `data_path` in the first cell)
- **Command-line usage:** see the CLI section in `README.md`
- **Full API reference:** see the API reference section in `README.md`
- **Static notebook export:**
  `examples/mwow_example_scripts_notebook_export.html` — viewable
  without Jupyter


## Troubleshooting

**`conda create` fails or is very slow:**
Make sure conda-forge is your default (and only) channel:
```bash
conda config --show channels
# Should show:  - conda-forge
```

**Cartopy import error (missing projection data):**
Cartopy downloads coastline/border shapefiles on first use. If you are
behind a firewall, pre-download them:
```bash
python -c "import cartopy; cartopy.io.shapereader.natural_earth()"
```

**`ffmpeg` not found (video generation fails):**
The `generate_region_video` function shells out to `ffmpeg`. Verify it
is installed:
```bash
ffmpeg -version
```
With conda, `conda install ffmpeg -c conda-forge` handles this
automatically.

**`mwow-tools` command not found:**
Make sure you ran `pip install -e .` from the repo directory with the
correct environment activated.

**Import errors for numpy/xarray/etc.:**
Verify you are in the correct environment:
```bash
conda activate mwow   # or: source .venv/bin/activate
python -c "from mwow_tools import open_mwow_files; print('OK')"
```
