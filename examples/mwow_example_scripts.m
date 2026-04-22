%% MWOW time-series example in MATLAB
% This script:
% 1) Opens one or more MWOW NetCDF files and stacks them along orbit.
% 2) Extracts all data at a single lat/lon point across orbit.
% 3) Matches a ship track (lat/lon/time series) to the nearest MWOW point in
%    space and nearest observation in time.
% 4) Selects a lat/lon region and drops orbit slices that are entirely NaN.
% 5) Plots each orbit in the selected region.
%
% Assumptions for these specific files:
% - Variables are named: latitude, longitude, time, wind_speed.
% - Array order is always [orbit, lat, lon].
% - time uses CF-style units such as 'seconds since 2000-01-01 00:00:00'.

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
% Select nearest lat/lon from MWOW for each ship point, then choose the
% orbit with the nearest observation time.

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
    text(ds_ship.longitude(i), ds_ship.latitude(i), [' ' datestr(ds_ship.time(i), 'yyyy-mm-dd HH:MM:SS')], ...
        'FontSize', 8, 'HorizontalAlignment', 'left', 'VerticalAlignment', 'bottom');
end
hold off;

%% Select an arbitrary region surrounding a lat/lon coordinate
lat_center = -38;
lon_center = 70;

lon_size = 5; % degrees
lat_size = 5; % degrees

% Select our lat/lon region and drop orbit slices that are all NaN.
ds_region = select_region(DS, lat_center, lon_center, lat_size, lon_size);
disp(ds_region)

%% Plot all orbits in the region
n_orbits = numel(ds_region.orbit);
figure('Position', [100 100 900 300 * n_orbits], 'Toolbar', 'none', 'MenuBar', 'none');
for i = 1:n_orbits
    subplot(n_orbits, 1, i);
    imagesc(ds_region.longitude, ds_region.latitude, squeeze(ds_region.wind_speed(i, :, :)));
    set(gca, 'YDir', 'normal');
    axis equal tight;
    xlabel('Longitude [deg]');
    ylabel('Latitude [deg]');
    title(sprintf('Orbit %d', ds_region.orbit(i) - 1));
    colorbar;
end


%% Local functions
function DS = open_mwow_files(paths)
    if ischar(paths) || isstring(paths)
        paths = cellstr(paths);
    end

    first_file = paths{1};
    latitude = double(ncread(first_file, 'latitude'));
    longitude = double(ncread(first_file, 'longitude'));

    latitude = latitude(:);
    longitude = longitude(:);

    wind_speed_all = [];
    time_all = [];

    for k = 1:numel(paths)
        file = paths{k};

        wind_speed = double(ncread(file, 'wind_speed'));
        time_raw = ncread(file, 'time');
        time_dt = decode_cf_time(file, 'time', time_raw);

        wind_speed_all = cat(1, wind_speed_all, wind_speed);
        time_all = cat(1, time_all, time_dt);
    end

    DS = struct();
    DS.latitude = latitude;
    DS.longitude = longitude;
    DS.wind_speed = wind_speed_all;
    DS.time = time_all;
    DS.orbit = (1:size(wind_speed_all, 1)).';
end


function time_dt = decode_cf_time(file, varname, time_raw)
    info = ncinfo(file, varname);
    units = '';

    for i = 1:numel(info.Attributes)
        name = info.Attributes(i).Name;
        value = info.Attributes(i).Value;
        if strcmpi(name, 'units')
            units = value;
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
    [~, ilat] = min(abs(DS.latitude - lat0));
    [~, ilon] = min(abs(DS.longitude - lon0));

    ds_point = struct();
    ds_point.latitude = repmat(DS.latitude(ilat), size(DS.orbit));
    ds_point.longitude = repmat(DS.longitude(ilon), size(DS.orbit));
    ds_point.orbit = DS.orbit;
    ds_point.wind_speed = squeeze(DS.wind_speed(:, ilat, ilon));
    ds_point.time = squeeze(DS.time(:, ilat, ilon));
end


function ds_ship = match_ship_track(DS, ship_lat, ship_lon, ship_time)
    n = numel(ship_lat);

    out_lat = nan(n, 1);
    out_lon = nan(n, 1);
    out_ws = nan(n, 1);
    out_time = NaT(n, 1);
    out_orbit = nan(n, 1);

    for i = 1:n
        [~, ilat] = min(abs(DS.latitude - ship_lat(i)));
        [~, ilon] = min(abs(DS.longitude - ship_lon(i)));

        tvec = squeeze(DS.time(:, ilat, ilon));
        wsvec = squeeze(DS.wind_speed(:, ilat, ilon));

        valid = ~isnat(tvec);
        if ~any(valid)
            continue
        end

        dt = abs(tvec(valid) - ship_time(i));
        [~, jrel] = min(dt);
        valid_idx = find(valid);
        j = valid_idx(jrel);

        out_lat(i) = DS.latitude(ilat);
        out_lon(i) = DS.longitude(ilon);
        out_ws(i) = wsvec(j);
        out_time(i) = tvec(j);
        out_orbit(i) = DS.orbit(j);
    end

    ds_ship = struct();
    ds_ship.latitude = out_lat;
    ds_ship.longitude = out_lon;
    ds_ship.wind_speed = out_ws;
    ds_ship.time = out_time;
    ds_ship.orbit = out_orbit;
end


function ds_region = select_region(DS, lat_center, lon_center, lat_size, lon_size)
    lat_mask = DS.latitude >= (lat_center - lat_size) & DS.latitude <= (lat_center + lat_size);
    lon_mask = DS.longitude >= (lon_center - lon_size) & DS.longitude <= (lon_center + lon_size);

    wind_speed = DS.wind_speed(:, lat_mask, lon_mask);
    time = DS.time(:, lat_mask, lon_mask);

    n_orbit = size(wind_speed, 1);
    valid_orbit = false(n_orbit, 1);
    for k = 1:n_orbit
        valid_orbit(k) = any(~isnan(squeeze(wind_speed(k, :, :))), 'all');
    end

    ds_region = struct();
    ds_region.latitude = DS.latitude(lat_mask);
    ds_region.longitude = DS.longitude(lon_mask);
    ds_region.wind_speed = wind_speed(valid_orbit, :, :);
    ds_region.time = time(valid_orbit, :, :);
    ds_region.orbit = DS.orbit(valid_orbit);
end
