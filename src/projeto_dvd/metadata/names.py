"""Folder and file names that Windows accepts. Pure."""

import re
from pathlib import Path

from projeto_dvd.library.files import nfc

MAX_NAME = 80  # keeps OUTPUT_DIR\covers\<disc>\<title>\poster.jpg under MAX_PATH (260)
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}  # fmt: skip


def safe_name(text: str, default: str = "Sem nome") -> str:
    name = nfc(text).replace(": ", " - ")
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", name)
    name = re.sub(r"\s+", " ", name).strip()[:MAX_NAME].rstrip(" .")
    if not name or name.split(".")[0].upper() in _RESERVED:
        return default
    return name


def art_dir(output_dir: Path, folder: str, name: str) -> Path:
    """OUTPUT_DIR/covers/<disc folder>/<title>; ValueError if it would land outside covers."""
    covers = (output_dir / "covers").resolve()
    path = (covers / safe_name(folder) / safe_name(name)).resolve()
    if not path.is_relative_to(covers) or path.parent.parent != covers:
        raise ValueError(f"art folder outside covers: {path}")
    return output_dir / "covers" / safe_name(folder) / safe_name(name)
