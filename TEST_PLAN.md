# Test Plan: mwow-user-tools

## Context

The `mwow-user-tools` repo provides Python tools for scientists to access MWOW L3 ocean wind NetCDF data. It has never been formally tested. The code was extracted from a Jupyter notebook and currently has no test suite. We need unit tests and end-to-end tests covering the core Python package (`mwow_tools/`), the CLI (`cli.py`), and the pyFerret bridge (`ferret/mwow_ferret.py`). Tests should run against real v0.2 MWOW data (all 4 product types).

## Key Finding: All 4 File Types

The code **should** work on all 4 product types because `reader.py` uses generic xarray operations with no hardcoded grid sizes. Lowres files are 2880x1440 (global 0.125 deg), highres tiles are 2880x2880 (45x45 deg, 1/64 deg). Both share the same dimensions `(orbit, latitude, longitude)` and variables (`wind_speed`, `wind_direction`, `time`, etc.). The tests must verify this explicitly.

## Data Path Configuration

The v0.2 data is at `/u/tsali-z0/fore/mwow_v0.2_fwd/`. Data paths must be **runtime configurable** so tests work on any machine. Approach:
- Tests read data root from environment variable `MWOW_DATA_ROOT`
- Default: `/u/tsali-z0/fore/mwow_v0.2_fwd`
- E2E tests that need real data are marked with `@pytest.mark.skipif` when the path doesn't exist
- A `conftest.py` provides fixtures that resolve file paths for each of the 4 product types

## Bugs Found During Review

### Bug #1 (confirmed): `open_mwow_files` fails on multiple highres tiles

When opening multiple highres tiles with `open_mwow_files`, `xr.open_mfdataset` tries to concatenate them — but tiles have different lat/lon coordinates (each covers a different 45x45 deg region). This will fail or produce unexpected results. **Fix required before testing.**

### Bug #2 (possible): Misleading transpose in `mwow_ferret.py`

Comments on lines 59 and 176 say `# shape: (lon, lat, orbit)` but actual NetCDF dimension order is `(orbit, latitude, longitude)`. The `np.transpose(data, (2, 1, 0))` call reverses this to `(lon, lat, orbit)`, which then gets assigned to axes `[ORBIT, LATITUDE, LONGITUDE]` — meaning orbit data goes to the LONGITUDE axis and longitude data goes to the ORBIT axis. The `axis_pos` mapping may compensate, but this needs verification during testing.

### Not a bug: `select_region` uses `wind_speed` for empty-orbit check

The `drop_empty_orbits` logic in `reader.py:130` checks `wind_speed.notnull()`. This is intentional — if wind_speed is all fill values, no MWOW data is useful to plot.

## Pre-testing Fix

Before running any tests, fix `open_mwow_files` in `reader.py` to handle highres tiles with different lat/lon grids. The function needs to either:
- Detect incompatible coordinates and open tiles individually (returning a list or dict)
- Use `xr.open_mfdataset(..., combine="nested")` or similar strategy
- Document that multiple highres tiles should be opened individually

## Test Framework

**pytest** (already listed in `pyproject.toml` under `[project.optional-dependencies] dev`).

## Import Validation

Before running any tests, verify that all required imports are available. If pyferret or any other dependency is missing, **stop and troubleshoot** rather than skipping tests. The test run should begin with an environment check.

## Test Structure

```
mwow-user-tools/
└── tests/
    ├── conftest.py           # Fixtures: data root, file paths for all 4 types
    ├── test_reader.py        # Unit tests for reader.py functions
    ├── test_cli.py           # Unit + E2E tests for CLI
    ├── test_e2e.py           # End-to-end tests against real data
    └── test_plots/           # Output directory for visual sanity-check plots
```

---

## 1. `tests/conftest.py` — Shared Fixtures

**File: `mwow-user-tools/tests/conftest.py`**

- `data_root` fixture: reads `MWOW_DATA_ROOT` env var, defaults to `/u/tsali-z0/fore/mwow_v0.2_fwd`
- `has_real_data` fixture: checks `data_root` exists on disk
- `epi_lowres_files` fixture: globs `{data_root}/epi/lowres/2026/04/14/*.nc`
- `epi_highres_files` fixture: globs `{data_root}/epi/highres/2026/04/14/*.nc`
- `nonepi_lowres_files` fixture: globs `{data_root}/nonepi/lowres/2026/04/14/*.nc`
- `nonepi_highres_files` fixture: globs `{data_root}/nonepi/highres/2026/04/14/*.nc`
- `single_lowres_file` fixture: first file from `epi_lowres_files`
- `single_highres_file` fixture: first file from `epi_highres_files`
- `plot_dir` fixture: creates `tests/test_plots/` and returns the path
- `skip_no_data` marker: `pytest.mark.skipif(not has_real_data, ...)`
- Custom pytest marker registration for `realdata`

