# Clairsense for Home Assistant

![Clairsense](custom_components/clairsense/brand/logo.png)

This integration shows the readings of your Clairsense indoor air-quality monitors in Home Assistant. It is read-only: it reports measurements and does not control anything.

It talks to the Clairsense cloud, so Home Assistant needs an internet connection. The monitors themselves are not contacted directly.

This is a community integration, not an official Home Assistant product.

## Requirements

- Home Assistant 2025.4 or newer
- A Clairsense account with at least one device
- A GitHub account. Home Assistant asks for it when you add this repository by its link.
- On Home Assistant 2026.10 and older: [HACS](https://hacs.xyz). Newer versions have the Marketplace built in.
- Home Assistant's default `my` integration enabled (it is on by default). Signing in uses it to return you to Home Assistant.

## Install

### Home Assistant 2026.11 and newer

1. Go to **Settings > Marketplace**. The first time, read the notice, tick **I understand the risks and agree** and continue.
2. Choose **Add from link**, paste `https://github.com/clairsense/homeassistant-clairsense` and choose **Add**.
3. If Home Assistant asks you to connect GitHub, open the page it names and enter the code it shows.
4. Open **Clairsense** in the Marketplace, choose **Install** and confirm.

No restart is needed. Home Assistant starts the Clairsense set-up right after the install.

### Home Assistant 2025.4 to 2026.10

1. Open HACS and choose the three-dot menu, then **Custom repositories**.
2. Add `https://github.com/clairsense/homeassistant-clairsense` with the type **Integration**.
3. Find **Clairsense** in HACS, download it, and restart Home Assistant.

## Set up

1. If the set-up did not start by itself, go to **Settings > Devices & services > Add integration** and choose **Clairsense**.
2. Choose **Open website**, sign in with your Clairsense account in the page that opens, and approve the access request.
3. Your devices appear in Home Assistant, each with the sensors it reports.

## Sensors

| Sensor | What it is | Unit |
| --- | --- | --- |
| Temperature | Air temperature | °C |
| Humidity | Relative humidity | % |
| Carbon dioxide | CO₂ concentration | ppm |
| PM2.5 | Fine particulate matter | µg/m³ |
| Pressure | Air pressure | hPa |
| Air quality index | Overall air-quality index | none |
| Volatile organic compounds | VOC concentration | ppm |
| Infection risk | Estimated infection risk | % |

A sensor appears the first time a device reports that reading.

## Behaviour

- Readings are fetched every 60 seconds.
- A reading older than 3 minutes is left out by the cloud, so its sensor shows as unavailable. A device that is offline shows all of its sensors as unavailable. Home Assistant never shows zero or an old value in their place.
- Devices you add or remove in the Clairsense app appear or disappear on the next update, without reloading the integration.
- Each device shows its name, room, model and firmware version from your Clairsense account. A new name or firmware version follows on the next update; a name or area you set in Home Assistant stays as you set it.
- One Home Assistant install can be linked to a Clairsense account at a time. Linking a second install replaces the first, which then asks you to sign in again.
- On first-generation units, the CO₂ and VOC figures are estimates calculated from the gas sensor, not direct measurements.

## Troubleshooting

Home Assistant asks you to sign in to Clairsense again when:

- another Home Assistant install signs in to the same Clairsense account. The newest sign-in replaces the older one, so the first install asks you to sign in again.
- you restore a Home Assistant backup. The sign-in saved in the backup is no longer valid, so sign in again when asked.

## Removal

Remove the integration under **Settings > Devices & services > Clairsense > Delete**. This also unlinks your account on the Clairsense side. You can then uninstall it: open **Clairsense** in the Marketplace and choose **Uninstall** in the three-dot menu, or remove the repository in HACS on older versions.

## Development

```bash
python -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest -q
```

The tests need a Python version supported by the pinned Home Assistant release (currently Python 3.14).

To test against the oldest supported release, Home Assistant 2025.4, use Python 3.13 and `requirements_test_min.txt` instead. CI runs both.

## License

MIT. See [LICENSE](LICENSE).
