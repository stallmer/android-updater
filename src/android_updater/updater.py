from dataclasses import dataclass

from . import adb, direct, repo
from .watchlist import Config


@dataclass
class Candidate:
    release: repo.Release
    installed_code: int


def latest_releases(index: dict, cfg: Config, sdk: int, abis: list[str]) -> list[repo.Release]:
    rels = [repo.best_release(index, p, sdk, abis) for p in cfg.packages]
    rels += [direct.latest(a, abis) for a in cfg.direct]
    return [r for r in rels if r]


def find_updates(index: dict, cfg: Config, installed: dict[str, int],
                 sdk: int, abis: list[str]) -> list[Candidate]:
    """Watched apps that are installed on the phone and have a newer release."""
    return [Candidate(r, installed[r.package])
            for r in latest_releases(index, cfg, sdk, abis)
            if r.package in installed and r.version_code > installed[r.package]]


def apply(serial: str, cands: list[Candidate]) -> dict[str, str | None]:
    """Install each update; map package -> None on success or an error message."""
    results = {}
    for c in cands:
        try:
            apk = repo.download(c.release)
            adb.install(serial, apk)
            results[c.release.package] = None
        except Exception as e:  # keep going so one failure doesn't block the rest
            results[c.release.package] = str(e)
    return results
