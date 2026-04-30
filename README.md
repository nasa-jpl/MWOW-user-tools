# mwow-user-tools

Tools for accessing and visualizing
[MWOW (Multi-sensor Worldwide Ocean Winds)](https://podaac.jpl.nasa.gov/)
Level 3 data products.

MWOW merges ocean surface wind retrievals from 14+ satellite sensors
(scatterometers, radiometers, and SAR) onto a global 0.125° grid with
6-hourly temporal resolution.  Each file contains multiple satellite
passes indexed by an **orbit** dimension.

This repository provides:

| Tool | Language | Description |
|------|----------|-------------|
| **mwow_tools** | Python package | Reusable functions for opening files, extracting time series, matching ship tracks, selecting regions, inter-sensor collocation, comparison statistics/plots, and regional video generation |
| **mwow-tools** | CLI | Command-line interface for quick extraction and plotting |
| **ferret/** | pyFerret / Ferret | Bridge module, journal scripts, and descriptor template for NOAA Ferret users |
| **examples/** | Jupyter + MATLAB | Worked examples with inline plots |


## Data format

MWOW Level 3 NetCDF files follow CF-1.7 and ACDD-1.3 conventions:

| Dimension | Size | Description |
|-----------|------|-------------|
| longitude | 2880 | -179.9° to 179.9° at 0.125° spacing |
| latitude  | 1440 | -89.9° to 89.9° at 0.125° spacing |
| orbit     | varies | Satellite passes in the accumulation window |

Key variables:

| Variable | Units | Description |
|----------|-------|-------------|
| wind_speed | m/s | Ocean surface wind speed |
| wind_direction | degrees | Meteorological wind direction |
| wind_speed_uncert | m/s | Wind speed uncertainty |
| wind_direction_uncert | degrees | Wind direction uncertainty |
| quality_indicator | — | Quality flag (0 = best) |
| sensor_id | — | Source sensor identifier |
| time | datetime | Observation time per grid cell per orbit |
| orbit_start_time | datetime | Start time of each orbit pass |

### Sensor IDs

| ID | Sensor |
|----|--------|
| 0 | ASCAT-B |
| 1 | ASCAT-C |
| 2 | EOS-6 |
| 3 | HY-2B |
| 4 | HY-2C |
| 5 | SMAP |
| 6 | SWOT |
| 7 | COWVR |


## Obtaining MWOW data

MWOW data products are distributed through the NASA Physical Oceanography
Distributed Active Archive Center (PO.DAAC) at JPL:

1. **PO.DAAC Portal**: Search for "MWOW" at
   <https://podaac.jpl.nasa.gov/> and download files interactively.

2. **podaac-data-subscriber** (recommended for bulk downloads):
   ```bash
   pip install podaac-data-subscriber
   podaac-data-downloader -c MWOW_L3_6HOURLY -d ./mwow_data \
       --start-date 2026-03-21T00:00:00Z --end-date 2026-03-22T00:00:00Z
   ```

3. **OPeNDAP**: Access data remotely without full download via the
   OPeNDAP endpoints listed on the PO.DAAC dataset landing page.

You will need a free [NASA Earthdata Login](https://urs.earthdata.nasa.gov/)
account.


## Installation

```bash
git clone git@github-fn.jpl.nasa.gov:MWOW/mwow-user-tools.git
cd mwow-user-tools
conda env create -f environment.yml
conda activate mwow-user-tools
pip install -e .
```

This creates a Python 3.10 environment with all dependencies including
pyFerret. See [INSTALL.md](INSTALL.md) for detailed instructions for
Jupyter, CLI, Python, MATLAB, and pyFerret users.


## Quick start

### Python

```python
from mwow_tools import open_mwow_files, select_point, match_ship_track, select_region

# Open one or more MWOW files (accepts glob patterns)
ds = open_mwow_files("/data/mwow/*.nc")

# 1. Time series at a single point
ds_point = select_point(ds, lat=-54, lon=90)

# 2. Match a ship track
ds_ship = match_ship_track(ds,
    lats=[-38.1, -38.2, -38.3],
    lons=[70.0, 70.1, 70.2],
    times=["2026-03-21T19:35:36", "2026-03-21T20:35:36", "2026-03-21T21:35:36"],
)

# 3. Select a region (10° x 10° box centered at -38, 70)
ds_region = select_region(ds, lat_center=-38, lon_center=70, lat_size=5, lon_size=5)
```

### Sensor comparison

```python
from mwow_tools import find_collocations, plot_joint_histogram, plot_qi_sensitivity
import xarray as xr

ds = xr.open_dataset("/data/mwow/MWOW_L3_20260115T06_20260115T12_EPI_v0.2.nc")

# Find ASCAT-collocated observations for HY-2B (within ±30 min)
result = find_collocations(ds, "HY-2B")

# Plot 2D joint histogram with bias/std
plot_joint_histogram(result["ref_speed"], result["target_speed"], "HY-2B",
                     save_path="hy2b_vs_ascat.png")

# QI sensitivity (side-by-side panels at QI=0, <=1, <=2)
plot_qi_sensitivity(result, "HY-2B", save_path="hy2b_qi_sensitivity.png")
```

### Regional video

```python
from mwow_tools import generate_region_video
import glob

files = sorted(glob.glob("/data/mwow/MWOW_L3_*_EPI_v0.2.nc"))
region = {"lat_center": 14.0, "lon_center": -95.0, "lat_size": 4.0, "lon_size": 5.0}

generate_region_video(files, region, output_name="tehuantepec.mp4",
                      speedup=3600, utc_offset=-6)
```

### Command line

```bash
# Point time series with plot
mwow-tools timeseries /data/mwow/*.nc --lat -54 --lon 90

# Ship track from CSV (must have columns: latitude, longitude, time)
mwow-tools ship-track /data/mwow/*.nc --track ship_positions.csv

# Regional plot
mwow-tools region /data/mwow/*.nc --lat -38 --lon 70 --size 5

# Save plot to file instead of displaying
mwow-tools timeseries /data/mwow/*.nc --lat -54 --lon 90 -o timeseries.png

# Print data to stdout (no plot)
mwow-tools timeseries /data/mwow/*.nc --lat -54 --lon 90 --no-plot
```

### MATLAB

```matlab
folder = '/data/mwow/';
paths = dir(fullfile(folder, '*.nc'));
paths = fullfile({paths.folder}, {paths.name});

DS = open_mwow_files(paths);

% Single-point time series
ds_point = select_point_all_orbits(DS, -54, 90);

% Ship track
ds_ship = match_ship_track(DS, ship_lat, ship_lon, ship_time);

% Region
ds_region = select_region(DS, -38, 70, 5, 5);
```

See `examples/mwow_example_scripts.m` for the complete script with plotting.


## pyFerret usage

The `ferret/` directory provides three levels of integration for
NOAA scientists who work in Ferret / pyFerret:

### 1. Python bridge (recommended)

The bridge module loads MWOW data into pyFerret with proper axis
definitions.  Point and region functions map orbits to the **T (time)
axis** so you can use Ferret's time-based subsetting.  Full-file loads
use the **Z axis** because overlapping sensor times make a monotonic
time axis unreliable at global scale.

```python
import pyferret
from mwow_ferret import load_mwow, load_mwow_point, load_mwow_region

pyferret.start(quiet=True)

# Single-point time series (T axis — enables time subsetting)
load_mwow_point("/data/mwow/*.nc", lat=-54, lon=90)
pyferret.run('plot MWOW_WIND_SPEED_POINT')
pyferret.run('list MWOW_WIND_SPEED_POINT[T="18-APR-2026 00:00":"18-APR-2026 06:00"]')

# Regional subset (T axis)
load_mwow_region("/data/mwow/*.nc", lat_center=-38, lon_center=70)
pyferret.run('shade/l=1/palette=viridis MWOW_WIND_SPEED_REGION')

# Full dataset (Z axis — browse orbits with /K=)
load_mwow("/data/mwow/*.nc")
pyferret.run('shade/k=1/palette=viridis MWOW_WIND_SPEED')
```

All functions accept a ``var`` parameter (default ``"wind_speed"``).
Orbits are automatically deduplicated and sorted by time.  If the time
variation within an orbit exceeds 10 minutes for a region, a warning
recommends using the ``_z`` variant (e.g. ``load_mwow_region_z``) instead.

Convenience plotting functions are also available:

```python
from mwow_ferret import plot_timeseries, plot_region_orbit

plot_timeseries("MWOW_WIND_SPEED_POINT", output="timeseries.png")
plot_region_orbit("MWOW_WIND_SPEED_REGION", orbit=2, palette="viridis")
```

### 2. Ferret journal scripts

For pure-Ferret workflows, add `ferret/` to your `FER_GO` path and use
the provided `.jnl` scripts:

```
! Time series at a point (negative coords in parentheses)
go mwow_timeseries "/data/mwow/MWOW_file.nc" (-54) 90

! Regional shade plot for orbit 1
go mwow_region "/data/mwow/MWOW_file.nc" (-43) (-33) 65 75 1
```

### 3. Multi-file descriptor

For aggregating multiple MWOW files into a single Ferret dataset,
edit `ferret/mwow_multi.des` with your file paths and then:

```
use mwow_multi.des
shade/k=1 wind_speed
```

### How MWOW maps to Ferret axes

| MWOW dimension | Ferret axis | Access qualifier | Functions |
|---------------|-------------|-----------------|-----------|
| longitude | X | `/X=` or `/I=` | all |
| latitude | Y | `/Y=` or `/J=` | all |
| orbit | T (time) | `/T=` or `/L=` | `load_mwow_point`, `load_mwow_region` |
| orbit | Z (custom) | `/K=` | `load_mwow`, `*_z` variants |


## Examples

| File | Description |
|------|-------------|
| `examples/mwow_example_scripts.ipynb` | Jupyter notebook with three worked examples and inline plots |
| `examples/mwow_example_scripts.m` | Equivalent MATLAB script with helper functions |
| `examples/mwow_example_scripts_notebook_export.html` | Static HTML export of the notebook (viewable without Jupyter) |
| `ferret/mwow_pyferret_examples.py` | pyFerret examples covering all bridge functions |
| `ferret/mwow_timeseries.jnl` | Ferret journal script for point time series |
| `ferret/mwow_region.jnl` | Ferret journal script for regional shade plots |

To regenerate the HTML export from the notebook:

```bash
jupyter nbconvert --to html examples/mwow_example_scripts.ipynb \
    --output mwow_example_scripts_notebook_export.html
```


## API reference

### `mwow_tools.open_mwow_files(paths, chunks="auto")`

Open one or more MWOW NetCDF files and stack them along the orbit dimension.

- **paths**: File path(s), list of paths, or a glob pattern (e.g. `"/data/*.nc"`)
- **chunks**: Chunk specification for dask (default `"auto"`)
- **Returns**: `xarray.Dataset` with dimensions `(longitude, latitude, orbit)`

### `mwow_tools.select_point(ds, lat, lon)`

Extract all orbit data at the nearest grid point to the given coordinate.

- **ds**: MWOW dataset
- **lat**, **lon**: Target coordinates in degrees
- **Returns**: `xarray.Dataset` with a single lat/lon, indexed by orbit

### `mwow_tools.match_ship_track(ds, lats, lons, times)`

Match a sequence of moving-platform positions to the nearest MWOW observation
in space and time.

- **ds**: MWOW dataset
- **lats**, **lons**: Arrays of track coordinates
- **times**: Array of track timestamps (datetime64 or parseable strings)
- **Returns**: `xarray.Dataset` with one entry per input position

### `mwow_tools.select_region(ds, lat_center, lon_center, lat_size=5.0, lon_size=5.0, drop_empty_orbits=True)`

Select a geographic box and optionally drop orbits that have no data in the region.

- **ds**: MWOW dataset
- **lat_center**, **lon_center**: Center of the box (degrees)
- **lat_size**, **lon_size**: Half-width of the box (degrees, default 5.0)
- **drop_empty_orbits**: Remove all-NaN orbit slices (default True)
- **Returns**: `xarray.Dataset` for the selected region

### `mwow_tools.find_collocations(ds, target_sensor, ref_sensors=("ASCAT-B", "ASCAT-C"), max_dt_minutes=30, qi_max=None)`

Find temporally collocated observations between sensors on the MWOW grid.
For each grid cell where both reference and target sensors have valid data
within the time window, returns matched speed/direction/QI arrays.

- **ds**: MWOW dataset
- **target_sensor**: Sensor name (e.g. `"HY-2B"`) or integer ID
- **ref_sensors**: Reference sensor(s) (default ASCAT-B/C combined)
- **max_dt_minutes**: Maximum time difference in minutes (default 30)
- **qi_max**: If set, only include target obs with `quality_indicator <= qi_max`
- **Returns**: dict with arrays `ref_speed`, `target_speed`, `ref_direction`, `target_direction`, `target_qi`, `dt_minutes`, `lat`, `lon`, `time`

### `mwow_tools.collocate_files(file_paths, target_sensor, ...)`

Convenience wrapper that runs `find_collocations` one file at a time and
concatenates results.  Same parameters as `find_collocations` plus `file_paths`.

### `mwow_tools.plot_joint_histogram(ref_speed, target_speed, target_name, ...)`

Plot a 2D joint histogram of wind speed with log-color density, 1:1 line,
and bias/std annotation.

- **ref_speed**, **target_speed**: Matched speed arrays
- **target_name**: Sensor name for labels
- **bins**: Number of bins per axis (default 60)
- **speed_range**: (min, max) speed in m/s (default (0, 30))
- **save_path**: If provided, save figure to this path
- **Returns**: matplotlib Axes

### `mwow_tools.plot_qi_sensitivity(collocation_result, target_name, qi_levels=(0, 1, 2), ...)`

Plot joint histograms at multiple QI thresholds side by side.

- **collocation_result**: Output of `find_collocations`
- **target_name**: Sensor name
- **qi_levels**: QI thresholds for each panel
- **Returns**: matplotlib Figure

### `mwow_tools.generate_region_video(file_paths, region, ...)`

Generate a time-lapse video of orbit passes over a geographic region.
Frame dwell times are proportional to real inter-observation intervals.

- **file_paths**: MWOW file paths
- **region**: dict with `lat_center`, `lon_center`, `lat_size`, `lon_size`
- **speedup**: Real seconds per video second (default 3600)
- **utc_offset**: Hours from UTC for clock overlay
- **qi_max**: Quality filter (default 0)
- **Returns**: Path to output MP4 file


## Repository structure

```
mwow-user-tools/
├── README.md
├── pyproject.toml          # Python packaging (pip install -e .)
├── environment.yml         # Conda environment specification
├── .gitignore
├── mwow_tools/             # Python package
│   ├── __init__.py
│   ├── reader.py           # Core data access functions
│   ├── collocate.py        # Inter-sensor temporal collocation
│   ├── sensor_comparison.py # Joint histograms, bias/std, QI analysis
│   ├── video.py            # Regional wind field video generation
│   └── cli.py              # Command-line interface
├── ferret/                 # pyFerret / Ferret integration
│   ├── mwow_ferret.py      # Python bridge module
│   ├── mwow_pyferret_examples.py
│   ├── mwow_timeseries.jnl # Ferret journal: point time series
│   ├── mwow_region.jnl     # Ferret journal: regional plot
│   └── mwow_multi.des      # Multi-file descriptor template
└── examples/               # Worked examples
    ├── mwow_example_scripts.ipynb
    ├── mwow_example_scripts.m
    └── mwow_example_scripts_notebook_export.html
```


## License

BSD 3-Clause. See individual files for author information.
