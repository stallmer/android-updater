"""Apps published outside F-Droid: a URL holding the latest version code, and an APK URL template."""
from dataclasses import dataclass

from .repo import Release, _get

KNOWN_ABIS = {"arm64-v8a", "armeabi-v7a", "x86_64", "x86"}


@dataclass
class DirectApp:
    package: str
    version_url: str  # plain text containing the integer versionCode
    apk_url: str      # may contain {abi}


def latest(app: DirectApp, abis: list[str]) -> Release:
    code = int(_get(app.version_url).decode().strip())
    abi = next((a for a in abis if a in KNOWN_ABIS), "universal")
    url = app.apk_url.format(abi=abi)
    return Release(app.package, str(code), code, url, f"{app.package}_{code}_{abi}.apk")
