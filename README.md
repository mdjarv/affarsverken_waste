
# Affärsverken Waste Collection Integration for Home Assistant

[![HACS Badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/hacs/integration)

This integration provides sensors for monitoring waste collection schedules from Affärsverken in Home Assistant. It is designed to be fully compatible with the Home Assistant Community Store (HACS).

## Features

- **Automatic discovery of waste collection schedules:** The integration fetches data from the Affärsverken API to find the next pickup dates for your address.
- **Sensors for each waste type:** A dedicated sensor is created for each type of waste (e.g., "Hushållsavfall," "Trädgårdsavfall").
- **Rich sensor attributes:** Each sensor includes detailed attributes such as:
    - `days_until_pickup`
    - `pickup_date`
    - `is_today`, `is_tomorrow`, `is_this_week`
    - `pickup_weekday`
- **Configurable through the UI:** Set up the integration directly from the Home Assistant frontend.
- **Efficient data fetching:** The integration caches API responses to avoid unnecessary requests.

## Installation

### Prerequisites

- Home Assistant installation.
- HACS installed and configured.

### Installation with HACS

1.  **Add the repository:**
    - Open HACS in your Home Assistant instance.
    - Go to the "Integrations" section.
    - Click the three dots in the top right corner and select "Custom repositories."
    - Add the URL to this repository (`https://github.com/mdjarv/affarsverken_waste`) and select the "Integration" category.
    - Click "Add."

2.  **Install the integration:**
    - Search for "Affärsverken Waste Collection" in HACS.
    - Click "Install."
    - Restart Home Assistant.

## Configuration

1.  **Go to Settings > Devices & Services.**
2.  **Click "Add Integration" and search for "Affärsverken Waste Collection."**
3.  **Enter your address (for example "Drottninggatan 1") and an optional name for the integration instance like "Home".**
4.  **Click "Submit."**

The integration will automatically create sensors for each waste collection type associated with your address.

## Usage

Once configured, you can use the sensors in your automations, scripts, and Lovelace dashboards. For example, you can create an automation to notify you the day before waste collection.

### Example Markdown Card

Here is an example of a markdown card that displays the pickup schedule for a specific waste type. This card will show whether the pickup is today, tomorrow, or in a number of days.

```yaml
type: markdown
content: |
  {% set sensor = 'sensor.hemma_restavfall' %}
  # Restavfall
  {% if state_attr(sensor, 'is_today') %}
  ## Idag!
  {% elif state_attr(sensor, 'is_tomorrow') %}
  ## Imorgon!
  {% else %}
  ## Om {{ state_attr(sensor, 'days_until_pickup') }} dagar
  ### På {{ state_attr(sensor, 'pickup_weekday') }}, {{ state_attr(sensor, 'pickup_date') }}
  {% endif %}
```

### Example Automation

Here is an example of an automation that sends a notification at 8:00 PM the day before the waste collection.

```yaml
alias: Waste Collection Reminder
description: ""
trigger:
  - platform: time
    at: "20:00:00"
condition:
  - condition: state
    entity_id: sensor.your_waste_sensor # Change this to your sensor
    attribute: is_tomorrow
    state: true
action:
  - service: notify.mobile_app_your_device # Change this to your notification service
    data:
      title: ️ Waste Collection Tomorrow
      message: Time to put out the bins!
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
