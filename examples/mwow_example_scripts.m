%% MWOW time-series example in MATLAB
% This script:
% 1) Opens one or more MWOW NetCDF files and stacks them along orbit.
% 2) Extracts all data at a single lat/lon point across orbit.
% 3) Matches a ship track (lat/lon/time series) to the nearest MWOW point in
%    space and nearest observation in time.
% 4) Selects a lat/lon region and drops orbit slices that are entirely NaN.
% 5) Plots each orbit in the selected region.
%
% Supports both MWOW v0.1 and v0.2 file formats:
%   v0.2: wind_speed(orbit, latitude, longitude) — ncread gives [orbit, lat, lon]
%   v0.1: wind_speed(longitude, latitude, time) — ncread gives [lon, lat, time],
%          permuted to [orbit, lat, lon] for a uniform interface.
%
% v0.1 files may contain duplicate orbits (from double-ingested HY-2B/HY-2C
% granules).  Duplicates are removed when extracting point or region data by
% detecting orbit slots with identical time and wind_speed values.

clear; clc; close all;

%% Start by opening a file or a set of files
folder = '/path_to_mwow_files/';
paths = dir(fullfile(folder, '*.nc'));
paths = fullfile({paths.folder}, {paths.name});

% Read and stack files along orbit
DS = open_mwow_files(paths);
disp(DS)

%% Pull out all data at a single lat/lon coordinate
lat0 = -54;
lon0 = 90;

ds_point = select_point_all_orbits(DS, lat0, lon0);
disp(ds_point)

%% Plot the point data over time
figure('Position', [100 100 1000 350], 'Toolbar', 'none', 'MenuBar', 'none');
scatter(ds_point.time, ds_point.wind_speed, 40, ds_point.orbit, 'filled');
xlabel('Time of Observation [UTC]');
ylabel('Wind Speed [m/s]');
cb = colorbar;
cb.Label.String = 'Orbit Pass Number';
grid on;

%% Set up input data. Replace with user-provided data.
ship_lat = [-38.1, -38.2, -38.3, -38.4, -38.5];
ship_lon = [70.0, 70.1, 70.2, 70.3, 70.4];
ship_time = datetime({ ...
    '2026-03-21T19:35:36', ...
    '2026-03-21T20:35:36', ...
    '2026-03-21T21:35:36', ...
    '2026-03-22T22:35:36', ...
    '2026-03-23T19:35:36'}, ...
    'InputFormat', 'yyyy-MM-dd''T''HH:mm:ss');

%% Perform the interpolation / nearest matching
ds_ship = match_ship_track(DS, ship_lat, ship_lon, ship_time);

%% Plot the matched ship points and label them with time
figure('Position', [100 100 1000 500], 'Toolbar', 'none', 'MenuBar', 'none');
scatter(ds_ship.longitude, ds_ship.latitude, 50, ds_ship.wind_speed, 'filled');
xlabel('Longitude [deg]');
ylabel('Latitude [deg]');
cb = colorbar;
cb.Label.String = 'Wind Speed [m/s]';
grid on;
hold on;
for i = 1:numel(ds_ship.longitude)
    text(ds_ship.longitude(i), ds_ship.latitude(i), ...
        [' ' datestr(ds_ship.time(i), 'yyyy-mm-dd HH:MM:SS')], ...
        'FontSize', 8, 'HorizontalAlignment', 'left', 'VerticalAlignment', 'bottom');
end
hold off;

%% Select an arbitrary region surrounding a lat/lon coordinate
lat_center = -38;
lon_center = 70;
lon_size = 5; % degrees half-width
lat_size = 5;

ds_region = select_region(DS, lat_center, lon_center, lat_size, lon_size);
disp(ds_region)

