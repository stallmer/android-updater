"""Fetch and query the F-Droid index (index-v2)."""
import hashlib
import json
import urllib.request
from dataclasses import dataclass

from .paths import APK_DIR, CACHE_DIR, INDEX_FILE

REPO_URL = "https://f-droid.org/repo"
TIMEOUT = 60
USER_AGENT = "android-updater/0.1"


def _open(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(req, timeout=TIMEOUT)


@dataclass
class Release:
    package: str
    version_name: str
    version_code: int
    url: str
    filename: str
    sha256: str | None = None  # direct sources publish no hash

    @property
    def apk_name(self) -> str:
        return self.filename


def _get(url: str) -> bytes:
    with _open(url) as r:
        return r.read()


def _sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_index() -> dict:
    """Return the parsed index, re-downloading only if entry.json says it changed."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    expected = json.loads(_get(f"{REPO_URL}/entry.json"))["index"]
    if not INDEX_FILE.exists() or _sha256_file(INDEX_FILE) != expected["sha256"]:
        data = _get(f"{REPO_URL}{expected['name']}")
        if hashlib.sha256(data).hexdigest() != expected["sha256"]:
            raise RuntimeError("index-v2.json hash does not match entry.json")
        INDEX_FILE.write_bytes(data)
    return json.loads(INDEX_FILE.read_text())


def best_release(index: dict, package: str, sdk: int, abis: list[str]) -> Release | None:
    """Highest stable version of `package` that the device can run."""
    pkg = index["packages"].get(package)
    if not pkg:
        return None
    best = None
    for v in pkg["versions"].values():
        m = v["manifest"]
        if v.get("releaseChannels"):  # beta etc.
            continue
        uses = m.get("usesSdk", {})
        if uses.get("minSdkVersion", 0) > sdk or uses.get("maxSdkVersion", 10**6) < sdk:
            continue
        native = m.get("nativecode")
        if native and not set(native) & set(abis):
            continue
        if best is None or m["versionCode"] > best.version_code:
            name = v["file"]["name"]
            best = Release(package, m["versionName"], m["versionCode"],
                           f"{REPO_URL}{name}", name.lstrip("/"), v["file"]["sha256"])
    return best


def download(rel: Release):
    """Download the APK (cached) and verify its SHA-256."""
    APK_DIR.mkdir(parents=True, exist_ok=True)
    path = APK_DIR / rel.filename
    if path.exists() and (rel.sha256 is None or _sha256_file(path) == rel.sha256):
        return path
    tmp = path.with_suffix(".part")
    with _open(rel.url) as r, tmp.open("wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    if rel.sha256 and _sha256_file(tmp) != rel.sha256:
        tmp.unlink()
        raise RuntimeError(f"hash mismatch for {rel.filename}")
    tmp.rename(path)
    return path
