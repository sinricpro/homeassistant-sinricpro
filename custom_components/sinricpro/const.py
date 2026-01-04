"""Constants for the SinricPro integration."""

from __future__ import annotations

from typing import Final

# Integration domain
DOMAIN: Final = "sinricpro"

# API endpoints
# Production URLs
API_BASE_URL: Final = "https://api.sinric.pro"
SSE_URL: Final = "https://sse.sinric.pro/sse/stream"
API_DEVICES_ENDPOINT: Final = "/api/v1/devices"
API_ACTION_ENDPOINT: Final = "/api/v1/devices/{device_id}/action"

# API headers
HEADER_API_KEY: Final = "x-sinric-api-key"

# Device types
DEVICE_TYPE_SWITCH: Final = "sinric.devices.types.SWITCH"
DEVICE_TYPE_LIGHT: Final = "sinric.devices.types.LIGHT"
DEVICE_TYPE_BLIND: Final = "sinric.devices.types.BLIND"
DEVICE_TYPE_DOORBELL: Final = "sinric.devices.types.DOORBELL"
DEVICE_TYPE_FAN: Final = "sinric.devices.types.FAN"
DEVICE_TYPE_GARAGE_DOOR: Final = "sinric.devices.types.GARAGE_DOOR"
DEVICE_TYPE_SMARTLOCK: Final = "sinric.devices.types.SMARTLOCK"
DEVICE_TYPE_SPEAKER: Final = "sinric.devices.types.SPEAKER"
DEVICE_TYPE_DIMMABLE_SWITCH: Final = "sinric.devices.types.DIMMABLE_SWITCH"
DEVICE_TYPE_TV: Final = "sinric.devices.types.TV"
DEVICE_TYPE_THERMOSTAT: Final = "sinric.devices.types.THERMOSTAT"
DEVICE_TYPE_AC_UNIT: Final = "sinric.devices.types.AC_UNIT"
DEVICE_TYPE_AIR_QUALITY_SENSOR: Final = "sinric.devices.types.AIR_QUALITY_SENSOR"
DEVICE_TYPE_CONTACT_SENSOR: Final = "sinric.devices.types.CONTACT_SENSOR"
DEVICE_TYPE_MOTION_SENSOR: Final = "sinric.devices.types.MOTION_SENSOR"
DEVICE_TYPE_TEMPERATURE_SENSOR: Final = "sinric.devices.types.TEMPERATURESENSOR"

# Power states
POWER_STATE_ON: Final = "On"
POWER_STATE_OFF: Final = "Off"
POWER_STATE_ON_LOWER: Final = "on"
POWER_STATE_OFF_LOWER: Final = "off"

# Actions
ACTION_SET_POWER_STATE: Final = "setPowerState"
ACTION_SET_BRIGHTNESS: Final = "setBrightness"
ACTION_SET_COLOR: Final = "setColor"
ACTION_SET_COLOR_TEMPERATURE: Final = "setColorTemperature"
ACTION_SET_RANGE_VALUE: Final = "setRangeValue"
ACTION_SET_MODE: Final = "setMode"
ACTION_SET_LOCK_STATE: Final = "setLockState"
ACTION_SET_VOLUME: Final = "setVolume"
ACTION_SET_MUTE: Final = "setMute"
ACTION_SET_POWER_LEVEL: Final = "setPowerLevel"
ACTION_SKIP_CHANNELS: Final = "skipChannels"
ACTION_MEDIA_CONTROL: Final = "mediaControl"
ACTION_TARGET_TEMPERATURE: Final = "targetTemperature"
ACTION_SET_THERMOSTAT_MODE: Final = "setThermostatMode"
ACTION_CURRENT_TEMPERATURE: Final = "currentTemperature"
ACTION_AIR_QUALITY: Final = "airQuality"
ACTION_SET_CONTACT_STATE: Final = "setContactState"
ACTION_MOTION: Final = "motion"
ACTION_DOORBELL_PRESS: Final = "DoorbellPress"
ACTION_TYPE_REQUEST: Final = "request"
ACTION_TYPE_EVENT: Final = "event"

# Garage door modes
GARAGE_DOOR_MODE_OPEN: Final = "Open"
GARAGE_DOOR_MODE_CLOSE: Final = "Close"

# Lock states
LOCK_STATE_LOCKED: Final = "LOCKED"
LOCK_STATE_UNLOCKED: Final = "UNLOCKED"
# Lock action values (lowercase for API requests)
LOCK_ACTION_LOCK: Final = "lock"
LOCK_ACTION_UNLOCK: Final = "unlock"

# Color temperature range (Kelvin)
# SinricPro supports: Warm White (2200K), Soft White (2700K), White (4000K),
# Daylight White (5500K), Cool White (7000K)
COLOR_TEMP_MIN_KELVIN: Final = 2200
COLOR_TEMP_MAX_KELVIN: Final = 7000

# Client ID
CLIENT_ID: Final = "home-assistant"

# Timeouts and intervals (in seconds)
DEFAULT_TIMEOUT: Final = 30
DEFAULT_SCAN_INTERVAL: Final = 1800  # 30 minutes

# SSE reconnection settings
SSE_INITIAL_BACKOFF: Final = 1  # seconds
SSE_MAX_BACKOFF: Final = 60  # seconds
SSE_BACKOFF_MULTIPLIER: Final = 2
SSE_MAX_RECONNECTION_ATTEMPTS: Final = 10

# API retry settings
API_MAX_RETRIES: Final = 3
API_RETRY_BACKOFF: Final = 1  # seconds

# Manufacturer info
MANUFACTURER: Final = "SinricPro"

# Logging
LOGGER_NAME: Final = "custom_components.sinricpro"
