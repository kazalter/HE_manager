"""Discovery of Windows game launchers without executing them."""

from pathlib import Path


_UTILITY_NAMES = {
    "unitycrashhandler32.exe", "unitycrashhandler64.exe", "unins000.exe",
    "uninstall.exe", "uninstaller.exe", "resetconfig.exe", "opensavefolder.exe",
}


def game_launchers(root: str) -> list[str]:
    """Return direct, regular executable filenames; never follow symlinks."""
    try:
        entries = Path(root).iterdir()
        return sorted(
            (p.name for p in entries if p.suffix.lower() == ".exe"
             and p.name.lower() not in _UTILITY_NAMES
             and not p.is_symlink() and p.is_file()),
            key=str.casefold,
        )
    except OSError:
        return []


def suggested_launcher(names: list[str]) -> str | None:
    """Suggest common launchers; leave an ambiguous choice to the user."""
    if len(names) == 1:
        return names[0]
    for preferred in ("startup.exe", "game.exe"):
        matches = [name for name in names if name.casefold() == preferred]
        if len(matches) == 1:
            return matches[0]
    return None
