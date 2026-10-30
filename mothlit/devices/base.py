"""Common contract between the UI and the device adapters."""

from typing import Any, Protocol


class DeviceError(Exception):
    """Failed to talk to a device.

    The message is already user-friendly and can go straight to the status bar.
    """


class Device(Protocol):
    name: str

    def turn_on(self) -> None: ...

    def turn_off(self) -> None: ...

    def state(self) -> Any: ...
