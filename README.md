# Felt Temperature

An easy-to-use “felt temperature” sensor for Home Assistant based on a simplified UTCI‑like approach. It combines temperature, humidity and (optionally) wind to estimate how the weather feels.

This is a pragmatic approximation, not the official UTCI. It’s built for simple setup and fast results.

## Requirements
- Temperature and relative humidity sources are required.
- Wind source is optional (recommended for better realism).
- You can either select one `weather.*` entity (which provides all values) or choose separate sources for each.

## Installation
1. Copy this custom component into `custom_components/felt_temperature/` or install via HACS (if available).
2. Restart Home Assistant.
3. Add the integration: Settings → Devices & Services → Add Integration → Felt Temperature.

## Configuration

You can configure the integration in two ways:

1) Weather mode (recommended)
- Select a single `weather.*` entity (e.g. `weather.home`).
- The integration reads temperature, humidity and wind from the weather entity.
- If wind is not available, it will be ignored (treated as 0 m/s).

2) Separate sources
- Select a temperature source (sensor/climate/weather) – required.
- Select a humidity source (sensor/climate/weather) – required.
- Select a wind source (sensor/weather) – optional.

Tips
- Prefer outdoor sensors for an outdoor felt temperature.
- Ensure correct units: °C, %, and m/s (conversion is handled when possible).

## Entity attributes
- `temperature_source` / `temperature_source_value`
- `humidity_source` / `humidity_source_value`
- `wind_speed_source` / `wind_speed_source_value`

## How it works (short)
The integration uses a simple equation inspired by apparent temperature concepts:

```
felt ≈ Ta + 0.33 * e - 0.70 * Va - 4.00
```

where `e` is vapor pressure derived from temperature and RH, `Va` is wind speed in m/s, and `Ta` is air temperature in °C. This is intentionally simplified for reliability and performance.

## Troubleshooting
- Sensor shows no value: make sure temperature and humidity sources are available and not `unknown`/`unavailable`.
- Wind is ignored: wind source missing or not providing a numeric value.
- Odd values: verify units and that sensors are outdoor if that’s your use case.

## Notes
- This is an approximation of felt temperature and not the full UTCI implementation.
- Contributions and issues: see the issue tracker.