%% Plot all orbits in the region
n_orbits = numel(ds_region.orbit);
figure('Position', [100 100 900 300 * n_orbits], 'Toolbar', 'none', 'MenuBar', 'none');
for i = 1:n_orbits
    subplot(n_orbits, 1, i);
    % Data is [orbit, lat, lon]; imagesc expects (y, x) = (lat, lon)
    imagesc(ds_region.longitude, ds_region.latitude, ...
            squeeze(ds_region.wind_speed(i, :, :)));
    set(gca, 'YDir', 'normal');
    axis equal tight;
    xlabel('Longitude [deg]');
    ylabel('Latitude [deg]');
    title(sprintf('Orbit %d', ds_region.orbit(i)));
    colorbar;
end


%% =========================================================================
%% Local functions
%% =========================================================================

function DS = open_mwow_files(paths)
% OPEN_MWOW_FILES  Read and stack MWOW NetCDF files along orbit dimension.
%   Supports v0.1 and v0.2 formats.  All data is returned in [orbit, lat, lon]
%   convention regardless of file version.
    if ischar(paths) || isstring(paths)
        paths = cellstr(paths);
    end

    first_file = paths{1};
    version = detect_version(first_file);
    latitude = double(ncread(first_file, 'latitude'));
    longitude = double(ncread(first_file, 'longitude'));
    latitude = latitude(:);
    longitude = longitude(:);

    wind_speed_all = [];
    time_all = [];

    for k = 1:numel(paths)
        file = paths{k};
        [wind_speed, time_dt] = read_one_file(file, version);
        % Both are now [orbit, lat, lon] after read_one_file
        wind_speed_all = cat(1, wind_speed_all, wind_speed);
        time_all = cat(1, time_all, time_dt);
    end

    DS = struct();
    DS.latitude = latitude;
    DS.longitude = longitude;
    DS.wind_speed = wind_speed_all;   % [orbit, lat, lon]
    DS.time = time_all;               % [orbit, lat, lon]
    DS.orbit = (1:size(wind_speed_all, 1)).';
    DS.version = version;
end


function version = detect_version(file)
% DETECT_VERSION  Determine MWOW file version from global attributes or dims.
    info = ncinfo(file);
    version = '0.2';  % default

    % Check global attributes for version_id
    for i = 1:numel(info.Attributes)
        if strcmpi(info.Attributes(i).Name, 'version_id')
            version = info.Attributes(i).Value;
            return
        end
    end

    % Fallback: v0.1 uses 'time' dimension, v0.2 uses 'orbit'
    for i = 1:numel(info.Dimensions)
        if strcmp(info.Dimensions(i).Name, 'orbit')
            version = '0.2';
            return
        end
    end
    version = '0.1';
end


function [wind_speed, time_dt] = read_one_file(file, version)
% READ_ONE_FILE  Read wind_speed and time from one file, return [orbit, lat, lon].
    if startsWith(version, '0.1')
        % v0.1: ncread gives [lon, lat, time] (matching ncdump dimension order)
        ws_raw = double(ncread(file, 'wind_speed'));   % [lon, lat, time]
        time_raw = ncread(file, 'time');               % [lon, lat, time]
        time_dt = decode_cf_time(file, 'time', time_raw);

        % Permute to [orbit, lat, lon] (orbit = time dim)
        wind_speed = permute(ws_raw, [3, 2, 1]);      % [time, lat, lon]
        time_dt = permute(time_dt, [3, 2, 1]);
    else
        % v0.2: ncread gives [orbit, lat, lon]
        wind_speed = double(ncread(file, 'wind_speed'));
        time_raw = ncread(file, 'time');
        time_dt = decode_cf_time(file, 'time', time_raw);
    end
end


