"""Apps published outside F-Droid: a URL holding the latest version code and an APK URL template, or GitHub releases."""
import json
import re
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


@dataclass
class GithubApp:
    package: str
    repo: str          # "owner/name"
    asset: str         # regex matched against release asset file names
    code_pattern: str  # regex run on the tag; group 1 is the versionCode


def latest_github(app: GithubApp) -> Release:
    rel = json.loads(_get(f"https://api.github.com/repos/{app.repo}/releases/latest"))
    tag = rel["tag_name"]
    m = re.search(app.code_pattern, tag)
    if not m:
        raise RuntimeError(f"{app.repo}: tag {tag!r} does not match {app.code_pattern!r}")
    code = int(m.group(1))
    assets = [a for a in rel["assets"] if re.search(app.asset, a["name"])]
    if len(assets) != 1:
        raise RuntimeError(f"{app.repo} {tag}: {len(assets)} assets match {app.asset!r}, expected 1")
    return Release(app.package, tag, code, assets[0]["browser_download_url"], f"{app.package}_{code}.apk")
