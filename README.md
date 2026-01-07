# SinricPro Home Assistant Integration

[![CI](https://github.com/sinricpro/homeassistant-sinricpro/actions/workflows/ci.yml/badge.svg)](https://github.com/sinricpro/homeassistant-sinricpro/actions/workflows/ci.yml)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Home Assistant custom integration for [SinricPro](https://sinric.pro) that allows you to control your SinricPro devices from Home Assistant.

## Features

- **16 Device Types Supported** - Comprehensive support for SinricPro devices
- **UI-based Configuration** - No YAML required
- **Real-time Updates** - Server-Sent Events (SSE) for instant state synchronization
- **Automatic Reconnection** - Exponential backoff for reliable connection
- **Smart State Management** - Pending state with SSE confirmation
- **Alert Notifications** - Receive SinricPro alerts as Home Assistant notifications
- **Event Automation** - Fire events for advanced automation scenarios

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Click on "Integrations"
3. Click the three dots in the top right corner and select "Custom repositories"
4. Add the repository URL: `https://github.com/sinricpro/homeassistant-sinricpro`
5. Select "Integration" as the category
6. Click "Add"
7. Search for "SinricPro" and install it
8. Restart Home Assistant

### Manual Installation

1. Download the latest release from the [releases page](https://github.com/sinricpro/homeassistant-sinricpro/releases)
2. Extract the `sinricpro` folder to your `custom_components` directory
3. Restart Home Assistant

## Configuration

1. Go to **Settings** > **Devices & Services**
2. Click **+ Add Integration**
3. Search for "SinricPro"
4. Enter your SinricPro API key
5. Click **Submit**

### Getting Your API Key

1. Log in to your [SinricPro Dashboard](https://portal.sinric.pro)
2. Navigate to **Credentials**
3. Copy your API key

## Supported Devices

This integration supports **16 SinricPro device types** mapped to Home Assistant platforms:

| SinricPro Device Type | HA Platform | Features |
|----------------------|-------------|----------|
| **Switch** | `switch` | On/Off control |
| **Light** | `light` | On/Off, Brightness (0-100), RGB Color, Color Temperature (2200K-7000K) |
| **Dimmable Switch** | `light` | On/Off, Power Level (0-100) - appears as dimmable light |
| **Blinds** | `cover` | Open/Close, Position (0-100) |
| **Doorbell** | `event` + `button` + `sensor` | Press event, Manual trigger button, Last ring timestamp sensor |
| **Fan** | `fan` | On/Off, Speed control (1 to max speed levels) |
| **Garage Door** | `cover` | Open/Close control |
| **Smart Lock** | `lock` | Lock/Unlock control |
| **Speaker** | `media_player` | On/Off, Volume (0-100), Mute/Unmute |
| **TV** | `media_player` | On/Off, Volume, Mute, Channel Up/Down, Play/Pause |
| **Thermostat** | `climate` | On/Off, Target Temperature, HVAC Mode (Heat/Cool/Auto/Off), Current Temperature, Humidity |
| **Window AC Unit** | `climate` | All thermostat features + Fan Mode (Low/Medium/High), ECO mode support |
| **Air Quality Sensor** | `sensor` | PM1.0, PM2.5, PM10 measurements (µg/m³) |
| **Contact Sensor** | `binary_sensor` | Open/Closed state detection |
| **Motion Sensor** | `binary_sensor` | Motion detected/not detected |
| **Temperature Sensor** | `sensor` | Temperature (°C), Humidity (%) |

### Device Features Details

#### Climate Devices (Thermostat & AC Unit)
- **Pending State Pattern**: Shows "unknown" while waiting for SSE confirmation (10s timeout)
- **AC Unit Extra**: Fan speed control with 3 levels (Low/Medium/High)
- **Retry Logic**: Automatic retry on timeout errors

#### Media Players (Speaker & TV)
- **TV Extra Features**: Channel navigation and playback control
- **Volume**: Displayed as 0.0-1.0 in Home Assistant (converted from 0-100)

#### Sensors
- **Real-time Updates**: All sensor values update via SSE events
- **Air Quality**: Individual sensors for each PM measurement
- **Temperature Sensor**: Provides both temperature and humidity entities

#### Binary Sensors
- **Contact Sensor**: Door/window open/close detection
- **Motion Sensor**: Motion presence detection with timestamp tracking

### SinricPro Alerts

The integration also handles **SinricPro alerts** (warnings, errors):
- **Persistent Notifications**: Alerts appear in HA notification panel
- **Event Firing**: `sinricpro_alert` event for automation
- **Device Context**: Shows device name when alert is device-specific

Example alert automation:
```yaml
automation:
  - alias: "SinricPro Alert Notification"
    trigger:
      - platform: event
        event_type: sinricpro_alert
    action:
      - service: notify.mobile_app
        data:
          message: "{{ trigger.event.data.message }}"
```

# Development

1. Start the environment: ./dev.sh start
2. Open http://localhost:8123 and create an admin account
3. Add the integration:
   - Settings → Devices & Services → + Add Integration
   - Search "SinricPro"
   - Enter your API key
4. Monitor logs:
./dev.sh logs
5. After code changes:
./dev.sh restart

## Troubleshooting

### Common Issues

#### "Invalid API key" error

- Verify your API key is correct
- Ensure you're using the API key from the SinricPro dashboard (not the App Key)
- Check that your API key hasn't expired

#### Devices not appearing

- Make sure your devices are properly configured in SinricPro
- Check that the devices are online in the SinricPro dashboard
- Try reloading the integration

#### State not updating

- The integration uses SSE for real-time updates with a 5-minute polling fallback
- Check your network connection
- Review the Home Assistant logs for connection errors

### Enabling Debug Logging

Add the following to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.sinricpro: debug
```

### Getting Help

If you encounter issues:

1. Check the [existing issues](https://github.com/sinricpro/homeassistant-sinricpro/issues)
2. Enable debug logging and capture relevant logs
3. Open a [new issue](https://github.com/sinricpro/homeassistant-sinricpro/issues/new/choose) with:
   - Integration version
   - Home Assistant version
   - Relevant logs
   - Steps to reproduce

## Contributing

Contributions are welcome! Please read our [contributing guidelines](CONTRIBUTING.md) before submitting a pull request.

### Development Setup

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   pip install -r requirements_test.txt
   ```
3. Run tests:
   ```bash
   pytest tests/
   ```
4. Run linting:
   ```bash
   ruff check .
   ruff format --check .
   mypy custom_components/sinricpro
   ```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.


## Acknowledgements

- [Home Assistant](https://www.home-assistant.io/) for the amazing home automation platform
- [SinricPro](https://sinric.pro) for the IoT platform

