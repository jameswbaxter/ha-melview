"""Client for the MelView API (Mitsubishi Electric Wi-Fi Control, AU/NZ).

Everything here is async and runs on one aiohttp session handed in by the
integration, so nothing blocks Home Assistant's event loop. Reads only ever
come from the data cached by the last refresh; the coordinator decides when
to refresh.
"""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from homeassistant.components.climate import HVACMode

from .const import APIVERSION, APPVERSION, HEADERS

_LOGGER = logging.getLogger(__name__)

API_URL = "https://api.melview.net/api"
TIMEOUT = ClientTimeout(total=20)

# The unit's own Wi-Fi adapter takes the command MelView encodes for it
LOCAL_DATA = """<?xml version="1.0" encoding="UTF-8"?>
<CSV>
    <CONNECT>ON</CONNECT>
    <CODE>
        <VALUE>{}</VALUE>
    </CODE>
</CSV>"""

# HA's modes to MelView's setmode values
MODE = {
    HVACMode.AUTO: 8,
    HVACMode.HEAT: 1,
    HVACMode.COOL: 3,
    HVACMode.DRY: 2,
    HVACMode.FAN_ONLY: 7,
}

# Fan speed names by MelView setfan value, for each number of fan stages
FANSTAGES = {
    1: {5: "On"},
    2: {2: "Low", 5: "High"},
    3: {2: "Low", 3: "Medium", 5: "High"},
    4: {2: "Low", 3: "Medium Low", 5: "Medium High", 6: "High"},
    5: {1: "Low", 2: "Medium Low", 3: "Medium", 5: "Medium High", 6: "High"},
}
FAN_AUTO = 0


class MelViewError(Exception):
    """MelView did not answer as expected."""


class MelViewAuthError(MelViewError):
    """MelView rejected the login."""


