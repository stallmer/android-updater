"""Config file: F-Droid packages plus apps from direct sources. Hand-editable TOML."""
import json
import tomllib
from dataclasses import dataclass, field

from .direct import DirectApp
from .paths import CONFIG_DIR, WATCHLIST_FILE


@dataclass
class Config:
    packages: list[str] = field(default_factory=list)  # F-Droid
    direct: list[DirectApp] = field(default_factory=list)

    def all_packages(self) -> list[str]:
        return self.packages + [a.package for a in self.direct]


def load() -> Config:
    if not WATCHLIST_FILE.exists():
        return Config()
    with WATCHLIST_FILE.open("rb") as f:
        raw = tomllib.load(f)
    return Config(list(raw.get("packages", [])),
                  [DirectApp(a["package"], a["version_url"], a["apk_url"]) for a in raw.get("app", [])])


def save(cfg: Config) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    body = ",\n".join(f"  {json.dumps(p)}" for p in sorted(set(cfg.packages)))
    out = f"packages = [\n{body}\n]\n" if body else "packages = []\n"
    for a in cfg.direct:
        out += (f"\n[[app]]\npackage = {json.dumps(a.package)}\n"
                f"version_url = {json.dumps(a.version_url)}\napk_url = {json.dumps(a.apk_url)}\n")
    WATCHLIST_FILE.write_text(out)
