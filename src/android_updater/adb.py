"""Thin wrapper around the adb binary."""
import shutil
import subprocess


class AdbError(RuntimeError):
    pass


def _run(args: list[str], serial: str | None = None) -> str:
    if not shutil.which("adb"):
        raise AdbError("adb not found; install android-tools / android-platform-tools")
    cmd = ["adb", *(["-s", serial] if serial else []), *args]
    p = subprocess.run(cmd, capture_output=True, text=True)
    out = (p.stdout + p.stderr).strip()
    if p.returncode != 0:
        raise AdbError(out or f"{' '.join(cmd)} failed")
    return out


def connected_device() -> str:
    """Serial of the single authorized device, or raise with a helpful message."""
    lines = _run(["devices"]).splitlines()[1:]
    states = [l.split("\t") for l in lines if "\t" in l]
    ready = [s for s, st in states if st == "device"]
    if any(st == "unauthorized" for _, st in states) and not ready:
        raise AdbError("device is unauthorized: accept the USB debugging prompt on the phone")
    if not ready:
        raise AdbError("no device found: enable USB debugging and plug in the phone")
    if len(ready) > 1:
        raise AdbError(f"multiple devices connected: {', '.join(ready)}")
    return ready[0]


def device_info(serial: str) -> tuple[int, list[str]]:
    sdk = int(_run(["shell", "getprop", "ro.build.version.sdk"], serial))
    abis = _run(["shell", "getprop", "ro.product.cpu.abilist"], serial).split(",")
    return sdk, [a for a in abis if a]


def installed_versions(serial: str) -> dict[str, int]:
    """package -> versionCode for everything installed."""
    out = _run(["shell", "pm", "list", "packages", "--show-versioncode"], serial)
    result = {}
    for line in out.splitlines():
        parts = dict(p.split(":", 1) for p in line.split() if ":" in p)
        if "package" in parts and "versionCode" in parts:
            result[parts["package"]] = int(parts["versionCode"])
    return result


def install(serial: str, apk) -> None:
    """Upgrade in place (-r). Raises AdbError with adb's failure text."""
    out = _run(["install", "-r", str(apk)], serial)
    if "Success" not in out:
        raise AdbError(out)