function time_dt = decode_cf_time(file, varname, time_raw)
% DECODE_CF_TIME  Convert CF-convention time values to MATLAB datetime.
    info = ncinfo(file, varname);
    units = '';

    for i = 1:numel(info.Attributes)
        if strcmpi(info.Attributes(i).Name, 'units')
            units = info.Attributes(i).Value;
        end
    end

    if isempty(units)
        error('Could not find time units attribute for variable %s.', varname);
    end

    units = char(units);
    tokens = regexp(units, '^(\w+) since (.+)$', 'tokens', 'once');
    if isempty(tokens)
        error('Unsupported time units: %s', units);
    end

    unit_name = lower(tokens{1});
    ref_string = strtrim(tokens{2});
    ref_string = regexprep(ref_string, ' UTC$', '');
    ref_string = regexprep(ref_string, ' GMT$', '');
    ref_time = parse_reference_time(ref_string);
    time_raw = double(time_raw);

    switch unit_name
        case {'second', 'seconds', 'sec', 'secs'}
            time_dt = ref_time + seconds(time_raw);
        case {'minute', 'minutes', 'min', 'mins'}
            time_dt = ref_time + minutes(time_raw);
        case {'hour', 'hours', 'hr', 'hrs'}
            time_dt = ref_time + hours(time_raw);
        case {'day', 'days'}
            time_dt = ref_time + days(time_raw);
        otherwise
            error('Unsupported CF time unit: %s', unit_name);
    end
end


function ref_time = parse_reference_time(ref_string)
    formats = { ...
        'yyyy-MM-dd HH:mm:ss', ...
        'yyyy-MM-dd HH:mm:ss.SSS', ...
        'yyyy-MM-dd''T''HH:mm:ss', ...
        'yyyy-MM-dd''T''HH:mm:ss.SSS', ...
        'yyyy-MM-dd'};
    ref_time = [];
    for i = 1:numel(formats)
        try
            ref_time = datetime(ref_string, 'InputFormat', formats{i});
            break
        catch
        end
    end
    if isempty(ref_time)
        error('Could not parse reference time string: %s', ref_string);
    end
end


function ds_point = select_point_all_orbits(DS, lat0, lon0)
% SELECT_POINT_ALL_ORBITS  Extract time series at nearest grid point.
%   Deduplicates orbits with identical time and wind_speed values.
    [~, ilat] = min(abs(DS.latitude - lat0));
    [~, ilon] = min(abs(DS.longitude - lon0));

    % Data is [orbit, lat, lon]
    ws_vec = squeeze(DS.wind_speed(:, ilat, ilon));
    t_vec = squeeze(DS.time(:, ilat, ilon));

    % Remove fill/NaT orbits
    valid = ~isnat(t_vec) & ~isnan(ws_vec);
    ws_vec = ws_vec(valid);
    t_vec = t_vec(valid);
    orbit_idx = find(valid);

    % Deduplicate: remove orbits with same time and wind_speed
    keep = deduplicate_orbits(t_vec, ws_vec);
    ws_vec = ws_vec(keep);
    t_vec = t_vec(keep);
    orbit_idx = orbit_idx(keep);

    ds_point = struct();
    ds_point.latitude = repmat(DS.latitude(ilat), size(orbit_idx));
    ds_point.longitude = repmat(DS.longitude(ilon), size(orbit_idx));
    ds_point.orbit = orbit_idx;
    ds_point.wind_speed = ws_vec;
    ds_point.time = t_vec;
end


