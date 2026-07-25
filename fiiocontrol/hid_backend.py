from __future__ import annotations

from dataclasses import dataclass
from typing import Any


VENDOR_ID = 0x2972
PRODUCT_ID = 0x0158


class HidBackendUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class HidDescriptor:
    path: bytes
    product_string: str | None
    manufacturer_string: str | None
    serial_number: str | None
    interface_number: int | None
    usage_page: int | None
    usage: int | None


def _load_hid() -> Any:
    try:
        import hid
    except ImportError as error:
        raise HidBackendUnavailable(
            "Python package 'hidapi' is not installed. Run: python -m pip install -e ."
        ) from error
    return hid


def enumerate_air_link() -> list[HidDescriptor]:
    hid = _load_hid()
    return [
        HidDescriptor(
            path=item["path"],
            product_string=item.get("product_string"),
            manufacturer_string=item.get("manufacturer_string"),
            serial_number=item.get("serial_number"),
            interface_number=item.get("interface_number"),
            usage_page=item.get("usage_page"),
            usage=item.get("usage"),
        )
        for item in hid.enumerate(VENDOR_ID, PRODUCT_ID)
    ]


def control_descriptors() -> list[HidDescriptor]:
    return [
        descriptor
        for descriptor in enumerate_air_link()
        if descriptor.usage_page == 0xFF00 and descriptor.usage == 3
    ]


def is_air_link_present(path: bytes | None = None) -> bool:
    descriptors = control_descriptors()
    if path is None:
        return bool(descriptors)
    return any(descriptor.path == path for descriptor in descriptors)


class HidApiDevice:
    def __init__(self, descriptor: HidDescriptor) -> None:
        hid = _load_hid()
        self.descriptor = descriptor
        self._handle = hid.device()
        self._handle.open_path(descriptor.path)

    def write(self, data: bytes) -> int:
        return int(self._handle.write(data))

    def read(self, size: int, timeout_ms: int) -> list[int]:
        return self._handle.read(size, timeout_ms)

    def close(self) -> None:
        self._handle.close()
