# Installing mwow-user-tools

## Prerequisites

- **Git** with access to `github-fn.jpl.nasa.gov`
- **Miniforge** or **Mambaforge** (conda-forge based).
  Download from <https://github.com/conda-forge/miniforge>.
  Do **not** use Anaconda, which requires a commercial license.
- **MWOW data** from PO.DAAC (see README.md for download instructions)


## Quick start (all users)

```bash
git clone git@github-fn.jpl.nasa.gov:MWOW/mwow-user-tools.git
cd mwow-user-tools
conda env create -f environment.yml
conda activate mwow-user-tools
pip install -e .
```

This creates a `mwow-user-tools` conda environment with Python 3.10 and
all dependencies, including pyFerret.

Verify the install:

```bash
python -c "from mwow_tools import open_mwow_files; print('OK')"
mwow-tools --help
```


## Jupyter notebook users

After the quick start above:

```bash
jupyter notebook examples/mwow_example_scripts.ipynb
```

Edit the `data_path` variable in the first code cell to point to your
MWOW data directory, then run all cells.

A static HTML export of the notebook is also available at
`examples/mwow_example_scripts_notebook_export.html` for browsing
without Jupyter.


## Command-line (CLI) users

The `mwow-tools` command is available after install:

```bash
# Point time series
mwow-tools timeseries /path/to/mwow/*.nc --lat -54 --lon 90

# Regional plot
mwow-tools region /path/to/mwow/*.nc --lat -38 --lon 70 --size 5

# Ship track from CSV (columns: latitude, longitude, time)
mwow-tools ship-track /path/to/mwow/*.nc --track ship_positions.csv

# Save plot to file instead of displaying
mwow-tools timeseries /path/to/mwow/*.nc --lat -54 --lon 90 -o timeseries.png

# Print data to stdout (no plot)
mwow-tools timeseries /path/to/mwow/*.nc --lat -54 --lon 90 --no-plot

# Plot a different variable with custom color range
mwow-tools region /path/to/mwow/*.nc --lat -38 --lon 70 --size 5 \
    --var wind_u --vmin -15 --vmax 15
```


## Python script users

```python
from mwow_tools import open_mwow_files, select_point, match_ship_track, select_region

ds = open_mwow_files("/path/to/mwow/*.nc")

# Time series at a single point
ds_point = select_point(ds, lat=-54, lon=90)

# Match a ship track
ds_ship = match_ship_track(ds,
    lats=[-38.1, -38.2, -38.3],
    lons=[70.0, 70.1, 70.2],
    times=["2026-03-21T19:35:36", "2026-03-21T20:35:36", "2026-03-21T21:35:36"],
)

# Select a geographic region
ds_region = select_region(ds, lat_center=-38, lon_center=70)
```

See the API reference in README.md for full function signatures.


## MATLAB users

MATLAB does not require the conda environment. Open MATLAB and:

1. `cd` to the `examples/` directory
2. Open `mwow_example_scripts.m`
3. Edit the `data_path` variable at the top to point to your MWOW data
4. Run each section

The MATLAB script includes helper functions for opening files, extracting
point time series, matching ship tracks, and selecting regions.


## pyFerret users

pyFerret is included in the conda environment. After the quick start:

```bash
# Add the ferret/ directory to your FER_GO path
export FER_GO="$FER_GO $(pwd)/ferret"
```

You may want to add this to your shell profile (e.g. `~/.bashrc`).

### Python bridge (recommended)

```python
import pyferret
from mwow_ferret import load_mwow, load_mwow_point, load_mwow_region

pyferret.start(quiet=True)

# Load full dataset (orbit -> Z axis, accessible via /K=)
load_mwow("/path/to/mwow/*.nc")
pyferret.run('shade/k=1/palette=viridis MWOW_WIND_SPEED')

# Single-point time series
load_mwow_point("/path/to/mwow/*.nc", lat=-54, lon=90)
pyferret.run('plot MWOW_POINT')

# Regional subset
load_mwow_region("/path/to/mwow/*.nc", lat_center=-38, lon_center=70)
pyferret.run('shade/k=1 MWOW_WIND_SPEED_REGION')
```

### Ferret journal scripts

For pure-Ferret workflows:

```
go mwow_timeseries "/path/to/mwow/MWOW_file.nc" (-54) 90
go mwow_region "/path/to/mwow/MWOW_file.nc" (-43) (-33) 65 75 1
```

See `ferret/mwow_pyferret_examples.py` for more examples.


## For MWOW developers: switching environments

If you work on other MWOW repos (mwowgrid, swot_nn_winds, etc.) that
use a different Python version, switch between environments as needed:

```bash
# Work on mwow-user-tools (Python 3.10 + pyFerret)
conda activate mwow-user-tools

# Switch back to your main dev environment
conda activate py312
```

The `mwow-user-tools` environment is fully isolated and does not affect
your other environments.


## Troubleshooting

**`conda env create` fails**: Make sure you are using miniforge/mambaforge,
not Anaconda. Check that conda-forge is your default channel:
```bash
conda config --show channels
# Should show: - conda-forge
```

**`import pyferret` fails**: pyFerret requires Python 3.10. Verify you
are in the correct environment:
```bash
conda activate mwow-user-tools
python --version   # Should show 3.10.x
```

**`mwow-tools` command not found**: Run `pip install -e .` from the
repo directory while the `mwow-user-tools` environment is active.