class MelViewAuthentication:
    """The MelView login, kept as its auth cookie."""

    def __init__(self, session: ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._cookie: str | None = None

    async def async_login(self) -> None:
        """Log in, keeping the auth cookie. Raises MelViewAuthError."""
        self._cookie = None
        try:
            async with self._session.post(
                f"{API_URL}/login.aspx",
                json={"user": self._email, "pass": self._password, "appversion": APPVERSION},
                headers=HEADERS,
                timeout=TIMEOUT,
            ) as resp:
                if resp.status != 200:
                    raise MelViewAuthError(f"login answered {resp.status}")
                cookie = resp.cookies.get("auth")
        except ClientError as err:
            raise MelViewError(f"login failed: {err}") from err
        if cookie is None or len(cookie.value) <= 5:
            raise MelViewAuthError("login returned no auth cookie")
        self._cookie = cookie.value

    async def async_post(self, path: str, payload: dict[str, Any]) -> Any:
        """POST to the API as the logged-in user, logging in again once on a 401."""
        if self._cookie is None:
            await self.async_login()
        for attempt in (1, 2):
            try:
                async with self._session.post(
                    f"{API_URL}/{path}",
                    json=payload,
                    headers=HEADERS,
                    cookies={"auth": self._cookie},
                    timeout=TIMEOUT,
                ) as resp:
                    if resp.status == 401 and attempt == 1:
                        _LOGGER.debug("%s answered 401, logging in again", path)
                    elif resp.status != 200:
                        raise MelViewError(f"{path} answered {resp.status}")
                    else:
                        # MelView doesn't always label its JSON as JSON
                        return await resp.json(content_type=None)
            except ClientError as err:
                raise MelViewError(f"{path} failed: {err}") from err
            await self.async_login()
        raise MelViewAuthError(f"{path} still unauthorised after logging in again")


class MelViewZone:
    """One zone of a ducted unit."""

    def __init__(self, zoneid: int, name: str, status: int) -> None:
        self.id = zoneid
        self.name = name
        self.status = status


class MelViewDevice:
    """One indoor unit."""

    def __init__(
        self,
        session: ClientSession,
        auth: MelViewAuthentication,
        deviceid: str,
        buildingid: str,
        friendlyname: str,
        localcontrol: bool,
    ) -> None:
        self._session = session
        self._auth = auth
        self._deviceid = deviceid
        self._buildingid = buildingid
        self._friendlyname = friendlyname
        self._localcontrol = localcontrol
        self._localip: str | None = None
        self._caps: dict[str, Any] = {}
        self._json: dict[str, Any] = {}
        self._zones: dict[int, MelViewZone] = {}
        self.fan: dict[int, str] = dict(FANSTAGES[3])

    # -- refreshing ---------------------------------------------------------

    async def async_refresh_caps(self) -> None:
        """Fetch what the unit supports. Only needed once."""
        self._caps = await self._auth.async_post(
            "unitcapabilities.aspx", {"unitid": self._deviceid, "v": APIVERSION}
        )
        if self._localcontrol:
            self._localip = self._caps.get("localip") or None
        self.fan = dict(FANSTAGES.get(self._caps.get("fanstage") or 3, FANSTAGES[3]))
        if self._caps.get("hasautofan") == 1:
            self.fan[FAN_AUTO] = "Auto"

    async def async_refresh(self) -> None:
        """Fetch the unit's current settings and temperatures."""
        if not self._caps:
            await self.async_refresh_caps()
        data = await self._auth.async_post(
            "unitcommand.aspx", {"unitid": self._deviceid, "v": APIVERSION}
        )
        self._apply(data)

    def _apply(self, data: dict[str, Any]) -> None:
        self._json = data
        self._zones = {
            z["zoneid"]: MelViewZone(z["zoneid"], z["name"], z["status"])
            for z in data.get("zones", [])
        }

    async def async_send_command(self, command: str) -> None:
        """Send a command, through the unit's own adapter too when local."""
        resp = await self._auth.async_post(
            "unitcommand.aspx",
            {"unitid": self._deviceid, "v": APIVERSION, "commands": command, "lc": 1},
        )
        _LOGGER.debug("%s: sent %s", self._friendlyname, command)
        if not self._localip:
            return
        local_command = resp.get("lc") if isinstance(resp, dict) else None
        if not local_command:
            _LOGGER.warning("%s: MelView gave no local command for %s", self._friendlyname, command)
            return
        try:
            async with self._session.post(
                f"http://{self._localip}/smart",
                data=LOCAL_DATA.format(local_command),
                timeout=TIMEOUT,
            ) as local:
                if local.status != 200:
                    _LOGGER.warning(
                        "%s: local adapter answered %s", self._friendlyname, local.status
                    )
        except ClientError as err:
            # MelView has the command already, so the unit still gets it
            _LOGGER.warning("%s: local adapter unreachable: %s", self._friendlyname, err)

    # -- reading (cached only) ----------------------------------------------

    def get_id(self) -> str:
        return self._deviceid

    def get_friendly_name(self) -> str:
        return self._friendlyname

    def get_local_ip(self) -> str | None:
        return self._localip

    def get_precision_halves(self) -> bool:
        return self._caps.get("halfdeg") == 1

    def is_power_on(self) -> bool:
        return bool(self._json.get("power"))

    def get_mode(self) -> HVACMode:
        """The mode the unit is set to, whether or not it is on."""
        setmode = self._json.get("setmode")
        for mode, value in MODE.items():
            if value == setmode:
                return mode
        return HVACMode.AUTO

    def get_supported_modes(self) -> list[HVACMode]:
        if self._caps.get("hascoolonly") == 1:
            return [HVACMode.COOL]
        modes = [HVACMode.HEAT, HVACMode.COOL]
        if self._caps.get("hasdrymode") == 1:
            modes.append(HVACMode.DRY)
        modes.append(HVACMode.FAN_ONLY)
        if self._caps.get("hasautomode") == 1:
            modes.append(HVACMode.AUTO)
        return modes

    def get_temperature(self) -> float | None:
        settemp = self._json.get("settemp")
        return float(settemp) if settemp is not None else None

    def get_room_temperature(self) -> float | None:
        roomtemp = self._json.get("roomtemp")
        return float(roomtemp) if roomtemp is not None else None

    def get_outside_temperature(self) -> float | None:
        if self._caps.get("hasoutdoortemp") != 1:
            return None
        outdoortemp = self._json.get("outdoortemp")
        return float(outdoortemp) if outdoortemp is not None else None

    def get_temperature_range(self, mode: HVACMode) -> tuple[float, float]:
        """The unit's own limits for a mode, else auto's, else 16-31."""
        limits = self._caps.get("max") or {}
        mode_limits = limits.get(str(MODE.get(mode))) or limits.get(str(MODE[HVACMode.AUTO]))
        if mode_limits:
            return float(mode_limits["min"]), float(mode_limits["max"])
        return 16.0, 31.0

    def get_speed(self) -> str | None:
        return self.fan.get(self._json.get("setfan"))

    def get_zone(self, zoneid: int) -> MelViewZone | None:
        return self._zones.get(zoneid)

    def get_zones(self) -> list[MelViewZone]:
        return list(self._zones.values())

    # -- commands -----------------------------------------------------------
    # Each also updates the cache, so the entity shows the change at once
    # rather than after MelView catches up on the next poll.

    async def async_power_on(self) -> None:
        await self.async_send_command("PW1")
        self._json["power"] = 1

    async def async_power_off(self) -> None:
        await self.async_send_command("PW0")
        self._json["power"] = 0

    async def async_set_mode(self, mode: HVACMode) -> None:
        if mode not in self.get_supported_modes():
            raise MelViewError(f"{self._friendlyname} does not support {mode}")
        if not self.is_power_on():
            await self.async_power_on()
        await self.async_send_command(f"MD{MODE[mode]}")
        self._json["setmode"] = MODE[mode]

    async def async_set_temperature(self, temperature: float) -> None:
        low, high = self.get_temperature_range(self.get_mode())
        if not low <= temperature <= high:
            raise MelViewError(
                f"{temperature} is outside {low}-{high} for {self.get_mode()}"
            )
        await self.async_send_command(f"TS{temperature:.2f}")
        self._json["settemp"] = temperature

    async def async_set_speed(self, speed: str) -> None:
        value = next((k for k, v in self.fan.items() if v == speed), None)
        if value is None:
            raise MelViewError(f"{self._friendlyname} has no fan speed {speed}")
        if not self.is_power_on():
            await self.async_power_on()
        await self.async_send_command(f"FS{value:.2f}")
        self._json["setfan"] = value

    async def async_set_zone(self, zoneid: int, on: bool) -> None:
        await self.async_send_command(f"Z{zoneid}{int(on)}")
        if zone := self._zones.get(zoneid):
            zone.status = int(on)


class MelView:
    """All the units on one MelView account."""

    def __init__(
        self, session: ClientSession, auth: MelViewAuthentication, localcontrol: bool
    ) -> None:
        self._session = session
        self._auth = auth
        self._localcontrol = localcontrol

    async def async_get_devices_list(self) -> list[MelViewDevice]:
        reply = await self._auth.async_post("rooms.aspx", {"unitid": 0})
        return [
            MelViewDevice(
                self._session,
                self._auth,
                unit["unitid"],
                building["buildingid"],
                unit["room"],
                self._localcontrol,
            )
            for building in reply
            for unit in building["units"]
        ]
