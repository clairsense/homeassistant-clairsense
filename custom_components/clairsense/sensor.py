"""Sensors: one per reading a monitor reports."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    UnitOfPressure,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ClairsenseConfigEntry, ClairsenseCoordinator

PARALLEL_UPDATES = 0


def _description(
    key: str,
    *,
    device_class: SensorDeviceClass | None,
    unit: str | None,
    precision: int,
) -> SensorEntityDescription:
    return SensorEntityDescription(
        key=key,
        translation_key=key,
        device_class=device_class,
        native_unit_of_measurement=unit,
        suggested_display_precision=precision,
        state_class=SensorStateClass.MEASUREMENT,
    )


SENSORS: tuple[SensorEntityDescription, ...] = (
    _description(
        "temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        unit=UnitOfTemperature.CELSIUS,
        precision=1,
    ),
    _description(
        "humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        unit=PERCENTAGE,
        precision=0,
    ),
    _description(
        "co2",
        device_class=SensorDeviceClass.CO2,
        unit=CONCENTRATION_PARTS_PER_MILLION,
        precision=0,
    ),
    _description(
        "pm25",
        device_class=SensorDeviceClass.PM25,
        unit=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        precision=1,
    ),
    _description(
        "pressure",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        unit=UnitOfPressure.HPA,
        precision=1,
    ),
    _description(
        "iaq", device_class=SensorDeviceClass.AQI, unit=None, precision=0
    ),
    _description(
        "voc",
        device_class=SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS_PARTS,
        unit=CONCENTRATION_PARTS_PER_MILLION,
        precision=2,
    ),
    _description(
        "infection_risk", device_class=None, unit=PERCENTAGE, precision=0
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClairsenseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add a sensor for every (device, reading) pair, now and as they appear."""
    coordinator = entry.runtime_data
    descriptions = {description.key: description for description in SENSORS}
    known: set[tuple[str, str]] = set()

    @callback
    def _add_new_pairs() -> None:
        new: list[ClairsenseSensor] = []
        for device in coordinator.data.devices.values():
            for key in device.readings:
                if key in descriptions and (device.id, key) not in known:
                    known.add((device.id, key))
                    new.append(
                        ClairsenseSensor(
                            coordinator, device.id, descriptions[key], known
                        )
                    )
        if new:
            async_add_entities(new)

    _add_new_pairs()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_pairs))


class ClairsenseSensor(CoordinatorEntity[ClairsenseCoordinator], SensorEntity):
    """One reading of one monitor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ClairsenseCoordinator,
        device_id: str,
        description: SensorEntityDescription,
        known: set[tuple[str, str]],
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._device_id = device_id
        self._known = known
        self._attr_unique_id = f"{device_id}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Link to the monitor; the coordinator keeps its name, firmware and room."""
        return DeviceInfo(identifiers={(DOMAIN, self._device_id)})

    @property
    def native_value(self) -> float | None:
        """The reading, or None when it is missing."""
        device = self.coordinator.data.devices.get(self._device_id)
        if device is None:
            return None
        return device.readings.get(self.entity_description.key)

    @property
    def available(self) -> bool:
        """Only a live, fresh reading counts; nothing is ever carried over."""
        if not super().available:
            return False
        device = self.coordinator.data.devices.get(self._device_id)
        return (
            device is not None
            and device.online
            and self.entity_description.key in device.readings
        )

    async def async_will_remove_from_hass(self) -> None:
        """Forget the pair so a device that returns gets its sensors again."""
        self._known.discard((self._device_id, self.entity_description.key))
