"""
Command-line interface for mwow_tools.

Usage examples::

    mwow-tools timeseries /data/mwow/*.nc --lat -54 --lon 90
    mwow-tools region /data/mwow/*.nc --lat -38 --lon 70 --size 5 --var wind_u --vmin -15 --vmax 15
    mwow-tools ship-track /data/mwow/*.nc --track ship.csv --var wind_speed
"""

import argparse
import sys

import numpy as np


# ── Variable helpers ────────────────────────────────────────────────────

DERIVED = {"wind_u", "wind_v"}

UNITS = {
    "wind_speed": "m/s",
    "wind_direction": "deg",
    "wind_speed_uncert": "m/s",
    "wind_direction_uncert": "deg",
    "wind_u": "m/s",
    "wind_v": "m/s",
    "quality_indicator": "",
}


def _get_plot_data(ds, var):
    """Return a DataArray for *var*, computing derived variables on the fly."""
    if var == "wind_u":
        return ds["wind_speed"] * np.sin(np.radians(ds["wind_direction"]))
    elif var == "wind_v":
        return ds["wind_speed"] * np.cos(np.radians(ds["wind_direction"]))
    elif var in ds:
        return ds[var]
    else:
        available = sorted(set(ds.data_vars) | DERIVED)
        sys.exit(f"Unknown variable '{var}'. Available: {', '.join(available)}")


def _label_for(var):
    """Human-readable label with units for axis / colorbar."""
    name = var.replace("_", " ").title()
    unit = UNITS.get(var, "")
    return f"{name} [{unit}]" if unit else name


# ── Argument helpers ────────────────────────────────────────────────────

def _add_common_args(parser):
    parser.add_argument(
        "files", nargs="+",
        help="MWOW NetCDF file(s) or glob pattern",
    )
    parser.add_argument(
        "--var", default="wind_speed",
        help="Variable to plot (default: wind_speed). "
             "File variables plus derived: wind_u (zonal), wind_v (meridional).",
    )
    parser.add_argument(
        "--vmin", type=float, default=None,
        help="Colorbar / y-axis minimum",
    )
    parser.add_argument(
        "--vmax", type=float, default=None,
        help="Colorbar / y-axis maximum",
    )
    parser.add_argument(
        "--no-plot", action="store_true",
        help="Suppress the plot (print summary to stdout instead)",
    )
    parser.add_argument(
        "-o", "--output",
        help="Save plot to this file instead of displaying interactively",
    )


# ── Orbit title helper ─────────────────────────────────────────────────

def _orbit_title(ds_orbit):
    """Build a title string like 'ASCAT-C — 20260414T032145 UTC Asc'."""
    sensor = str(ds_orbit["sensor_name"].values) if "sensor_name" in ds_orbit else "?"
    time_slice = ds_orbit["time"].values
    valid_times = time_slice[~np.isnat(time_slice)]
    if len(valid_times) > 0:
        mean_ns = int(valid_times.astype("int64").mean())
        mean_t = np.datetime64(mean_ns, "ns")
        ts = str(mean_t)[:19].replace("-", "").replace(":", "")
        # Ascending if time increases with latitude
        mid_lon_idx = ds_orbit.sizes["longitude"] // 2
        t_col = ds_orbit["time"].isel(longitude=mid_lon_idx).values
        t_valid = t_col[~np.isnat(t_col)]
        direction = ""
        if len(t_valid) > 1:
            lat_vals = ds_orbit.latitude.values
            lat_of_valid = lat_vals[~np.isnat(t_col)]
            if lat_of_valid[0] < lat_of_valid[-1]:
                direction = " Asc" if t_valid[-1] > t_valid[0] else " Desc"
            else:
                direction = " Desc" if t_valid[-1] > t_valid[0] else " Asc"
    else:
        ts = "no-data"
        direction = ""
    return f"{sensor} — {ts} UTC{direction}"


# ── Subcommands ─────────────────────────────────────────────────────────

def cmd_timeseries(args):
    """Extract and plot a time series at a single point."""
    from mwow_tools import open_mwow_files, select_point
    import matplotlib.pyplot as plt

    ds = open_mwow_files(args.files)
    ds_point = select_point(ds, args.lat, args.lon)

    if args.no_plot:
        computed = ds_point.compute()
        data = _get_plot_data(computed, args.var)
        for i in range(computed.sizes["orbit"]):
            t = computed.time.values[i]
            val = float(data.values[i])
            print(f"orbit {i:3d}  time={t}  {args.var}={val:.2f}")
        return

    data = _get_plot_data(ds_point, args.var)
    label = _label_for(args.var)

    plt.figure(figsize=(12, 4))
    plt.scatter(ds_point.time, data, c=np.arange(ds_point.sizes["orbit"]))
    plt.xlabel("Time of Observation [UTC]")
    plt.ylabel(label)
    plt.colorbar(label="Orbit Pass Number")
    plt.title(f"MWOW {label} at ({args.lat}, {args.lon})")
    if args.vmin is not None or args.vmax is not None:
        plt.ylim(args.vmin, args.vmax)
    plt.grid(True)
    plt.tight_layout()
    if args.output:
        plt.savefig(args.output, dpi=150)
    else:
        plt.show()


