"""
Shared fixtures for mwow-user-tools tests.

Data root is configurable via the MWOW_DATA_ROOT environment variable.
Default: /u/tsali-z0/fore/mwow_v0.2_fwd
"""

import glob
import os
from pathlib import Path

import dask
import pytest

# Force synchronous dask scheduler to avoid segfaults from threaded
# HDF5/netCDF4 reads on NFS.
dask.config.set(scheduler="synchronous")

DEFAULT_DATA_ROOT = "/u/tsali-z0/fore/mwow_v0.2_fwd"
DATA_ROOT = os.environ.get("MWOW_DATA_ROOT", DEFAULT_DATA_ROOT)
HAS_REAL_DATA = os.path.isdir(os.path.join(DATA_ROOT, "epi", "lowres"))

# A known date with data in all 4 product types
DATA_DATE = "2026/04/18"

realdata = pytest.mark.skipif(
    not HAS_REAL_DATA,
    reason=f"Real MWOW data not found at {DATA_ROOT}",
)


def pytest_configure(config):
    config.addinivalue_line("markers", "realdata: requires real MWOW data on disk")


# ── Data root ────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def data_root():
    return DATA_ROOT


# ── File path fixtures ───────────────────────────────────────────────────

def _glob_nc(data_root, dataset, resolution, date=DATA_DATE):
    pattern = os.path.join(data_root, dataset, resolution, date, "*.nc")
    files = sorted(glob.glob(pattern))
    return files


@pytest.fixture(scope="session")
def epi_lowres_files(data_root):
    return _glob_nc(data_root, "epi", "lowres")


@pytest.fixture(scope="session")
def epi_highres_files(data_root):
    return _glob_nc(data_root, "epi", "highres")


@pytest.fixture(scope="session")
def nonepi_lowres_files(data_root):
    return _glob_nc(data_root, "nonepi", "lowres")


@pytest.fixture(scope="session")
def nonepi_highres_files(data_root):
    return _glob_nc(data_root, "nonepi", "highres")


@pytest.fixture(scope="session")
def single_lowres_file(epi_lowres_files):
    if not epi_lowres_files:
        pytest.skip("No EPI lowres files found")
    return epi_lowres_files[0]


@pytest.fixture(scope="session")
def single_highres_file(epi_highres_files):
    if not epi_highres_files:
        pytest.skip("No EPI highres files found")
    # Prefer a tile over open ocean (e.g. 180W_45S = South Pacific)
    for f in epi_highres_files:
        if "180W_45S" in f:
            return f
    return epi_highres_files[0]


@pytest.fixture(scope="session")
def single_nonepi_lowres_file(nonepi_lowres_files):
    if not nonepi_lowres_files:
        pytest.skip("No nonEPI lowres files found")
    return nonepi_lowres_files[0]


@pytest.fixture(scope="session")
def single_nonepi_highres_file(nonepi_highres_files):
    if not nonepi_highres_files:
        pytest.skip("No nonEPI highres files found")
    for f in nonepi_highres_files:
        if "180W_45S" in f:
            return f
    return nonepi_highres_files[0]


# ── Plot output directory ────────────────────────────────────────────────

@pytest.fixture(scope="session")
def plot_dir():
    d = Path(__file__).parent / "test_plots"
    d.mkdir(exist_ok=True)
    return d
