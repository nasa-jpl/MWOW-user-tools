# Installing MWOW User Tools (Ferret CLI)

Journal scripts for loading and visualizing MWOW (Multi-sensor Worldwide
Ocean Winds) version 0.2 data products using Ferret's command-line
interface. These scripts work in both classic Ferret and at pyFerret's
`yes?` prompt.


## Prerequisites

- **Ferret** or **pyFerret** installed and working
  - Classic Ferret: <https://ferret.pmel.noaa.gov/Ferret/>
  - pyFerret via conda: `conda install -c conda-forge pyferret`
- **Git** (to clone the repository)
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

All products share the same file structure and work with these scripts.

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


## Setup

No conda environment or Python install is required. Just clone the
repository and point Ferret to the scripts:

```bash
# 1. Clone the repository
git clone <repo-url>
cd mwow-user-tools

# 2. Add the ferret/ directory to your FER_GO path
export FER_GO="$FER_GO $(pwd)/ferret"
```

Add the `FER_GO` line to your shell profile (`~/.bashrc` or `~/.cshrc`)
to make it permanent.


## MWOW data structure in Ferret

MWOW v0.2 files have NetCDF dimensions `(orbit, latitude, longitude)`.
The journal scripts use `/order=zyx` to map these to Ferret axes:

| MWOW dimension | Ferret axis | Qualifier |
|---------------|-------------|-----------|
| longitude | X | `/X=` or `/I=` |
| latitude | Y | `/Y=` or `/J=` |
| orbit | Z | `/K=` |

Each K index corresponds to one satellite pass within the 6-hour file.


## Verify your install

Start Ferret (or pyFerret) and run:

```
yes? go mwow_timeseries "/path/to/your/MWOW_file.nc" (-54) 90
```

You should see a plot of wind speed at 54°S, 90°E across all orbits in
that file.


## Usage

### Point time series

Plot wind speed at a single location across all orbits in a file:

```
yes? go mwow_timeseries "/path/to/MWOW_file.nc" (-54) 90
yes? go mwow_timeseries "/path/to/MWOW_file.nc" (-38) 70
```

### Regional shade plot

Plot wind speed for a geographic box at a specific orbit:

```
! Region from 43°S-33°S, 65°E-75°E, orbit 1
yes? go mwow_region "/path/to/MWOW_file.nc" (-43) (-33) 65 75 1

! Same region, orbit 5
yes? go mwow_region "/path/to/MWOW_file.nc" (-43) (-33) 65 75 5

! Orbit defaults to 1 if omitted
yes? go mwow_region "/path/to/MWOW_file.nc" (-43) (-33) 65 75
```

### Direct file access (without scripts)

You can also open MWOW files directly:

```
yes? use/order=zyx "/path/to/MWOW_file.nc"

! List available variables
yes? show data

! Shade plot of orbit 1
yes? shade/k=1/palette=viridis wind_speed

! Subset by region and orbit
yes? shade/palette=viridis wind_speed[x=65:75, y=-43:-33, k=3]

! List values at a point across all orbits
yes? list wind_speed[x=90, y=-54]
```

### Multi-file descriptor

To aggregate multiple 6-hour files into a single Ferret dataset:

1. Copy `ferret/mwow_multi.des` and edit the `S_FILENAME` entries to
   list your files (one per 6-hour window).
2. Set `S_NUM_OF_FILES` to your total file count in each record.
3. In Ferret:

```
yes? use/order=zyx my_mwow_multi.des

! L= selects the time window (file), K= selects orbit within it
yes? shade/k=1/l=1/palette=viridis wind_speed
yes? shade/k=1/l=2/palette=viridis wind_speed
```


## Notes

- Negative coordinate values must be enclosed in parentheses in Ferret
  commands: `(-54)` not `-54`.
- The orbit dimension has no inherent time coordinate in Ferret. For
  time-axis plotting, use the pyFerret bridge (see `INSTALL_pyferret.md`).
- Each MWOW file covers a 6-hour accumulation window. The number of
  orbits (K values) varies by file.


## Troubleshooting

**"Unknown command: GO MWOW_TIMESERIES":**
The `ferret/` directory is not in your `FER_GO` path:
```bash
export FER_GO="$FER_GO /path/to/mwow-user-tools/ferret"
```

**Variables appear transposed or empty:**
Make sure you are using `/order=zyx` when opening v0.2 files. Without
it, Ferret may assign dimensions to the wrong axes.

**"No valid data" for a region/orbit:**
Not all orbits have data at all locations. Try a different K value:
```
yes? show grid wind_speed    ! see how many K values exist
yes? stat wind_speed[k=1]    ! check if orbit 1 has valid data
```