---

## 2. `tests/test_reader.py` — Unit Tests for `reader.py`

### `open_mwow_files`

| # | Test | Type | Data |
|---|------|------|------|
| 1 | Single lowres file returns Dataset with correct dims `(orbit, latitude, longitude)` | real | lowres |
| 2 | Single highres file returns Dataset with correct dims `(orbit, latitude, longitude)` | real | highres |
| 3 | Glob pattern opens multiple lowres files and concatenates along orbit | real | lowres |
| 4 | List of file paths works | real | lowres |
| 5 | Glob pattern matching no files falls back to literal path (and raises on missing) | synthetic | none |
| 6 | Multiple highres tiles from different regions open correctly after bug fix | real | highres |
| 7 | EPI and nonEPI files have consistent structure | real | all 4 |

### `select_point`

| # | Test | Type | Data |
|---|------|------|------|
| 8 | Returns dataset with orbit dim only (lat/lon scalar) | real | lowres |
| 9 | Nearest-neighbor selects correct grid point | real | lowres |
| 10 | Works on highres tile (point within tile bounds) | real | highres |
| 11 | Point outside highres tile bounds — picks edge | real | highres |
| 12 | Result contains expected variables (wind_speed, wind_direction, time, etc.) | real | lowres |

### `match_ship_track`

| # | Test | Type | Data |
|---|------|------|------|
| 13 | Single-point track returns correct shape | real | lowres |
| 14 | Multi-point track returns one result per point | real | lowres |
| 15 | Closest-time orbit is selected (construct times near known orbit times) | real | lowres |
| 16 | Works on highres data | real | highres |
| 17 | All-NaN time handling (point over land) returns result without crash | real | lowres |

### `select_region`

| # | Test | Type | Data |
|---|------|------|------|
| 18 | Returns subset with correct lat/lon bounds | real | lowres |
| 19 | `drop_empty_orbits=True` reduces orbit count | real | lowres |
| 20 | `drop_empty_orbits=False` preserves all orbits | real | lowres |
| 21 | Works on highres tile (region within tile) | real | highres |
| 22 | Region straddling tile edge on highres — returns only in-bounds portion | real | highres |
| 23 | Region over open ocean has data; region over land is mostly NaN | real | lowres |

### Cross-product-type consistency

| # | Test | Type | Data |
|---|------|------|------|
| 24 | All 4 product types have same variable names | real | all 4 |
| 25 | All 4 product types have same dimension names | real | all 4 |
| 26 | Lowres lat range is [-90, 90], lon range [-180, 180] | real | lowres |
| 27 | Highres lat/lon range matches tile label | real | highres |

---

## 3. `tests/test_cli.py` — CLI Tests

Uses `cli.main(argv=[...])` with `--no-plot`, and `--output` for plot tests.

| # | Test | Type | Data |
|---|------|------|------|
| 28 | `timeseries` with `--no-plot` prints orbit lines to stdout | real | lowres |
| 29 | `timeseries` with `--no-plot` on highres file | real | highres |
| 30 | `region` with `--no-plot` prints region summary | real | lowres |
| 31 | `ship-track` with `--no-plot` and a synthetic CSV | real | lowres |
| 32 | Missing `--lat` arg raises SystemExit | synthetic | none |
| 33 | Non-existent file path gives error | synthetic | none |
| 34 | `timeseries --output` saves plot PNG (verify file created, >0 bytes) | real | lowres |
| 35 | `region --output` saves plot PNG for visual inspection | real | lowres |

---

## 4. `tests/test_e2e.py` — End-to-End Tests

Full pipeline tests using real data across all 4 product types.

