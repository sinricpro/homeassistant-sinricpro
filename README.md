# SinricPro for Home Assistant

This custom component integrates [SinricPro](https://sinric.pro/) with Home Assistant, allowing you to control your Home Assistant devices from Amazon Alexa, Google Home, and other SinricPro-supported platforms.

## Features

- Connect Home Assistant to Amazon Alexa and Google Home through SinricPro
- Real-time device updates using Server-Sent Events (SSE)
- Automatically sync devices between Home Assistant and SinricPro
- Currently supports:
  - Switches (with more device types planned for future updates)

## Installation

### HACS (Recommended)

1. Make sure [HACS](https://hacs.xyz/) is installed in your Home Assistant instance
2. Add this repository as a custom repository in HACS:
   - Go to HACS → Integrations → ⋮ (top right) → Custom repositories
   - Enter `https://github.com/sinricpro/homeassistant-sinricpro` as the repository URL
   - Select "Integration" as the category
   - Click "ADD"
3. Click "SinricPro" in the list of integrations, then click "Download"
4. Restart Home Assistant

### Manual Installation

1. Download the latest release from the [releases page](https://github.com/sinricpro/homeassistant-sinricpro/releases)
2. Create a `custom_components` directory in your Home Assistant configuration directory if it doesn't already exist
3. Extract the `sinricpro` directory into the `custom_components` directory
4. Restart Home Assistant

## Setup

1. First, create your devices in SinricPro dashboard:
   - Sign up or log in to [SinricPro](https://sinric.pro/)
   - Add your devices in the SinricPro dashboard
   - Note the device IDs for reference

2. Get your SinricPro API Key:
   - Go to "Credentials" in your SinricPro dashboard
   - Copy your API Key

3. Add the integration to Home Assistant:
   - Go to Configuration → Devices & Services
   - Click "Add Integration"
   - Search for "SinricPro" and select it
   - Enter your API Key

## Usage

After configuring the integration, your SinricPro devices will be available in Home Assistant. You can control them from Home Assistant, and also from Alexa or Google Home through SinricPro.

### Services

The integration provides the following services:

- `sinricpro.refresh_devices`: Force refresh the device list from SinricPro
- `sinricpro.set_device_state`: Set the state of a SinricPro device
  - Parameters:
    - `device_id`: The ID of the SinricPro device (required)
    - `state`: JSON object with the state to set (required)
      - For switches: `{"powerState": "On"}` or `{"powerState": "Off"}`

### Real-time Updates

The integration uses Server-Sent Events (SSE) to receive real-time updates from SinricPro. This means that when you control a device through Alexa or Google Home, the state change will be instantly reflected in Home Assistant.

## Support

For issues, feature requests, or questions, please open an issue on the [GitHub repository](https://github.com/sinricpro/homeassistant-sinricpro/issues).

## License

This project is licensed under the MIT License - see the LICENSE file for details.