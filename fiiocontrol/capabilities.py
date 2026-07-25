from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AirLinkCapabilities:
    read_device_state: bool = True
    write_codecs: bool = False
    write_aptx_mode: bool = False
    write_ldac_mode: bool = False
    manage_connections: bool = False
    notifications: bool = False
    pairing: bool = False
    delete_pairing: bool = False

    @property
    def confirmed_labels(self) -> tuple[str, ...]:
        labels = ["Чтение состояния"]
        if self.write_codecs:
            labels.append("Запись кодеков")
        if self.write_aptx_mode:
            labels.append("Режим aptX Adaptive")
        if self.write_ldac_mode:
            labels.append("Режим LDAC")
        if self.manage_connections:
            labels.append("Подключение устройств")
        if self.pairing:
            labels.append("Режим сопряжения")
        if self.notifications:
            labels.append("Discovery events")
        return tuple(labels)


def capabilities_for_firmware(firmware: str | None) -> AirLinkCapabilities:
    confirmed = firmware == "1.4.0"
    return AirLinkCapabilities(
        write_codecs=confirmed,
        write_aptx_mode=confirmed,
        write_ldac_mode=confirmed,
        manage_connections=confirmed,
        pairing=True,
        notifications=True,
    )
