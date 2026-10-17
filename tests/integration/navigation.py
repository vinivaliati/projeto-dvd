"""Drive a DVD like a remote control, with libdvdnav (the navigation VLC uses).

Only in the test image (libdvdnav comes with ffmpeg there). This is the VLC virtual machine,
not a physical player: the final test on a player stays manual.
"""

import ctypes
from collections.abc import Callable
from pathlib import Path

Where = tuple[str, int, int]  # domain, title, part
EVENTS = {0: "BLOCK", 1: "NOP", 2: "STILL", 3: "SPU", 4: "AUDIO", 5: "VTS", 6: "CELL",
          7: "NAV", 8: "STOP", 9: "HIGHLIGHT", 10: "CLUT", 12: "HOP", 13: "WAIT"}  # fmt: skip
TITLE_MENU, ROOT_MENU = 2, 3
LIMIT = 300_000


class Nav:
    def __init__(self, disc: Path) -> None:
        self.lib = ctypes.CDLL("libdvdnav.so.4")
        self.lib.dvdnav_get_current_nav_pci.restype = ctypes.c_void_p
        self.lib.dvdnav_get_active_audio_stream.restype = ctypes.c_int8
        self.lib.dvdnav_get_active_spu_stream.restype = ctypes.c_int8
        for domain in ("vmgm", "vtsm", "vts"):
            getattr(self.lib, f"dvdnav_is_domain_{domain}").restype = ctypes.c_int8
        self.handle = ctypes.c_void_p()
        assert self.lib.dvdnav_open(ctypes.byref(self.handle), str(disc).encode()) == 1
        self.buffer = (ctypes.c_uint8 * 4096)()

    def where(self) -> Where:
        title, part = ctypes.c_int32(), ctypes.c_int32()
        self.lib.dvdnav_current_title_info(self.handle, ctypes.byref(title), ctypes.byref(part))
        domain = next(
            (name.upper() for name in ("vmgm", "vtsm", "vts")
             if getattr(self.lib, f"dvdnav_is_domain_{name}")(self.handle)),
            "FP",
        )  # fmt: skip
        return domain, title.value, part.value

    def highlighted(self) -> int:
        button = ctypes.c_int32()
        self.lib.dvdnav_get_current_highlight(self.handle, ctypes.byref(button))
        return button.value

    def streams(self) -> tuple[int, int]:
        """The audio and subpicture streams playing now."""
        audio = self.lib.dvdnav_get_active_audio_stream(self.handle)
        spu = self.lib.dvdnav_get_active_spu_stream(self.handle)
        return int(audio), int(spu)

    def run(self, until: Callable[[str, Where], bool]) -> Where:
        event, length = ctypes.c_int32(), ctypes.c_int32()
        for _ in range(LIMIT):
            ok = self.lib.dvdnav_get_next_block(self.handle, self.buffer, ctypes.byref(event),
                                                ctypes.byref(length))  # fmt: skip
            assert ok == 1, "libdvdnav failed to read the disc"
            name = EVENTS.get(event.value, str(event.value))
            where = self.where()
            if until(name, where) or name == "STOP":
                return where
            if name == "STILL":
                self.lib.dvdnav_still_skip(self.handle)
            elif name == "WAIT":
                self.lib.dvdnav_wait_skip(self.handle)
        raise AssertionError("the disc never reached the expected state")

    def menu_still(self) -> Where:
        """Play until a menu page stops and waits for the remote."""
        return self.run(lambda name, where: name == "STILL" and where[0] in ("VMGM", "VTSM"))

    def playing(self, title: int, packets: int = 3) -> Where:
        """Play until a few navigation packets of a title went by."""
        seen = [0]

        def reached(name: str, where: Where) -> bool:
            if name == "NAV" and where[:2] == ("VTS", title):
                seen[0] += 1
            return seen[0] >= packets

        return self.run(reached)

    def press(self, button: int) -> None:
        pci = self.lib.dvdnav_get_current_nav_pci(self.handle)
        ok = self.lib.dvdnav_button_select_and_activate(self.handle, ctypes.c_void_p(pci), button)
        assert ok == 1, f"button {button} does not exist here"

    def title_key(self) -> None:
        self.lib.dvdnav_menu_call(self.handle, TITLE_MENU)

    def menu_key(self) -> None:
        self.lib.dvdnav_menu_call(self.handle, ROOT_MENU)


def button_groups(menu_vob: Path) -> list[list[tuple[int, int]]]:
    """The y ranges of the buttons of each display group in the first menu PCI."""
    data = menu_vob.read_bytes()
    for start in range(0, len(data), 2048):
        pack = data[start : start + 2048]
        if pack[14:18] != b"\x00\x00\x01\xbb" or pack[38:42] != b"\x00\x00\x01\xbf":
            continue
        if pack[44] != 0:
            continue
        highlight = pack[45:][0x60:]
        mode = int.from_bytes(highlight[14:16], "big")
        groups, buttons = (mode >> 12) & 3, highlight[17]
        table = highlight[22 + 24 :]
        block = 36 // groups if groups else 0  # the 36 slots split evenly between the groups
        result = []
        for group in range(groups):
            ranges = []
            for slot in range(group * block, group * block + buttons):
                entry = table[slot * 18 : (slot + 1) * 18]
                y0 = ((entry[3] & 0x3F) << 4) | (entry[4] >> 4)
                y1 = ((entry[4] & 3) << 8) | entry[5]
                ranges.append((y0, y1))
            result.append(ranges)
        return result
    raise AssertionError("no menu navigation packet")
