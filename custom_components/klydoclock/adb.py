"""ADB connection to the clock."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from adb_shell.adb_device_async import AdbDeviceTcpAsync
from adb_shell.auth.keygen import keygen
from adb_shell.auth.sign_pythonrsa import PythonRSASigner

_LOGGER = logging.getLogger(__name__)

TIMEOUT = 15


class KlydoConnectionError(Exception):
    """The clock could not be reached over ADB."""


class KlydoRootError(Exception):
    """adbd on the clock refused to restart as root."""


def load_signer(key_path: str) -> PythonRSASigner:
    """Load (or create) the ADB key pair. Blocking."""
    path = Path(key_path)
    if not path.is_file() or not Path(f"{key_path}.pub").is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        keygen(key_path)
    return PythonRSASigner(
        Path(f"{key_path}.pub").read_text(encoding="utf-8"),
        path.read_text(encoding="utf-8"),
    )


class KlydoAdb:
    """Serialised access to one clock."""

    def __init__(self, host: str, port: int, signer: PythonRSASigner | None) -> None:
        self.host = host
        self.port = port
        self._signer = signer
        self._device: AdbDeviceTcpAsync | None = None
        self._lock = asyncio.Lock()
        self._closed = False

    async def _open(self) -> AdbDeviceTcpAsync:
        device = AdbDeviceTcpAsync(self.host, self.port, default_transport_timeout_s=9.0)
        await device.connect(
            rsa_keys=[self._signer] if self._signer else None, auth_timeout_s=10.0
        )
        return device

    async def _ensure_connected(self) -> AdbDeviceTcpAsync:
        if self._device is not None and self._device.available:
            return self._device
        await self._drop()
        device = await self._open()
        uid = (await device.shell("id -u") or "").strip()
        if uid != "0":
            # adbd restarts as root and drops the connection while doing so.
            try:
                await device.root()
            except Exception:  # noqa: BLE001 - connection reset is expected here
                pass
            try:
                await device.close()
            except Exception:  # noqa: BLE001
                pass
            for delay in (1.5, 3.0):
                await asyncio.sleep(delay)
                try:
                    device = await self._open()
                    break
                except Exception:  # noqa: BLE001
                    continue
            else:
                raise KlydoConnectionError("no reconnect after adb root")
            uid = (await device.shell("id -u") or "").strip()
            if uid != "0":
                await device.close()
                raise KlydoRootError(f"adbd is not running as root (uid={uid})")
        self._device = device
        return device

    async def _drop(self) -> None:
        device, self._device = self._device, None
        if device is not None:
            try:
                await device.close()
            except Exception:  # noqa: BLE001
                pass

    async def _call(self, method: str, command: str, decode: bool):
        async with self._lock:
            if self._closed:
                raise KlydoConnectionError(f"{self.host}:{self.port}: connection closed")
            try:
                async with asyncio.timeout(TIMEOUT + 12):
                    device = await self._ensure_connected()
                    return await getattr(device, method)(
                        command, read_timeout_s=TIMEOUT, decode=decode
                    )
            except KlydoRootError:
                await self._drop()
                raise
            except Exception as err:
                await self._drop()
                raise KlydoConnectionError(
                    f"{self.host}:{self.port}: {type(err).__name__}: {err}"
                ) from err

    async def shell(self, command: str) -> str:
        """Run a shell command and return its text output."""
        return (await self._call("shell", command, True) or "").strip()

    async def read_file(self, path: str) -> bytes:
        """Return the raw content of a file on the clock (empty if missing)."""
        return await self._call("exec_out", f"cat '{path}' 2>/dev/null", False) or b""

    async def screencap(self) -> bytes:
        """Return a PNG screenshot of the clock."""
        return await self._call("exec_out", "screencap -p", False) or b""

    async def keyevent(self, keycode: int) -> None:
        """Simulate a remote control key press."""
        await self.shell(f"input keyevent {int(keycode)}")

    async def close(self) -> None:
        """Close the connection for good; later calls fail instead of reconnecting."""
        async with self._lock:
            self._closed = True
            await self._drop()