| # | Test | Type | Data |
|---|------|------|------|
| 36 | Open all 4 EPI lowres files for one day, select_point, get wind_speed values | real | epi-lowres |
| 37 | Open all 4 nonEPI lowres files for one day, select_point | real | nonepi-lowres |
| 38 | Open single EPI highres tile, select_region within tile | real | epi-highres |
| 39 | Open single nonEPI highres tile, select_region | real | nonepi-highres |
| 40 | Ship-track across a day of lowres data | real | epi-lowres |
| 41 | Wind speed values are physically reasonable (0-80 m/s) | real | all 4 |
| 42 | Wind direction values are in [0, 360) | real | all 4 |
| 43 | sensor_id values match expected sensor set for EPI vs nonEPI | real | epi+nonepi lowres |
| 44 | Time values fall within the 6-hour window indicated by filename | real | lowres |
| 45 | Highres tile lat/lon grid matches expected 1/64 deg resolution | real | highres |
| 46 | Lowres global grid matches expected 0.125 deg resolution | real | lowres |

### Visual sanity-check tests (save PNGs to `tests/test_plots/`)

| # | Test | Output |
|---|------|--------|
| 47 | Timeseries at a known ocean point (epi lowres) | `timeseries_epi_lowres.png` |
| 48 | Timeseries at same point (nonepi lowres) | `timeseries_nonepi_lowres.png` |
| 49 | Region plot of Indian Ocean (epi lowres, one orbit) | `region_epi_lowres.png` |
| 50 | Region plot from a highres tile | `region_epi_highres.png` |
| 51 | Ship-track plot along a synthetic track | `ship_track_epi_lowres.png` |

---

## 5. pyFerret Bridge Tests

If pyferret is importable, run these tests. If NOT importable, **stop and troubleshoot** (do not skip).

| # | Test | Notes |
|---|------|-------|
| 52 | `_unit_for` returns correct units for known variables | Pure Python, no pyferret needed |
| 53 | `_open` helper works the same as `open_mwow_files` | Pure Python test |
| 54 | `load_mwow` loads data with correct shape | Needs pyferret |
| 55 | `load_mwow_point` returns correct orbit count | Needs pyferret |
| 56 | `load_mwow_region` drops empty orbits | Needs pyferret |
| 57 | Transpose logic produces correct axis mapping (verify possible bug #2) | Needs pyferret or careful numpy check |

---

## 6. MATLAB Testing (Manual)

The MATLAB example script (`examples/mwow_example_scripts.m`) should be tested manually on a system with MATLAB installed. Instructions:

1. Open MATLAB
2. `cd` to the `examples/` directory
3. Edit the `data_path` variable at the top of `mwow_example_scripts.m` to point to your MWOW data (e.g., `/u/tsali-z0/fore/mwow_v0.2_fwd/epi/lowres/2026/04/14/`)
4. Run each section and verify:
   - File opens without error
   - Dimensions match expected (2880 lon, 1440 lat for lowres)
   - Wind speed values look reasonable (0-30 m/s typical)
   - Plots render correctly
5. Repeat with a highres tile to verify it works on both file types
6. Record any errors for troubleshooting

---

## 7. User Setup Testing (Manual, without Claude)

Test the clone-and-install experience as a new user would. Use `script` to record the session for troubleshooting:

```bash
script -q setup_test.log
# --- everything below is recorded ---

git clone git@github-fn.jpl.nasa.gov:MWOW/mwow-user-tools.git
cd mwow-user-tools

# Option A: conda
conda env create -f environment.yml
conda activate mwow-user-tools
pip install -e .

# Option B: pip only
python -m venv .venv
source .venv/bin/activate
pip install -e ".[cli,dev]"

# Quick smoke test
python -c "from mwow_tools import open_mwow_files; print('OK')"
mwow-tools timeseries /path/to/mwow/files/*.nc --lat -54 --lon 90 --no-plot

exit  # ends the script recording
```

If anything fails, hand `setup_test.log` to Claude for analysis.

---

## Implementation Order

1. **Fix bug #1**: Update `open_mwow_files` in `reader.py` to handle highres tiles
2. Create `tests/conftest.py` with fixtures and markers
3. Verify all imports (xarray, netCDF4, matplotlib, pyferret) — troubleshoot failures
4. Create `tests/test_reader.py`
5. Create `tests/test_cli.py`
6. Create `tests/test_e2e.py` (including visual plot tests)
7. Run all tests, fix failures
8. Review generated plots in `tests/test_plots/`

## Verification

```bash
cd /u/tate0/bstiles/MWOW/mwow-user-tools
pip install -e ".[dev,cli]"
MWOW_DATA_ROOT=/u/tsali-z0/fore/mwow_v0.2_fwd pytest tests/ -v
```

To run without real data (only synthetic/parsing tests):
```bash
pytest tests/ -v -k "not realdata"
```

Visual sanity check:
```bash
ls tests/test_plots/*.png
# Open these PNGs and verify they look like reasonable wind data
```
