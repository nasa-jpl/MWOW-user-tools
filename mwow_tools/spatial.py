"""
Static spatial wind map plotting for MWOW L3 data.

Produces geographic maps of wind speed, direction, u/v components, or
any gridded variable with coastlines, gridlines, and optional wind
direction arrows.  Supports orbit compositing and sensor/QI filtering.
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize

import cartopy.crs as ccrs
import cartopy.feature as cfeature

from mwow_tools.video import MWOW_JET_CMAP
from mwow_tools.collocate import SENSOR_IDS, SENSOR_NAMES


def plot_wind_map(ds, region=None, orbits=None, composite="last",
                  variable="wind_speed", arrows=True, arrow_subsample=None,
                  qi_max=2, sensor_ids=None,
                  speed_range=(0, 25), cmap=None,
                  title=None, save_path=None, dpi=150,
                  figsize=(10, 7), ax=None):
    """Plot a geographic wind map from MWOW L3 data.

    Parameters
    ----------
    ds : xarray.Dataset
        MWOW dataset with dimensions (orbit, latitude, longitude).
    region : dict or None, optional
        Spatial subset: {lat_center, lon_center, lat_size, lon_size}.
        If None, plots the full domain.
    orbits : list of int or None, optional
        Orbit indices to include.  If None, uses all orbits.
    composite : str, optional
        How to combine multiple orbits: "last" (default) overwrites with
        the last valid observation per pixel; "mean" averages (vector
        average for direction).
    variable : str, optional
        Variable to plot: "wind_speed" (default), "wind_direction",
        "u", "v", or any variable name in ds.
    arrows : bool, optional
        Overlay wind direction arrows (default True).
    arrow_subsample : int or None, optional
        Subsample factor for arrows.  Auto-computed if None (~15 arrows
        across the plot).
    qi_max : int or None, optional
        Maximum quality_indicator to display (default 2).
    sensor_ids : list of str or int or None, optional
        Filter to specific sensors (e.g. ["ASCAT-B", "HY-2B"]).
    speed_range : tuple, optional
        (vmin, vmax) for wind speed colorbar (default (0, 25)).
    cmap : str or Colormap or None, optional
        Colormap.  If None, auto-selected: mwow_jet for speed, hsv for
        direction.
    title : str or None, optional
        Plot title.  Auto-generated if None.
    save_path : str or None, optional
        If provided, save figure to this path.
    dpi : int, optional
        Output DPI (default 150).
    figsize : tuple, optional
        Figure size in inches (default (10, 7)).
    ax : matplotlib Axes or None, optional
        Existing GeoAxes to plot on.  If None, creates a new figure.

    Returns
    -------
    matplotlib.axes.Axes
        The map axes.
    """
    from mwow_tools.reader import select_region

    # Subset region if specified
    if region is not None:
        ds = select_region(
            ds, region["lat_center"], region["lon_center"],
            lat_size=region.get("lat_size", 5.0),
            lon_size=region.get("lon_size", 5.0),
            drop_empty_orbits=False)

    lats = ds.latitude.values
    lons = ds.longitude.values
    n_orbits = ds.sizes["orbit"]

    # Determine which orbits to use
    if orbits is None:
        orbit_indices = list(range(n_orbits))
    else:
        orbit_indices = list(orbits)

    # Filter by sensor_id
    if sensor_ids is not None:
        resolved = set()
        for s in sensor_ids:
            if isinstance(s, str):
                resolved.add(SENSOR_IDS[s.upper()])
            else:
                resolved.add(int(s))
        ds_sensor_ids = ds.sensor_id.values
        orbit_indices = [i for i in orbit_indices
                         if np.isfinite(ds_sensor_ids[i])
                         and int(ds_sensor_ids[i]) in resolved]

    if len(orbit_indices) == 0:
        print("WARNING: No orbits match the specified filters.")
        return None

    # Load data
    wind_speed = ds.wind_speed.values
    wind_dir = ds.wind_direction.values
    qi = ds.quality_indicator.values

    # Determine which variable to plot
    if variable in ("u", "v"):
        plot_data_source = variable
    elif variable == "wind_direction":
        plot_data_source = "wind_direction"
    elif variable == "wind_speed":
        plot_data_source = "wind_speed"
    elif variable in ds:
        plot_data_source = variable
    else:
        raise ValueError(f"Variable '{variable}' not found in dataset. "
                         f"Available: {list(ds.data_vars)}")

    # Composite orbits
    comp_field, comp_dir = _composite_orbits(
        ds, orbit_indices, composite, qi_max, plot_data_source)

    # Determine colormap and normalization
    if variable == "wind_direction":
        if cmap is None:
            cmap = "hsv"
        norm = Normalize(vmin=0, vmax=360)
        cbar_label = "Wind Direction [deg]"
    elif variable == "wind_speed":
        if cmap is None:
            cmap = MWOW_JET_CMAP
        norm = Normalize(vmin=speed_range[0], vmax=speed_range[1])
        cbar_label = "Wind Speed [m/s]"
    elif variable == "u":
        if cmap is None:
            cmap = "RdBu_r"
        vmax = max(abs(speed_range[0]), abs(speed_range[1]))
        norm = Normalize(vmin=-vmax, vmax=vmax)
        cbar_label = "Zonal Wind (u) [m/s]"
    elif variable == "v":
        if cmap is None:
            cmap = "RdBu_r"
        vmax = max(abs(speed_range[0]), abs(speed_range[1]))
        norm = Normalize(vmin=-vmax, vmax=vmax)
        cbar_label = "Meridional Wind (v) [m/s]"
    else:
        if cmap is None:
            cmap = MWOW_JET_CMAP
        norm = Normalize(vmin=speed_range[0], vmax=speed_range[1])
        cbar_label = variable

    # Determine coastline resolution based on domain size
    lat_span = lats[-1] - lats[0]
    coast_res = "110m" if lat_span > 60 else "50m" if lat_span > 15 else "10m"

    # Create figure
    projection = ccrs.PlateCarree()
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize,
                               subplot_kw={"projection": projection})
        own_figure = True
    else:
        fig = ax.figure
        own_figure = False

    ax.set_extent([lons[0], lons[-1], lats[0], lats[-1]], crs=projection)

    # Land and coastlines
    ax.add_feature(cfeature.LAND, facecolor="lightgray", zorder=1)
    ax.coastlines(resolution=coast_res, linewidth=0.8, zorder=3)

    # Plot the field
    im = ax.pcolormesh(
        lons, lats, comp_field,
        cmap=cmap, norm=norm, shading="nearest",
        transform=projection, zorder=2)

    # Wind direction arrows
    if arrows and comp_dir is not None:
        n_lon = len(lons)
        if arrow_subsample is None:
            arrow_subsample = max(1, n_lon // 15)

        lon_sub = lons[::arrow_subsample]
        lat_sub = lats[::arrow_subsample]
        lon_mesh, lat_mesh = np.meshgrid(lon_sub, lat_sub)

        dir_sub = comp_dir[::arrow_subsample, ::arrow_subsample]
        spd_sub = comp_field[::arrow_subsample, ::arrow_subsample]

        dir_rad = np.deg2rad(dir_sub)
        u = np.sin(dir_rad)
        v = np.cos(dir_rad)

        arrow_mask = np.isfinite(spd_sub) & np.isfinite(dir_sub)
        u_plot = np.where(arrow_mask, u, np.nan)
        v_plot = np.where(arrow_mask, v, np.nan)

        ax.quiver(lon_mesh, lat_mesh, u_plot, v_plot,
                  scale=25, width=0.003, headwidth=3, headlength=4,
                  color="white", alpha=0.8, transform=projection, zorder=4)

    # Gridlines
    gl = ax.gridlines(draw_labels=True, linewidth=0.5, color="gray",
                      alpha=0.5, linestyle="--", zorder=5)
    gl.top_labels = False
    gl.right_labels = False

    # Colorbar
    fig.colorbar(im, ax=ax, label=cbar_label, shrink=0.8, pad=0.05)

    # Title
    if title is None:
        if region is not None:
            title = (f"{cbar_label.split('[')[0].strip()} — "
                     f"{region['lat_center']}°, {region['lon_center']}°")
        else:
            title = cbar_label.split("[")[0].strip()
    ax.set_title(title, fontsize=12, fontweight="bold")

    if save_path is not None:
        fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
        if own_figure:
            plt.close(fig)

    return ax


def _composite_orbits(ds, orbit_indices, method, qi_max, variable):
    """Composite multiple orbits into a single 2D field.

    Returns (field_2d, direction_2d).  direction_2d is None if no
    wind_direction data is available.
    """
    wind_speed = ds.wind_speed.values
    wind_dir = ds.wind_direction.values if "wind_direction" in ds else None
    qi = ds.quality_indicator.values if "quality_indicator" in ds else None

    n_lat = ds.sizes["latitude"]
    n_lon = ds.sizes["longitude"]

    if variable == "u":
        if wind_dir is None:
            raise ValueError("Cannot compute u: wind_direction not in dataset")
    elif variable == "v":
        if wind_dir is None:
            raise ValueError("Cannot compute v: wind_direction not in dataset")

    if method == "last":
        field = np.full((n_lat, n_lon), np.nan)
        direction = np.full((n_lat, n_lon), np.nan) if wind_dir is not None else None

        for orb in orbit_indices:
            spd = wind_speed[orb]
            valid = np.isfinite(spd)
            if qi is not None and qi_max is not None:
                valid &= qi[orb] <= qi_max

            if variable == "wind_speed":
                field[valid] = spd[valid]
            elif variable == "wind_direction":
                if wind_dir is not None:
                    d = wind_dir[orb]
                    dir_valid = valid & np.isfinite(d)
                    field[dir_valid] = d[dir_valid]
            elif variable == "u":
                d = wind_dir[orb]
                dir_valid = valid & np.isfinite(d)
                field[dir_valid] = -spd[dir_valid] * np.sin(np.deg2rad(d[dir_valid]))
            elif variable == "v":
                d = wind_dir[orb]
                dir_valid = valid & np.isfinite(d)
                field[dir_valid] = -spd[dir_valid] * np.cos(np.deg2rad(d[dir_valid]))
            else:
                var_data = ds[variable].values[orb]
                var_valid = valid & np.isfinite(var_data)
                field[var_valid] = var_data[var_valid]

            if direction is not None:
                d = wind_dir[orb]
                dir_valid = valid & np.isfinite(d)
                direction[dir_valid] = d[dir_valid]

        return field, direction

    elif method == "mean":
        sum_u = np.zeros((n_lat, n_lon))
        sum_v = np.zeros((n_lat, n_lon))
        sum_spd = np.zeros((n_lat, n_lon))
        count = np.zeros((n_lat, n_lon), dtype=np.int32)

        for orb in orbit_indices:
            spd = wind_speed[orb]
            valid = np.isfinite(spd)
            if qi is not None and qi_max is not None:
                valid &= qi[orb] <= qi_max

            if wind_dir is not None:
                d = wind_dir[orb]
                dir_valid = valid & np.isfinite(d)
                d_rad = np.deg2rad(d[dir_valid])
                sum_u[dir_valid] += np.sin(d_rad)
                sum_v[dir_valid] += np.cos(d_rad)
                sum_spd[dir_valid] += spd[dir_valid]
                count[dir_valid] += 1
            else:
                sum_spd[valid] += spd[valid]
                count[valid] += 1

        has_data = count > 0
        mean_spd = np.full((n_lat, n_lon), np.nan)
        mean_spd[has_data] = sum_spd[has_data] / count[has_data]

        mean_dir = None
        if wind_dir is not None:
            mean_dir = np.full((n_lat, n_lon), np.nan)
            mean_dir[has_data] = np.rad2deg(
                np.arctan2(sum_u[has_data], sum_v[has_data])) % 360

        if variable == "wind_speed":
            return mean_spd, mean_dir
        elif variable == "wind_direction":
            return mean_dir, mean_dir
        elif variable == "u":
            field = np.full((n_lat, n_lon), np.nan)
            if mean_dir is not None:
                field[has_data] = -mean_spd[has_data] * np.sin(
                    np.deg2rad(mean_dir[has_data]))
            return field, mean_dir
        elif variable == "v":
            field = np.full((n_lat, n_lon), np.nan)
            if mean_dir is not None:
                field[has_data] = -mean_spd[has_data] * np.cos(
                    np.deg2rad(mean_dir[has_data]))
            return field, mean_dir
        else:
            return mean_spd, mean_dir

    else:
        raise ValueError(f"Unknown composite method: '{method}'. "
                         f"Use 'last' or 'mean'.")