def cmd_ship_track(args):
    """Match a ship track CSV to MWOW observations."""
    import pandas as pd
    from mwow_tools import open_mwow_files, match_ship_track
    import matplotlib.pyplot as plt

    track = pd.read_csv(args.track)
    required = {"latitude", "longitude", "time"}
    if not required.issubset(track.columns):
        sys.exit(
            f"CSV must have columns {required}; found {set(track.columns)}"
        )

    ds = open_mwow_files(args.files)
    ds_ship = match_ship_track(
        ds,
        track["latitude"].values,
        track["longitude"].values,
        track["time"].values,
    )

    if args.no_plot:
        computed = ds_ship.compute()
        data = _get_plot_data(computed, args.var)
        for i in range(computed.sizes["point"]):
            print(
                f"point {i:3d}  "
                f"lat={computed.latitude.values[i]:.2f}  "
                f"lon={computed.longitude.values[i]:.2f}  "
                f"time={computed.time.values[i]}  "
                f"{args.var}={float(data.values[i]):.2f}"
            )
        return

    data = _get_plot_data(ds_ship, args.var)
    label = _label_for(args.var)

    plt.figure(figsize=(12, 6))
    sc = plt.scatter(
        ds_ship.longitude, ds_ship.latitude,
        c=data, s=60, vmin=args.vmin, vmax=args.vmax,
    )
    for lon, lat, t in zip(
        ds_ship.longitude.values,
        ds_ship.latitude.values,
        ds_ship.time.values,
    ):
        lbl = np.datetime_as_string(t, unit="s")
        plt.text(lon, lat, f" {lbl}", fontsize=8, ha="left", va="bottom")
    plt.xlabel("Longitude [deg]")
    plt.ylabel("Latitude [deg]")
    plt.colorbar(sc, label=label)
    plt.title(f"MWOW {label} Along Ship Track")
    plt.grid(True)
    plt.tight_layout()
    if args.output:
        plt.savefig(args.output, dpi=150)
    else:
        plt.show()


def cmd_region(args):
    """Select and plot a geographic region."""
    from mwow_tools import open_mwow_files, select_region
    import matplotlib.pyplot as plt

    ds = open_mwow_files(args.files)
    ds_region = select_region(
        ds, args.lat, args.lon,
        lat_size=args.size, lon_size=args.size,
    )

    n_orbits = ds_region.sizes["orbit"]
    if n_orbits == 0:
        sys.exit("No orbits with data in the selected region.")

    if args.no_plot:
        print(f"Region: lat=[{args.lat - args.size}, {args.lat + args.size}], "
              f"lon=[{args.lon - args.size}, {args.lon + args.size}]")
        print(f"Orbits with data: {n_orbits}")
        return

    # Compute shared color range across all orbits
    plot_data = _get_plot_data(ds_region, args.var).compute()
    vals = plot_data.values
    finite = vals[np.isfinite(vals)]
    if len(finite) > 0:
        data_vmin, data_vmax = float(finite.min()), float(finite.max())
    else:
        data_vmin, data_vmax = 0.0, 1.0
    vmin = args.vmin if args.vmin is not None else data_vmin
    vmax = args.vmax if args.vmax is not None else data_vmax

    label = _label_for(args.var)

    fig, axes = plt.subplots(n_orbits, 1, figsize=(10, 4 * n_orbits), squeeze=False)
    for i in range(n_orbits):
        ax = axes[i, 0]
        ds_orbit = ds_region.isel(orbit=i)
        orbit_data = plot_data.isel(orbit=i)
        orbit_data.plot(ax=ax, x="longitude", y="latitude",
                        vmin=vmin, vmax=vmax, cbar_kwargs={"label": label})
        ax.set_aspect("equal")
        ax.set_title(_orbit_title(ds_orbit))
    plt.tight_layout()
    if args.output:
        plt.savefig(args.output, dpi=150)
    else:
        plt.show()


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="mwow-tools",
        description="Access and plot MWOW ocean wind data products.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # -- timeseries --
    ts = sub.add_parser(
        "timeseries",
        help="Extract a wind-speed time series at a single lat/lon point",
    )
    _add_common_args(ts)
    ts.add_argument("--lat", type=float, required=True, help="Latitude (degrees)")
    ts.add_argument("--lon", type=float, required=True, help="Longitude (degrees)")
    ts.set_defaults(func=cmd_timeseries)

    # -- ship-track --
    st = sub.add_parser(
        "ship-track",
        help="Match a moving-platform track to MWOW data",
    )
    _add_common_args(st)
    st.add_argument(
        "--track", required=True,
        help="CSV file with columns: latitude, longitude, time",
    )
    st.set_defaults(func=cmd_ship_track)

    # -- region --
    rg = sub.add_parser(
        "region",
        help="Select and plot a geographic region across orbits",
    )
    _add_common_args(rg)
    rg.add_argument("--lat", type=float, required=True, help="Center latitude (degrees)")
    rg.add_argument("--lon", type=float, required=True, help="Center longitude (degrees)")
    rg.add_argument(
        "--size", type=float, default=5.0,
        help="Half-width of the region in degrees (default: 5)",
    )
    rg.set_defaults(func=cmd_region)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