function ds_ship = match_ship_track(DS, ship_lat, ship_lon, ship_time)
% MATCH_SHIP_TRACK  Find nearest MWOW observation for each ship track point.
    n = numel(ship_lat);
    out_lat = nan(n, 1);
    out_lon = nan(n, 1);
    out_ws = nan(n, 1);
    out_time = NaT(n, 1);
    out_orbit = nan(n, 1);

    for i = 1:n
        [~, ilat] = min(abs(DS.latitude - ship_lat(i)));
        [~, ilon] = min(abs(DS.longitude - ship_lon(i)));

        % Data is [orbit, lat, lon]
        tvec = squeeze(DS.time(:, ilat, ilon));
        wsvec = squeeze(DS.wind_speed(:, ilat, ilon));

        valid = ~isnat(tvec) & ~isnan(wsvec);
        if ~any(valid)
            continue
        end

        % Deduplicate
        tvec_v = tvec(valid);
        wsvec_v = wsvec(valid);
        keep = deduplicate_orbits(tvec_v, wsvec_v);
        tvec_v = tvec_v(keep);
        wsvec_v = wsvec_v(keep);

        dt = abs(tvec_v - ship_time(i));
        [~, j] = min(dt);

        out_lat(i) = DS.latitude(ilat);
        out_lon(i) = DS.longitude(ilon);
        out_ws(i) = wsvec_v(j);
        out_time(i) = tvec_v(j);
        out_orbit(i) = j;
    end

    ds_ship = struct();
    ds_ship.latitude = out_lat;
    ds_ship.longitude = out_lon;
    ds_ship.wind_speed = out_ws;
    ds_ship.time = out_time;
    ds_ship.orbit = out_orbit;
end


function ds_region = select_region(DS, lat_center, lon_center, lat_size, lon_size)
% SELECT_REGION  Extract regional subset and drop empty/duplicate orbits.
    lat_mask = DS.latitude >= (lat_center - lat_size) & ...
               DS.latitude <= (lat_center + lat_size);
    lon_mask = DS.longitude >= (lon_center - lon_size) & ...
               DS.longitude <= (lon_center + lon_size);

    % Data is [orbit, lat, lon]
    wind_speed = DS.wind_speed(:, lat_mask, lon_mask);
    time_data = DS.time(:, lat_mask, lon_mask);

    n_orbit = size(wind_speed, 1);

    % Drop orbits that are entirely NaN
    valid_orbit = false(n_orbit, 1);
    for k = 1:n_orbit
        valid_orbit(k) = any(~isnan(squeeze(wind_speed(k, :, :))), 'all');
    end
    wind_speed = wind_speed(valid_orbit, :, :);
    time_data = time_data(valid_orbit, :, :);
    orbits_kept = DS.orbit(valid_orbit);

    % Deduplicate orbits: use center point as reference for duplicate detection
    n_kept = size(wind_speed, 1);
    if n_kept > 1
        nlat = size(wind_speed, 2);
        nlon = size(wind_speed, 3);
        clat = ceil(nlat / 2);
        clon = ceil(nlon / 2);
        ref_t = squeeze(time_data(:, clat, clon));
        ref_ws = squeeze(wind_speed(:, clat, clon));
        keep = deduplicate_orbits(ref_t, ref_ws);
        wind_speed = wind_speed(keep, :, :);
        time_data = time_data(keep, :, :);
        orbits_kept = orbits_kept(keep);
    end

    ds_region = struct();
    ds_region.latitude = DS.latitude(lat_mask);
    ds_region.longitude = DS.longitude(lon_mask);
    ds_region.wind_speed = wind_speed;
    ds_region.time = time_data;
    ds_region.orbit = orbits_kept;
end


function keep = deduplicate_orbits(t_vec, ws_vec)
% DEDUPLICATE_ORBITS  Remove orbits with identical time and wind_speed.
%   Returns logical mask of orbits to keep.
%
%   In MWOW v0.1, duplicate orbits arise from double-ingested HY-2B/HY-2C
%   granules, producing multiple time slots with identical measurements.
    n = numel(t_vec);
    keep = true(n, 1);

    for i = 2:n
        if ~keep(i)
            continue
        end
        for j = 1:i-1
            if ~keep(j)
                continue
            end
            % Check if both have valid data and are duplicates
            if isnat(t_vec(i)) || isnat(t_vec(j))
                continue
            end
            if isnan(ws_vec(i)) || isnan(ws_vec(j))
                continue
            end
            if abs(seconds(t_vec(i) - t_vec(j))) < 1.0 && ...
               abs(ws_vec(i) - ws_vec(j)) < 0.001
                keep(i) = false;
                break
            end
        end
    end
end
