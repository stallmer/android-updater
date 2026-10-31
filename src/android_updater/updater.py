from dataclasses import dataclass

from . import adb, direct, repo
from .watchlist import Config


@dataclass
class Candidate:
    release: repo.Release
    installed_code: int | None  # None: not installed yet


def latest_releases(index: dict, cfg: Config, sdk: int, abis: list[str]) -> list[repo.Release]:
    rels = [repo.best_release(index, p, sdk, abis) for p in cfg.packages]
    rels += [direct.latest(a, abis) for a in cfg.direct]
    rels += [direct.latest_github(a) for a in cfg.github]
    return [r for r in rels if r]


def tag_tracked(cfg: Config) -> set[str]:
    """Packages whose updates come only from their GitHub release tag, not from versionCodes."""
    return {a.package for a in cfg.github if a.track_tag}


def find_updates(index: dict, cfg: Config, installed: dict[str, int], tags: dict[str, str],
                 sdk: int, abis: list[str]) -> list[Candidate]:
    """Watched apps that are missing from the phone or have a newer release than installed.

    Tag-tracked apps are outdated whenever the latest tag differs from the one we installed.
    """
    tracked = tag_tracked(cfg)
    return [Candidate(r, installed.get(r.package))
            for r in latest_releases(index, cfg, sdk, abis)
            if r.package not in installed
            or (r.version_name != tags.get(r.package) if r.package in tracked
                else r.version_code > installed[r.package])]


def apply(serial: str, cands: list[Candidate]) -> dict[str, str | None]:
    """Install each candidate; map package -> None on success or an error message."""
    results = {}
    for c in cands:
        try:
            apk = repo.download(c.release)
            adb.install(serial, apk)
            results[c.release.package] = None
        except Exception as e:  # keep going so one failure doesn't block the rest
            results[c.release.package] = str(e)
    return results


def record(state, cands: list[Candidate], results: dict[str, str | None]) -> None:
    """Note the version of each successfully installed candidate in `state` and save it."""
    for c in cands:
        if results[c.release.package] is None:
            state.installed[c.release.package] = c.release.version_code
            state.tags[c.release.package] = c.release.version_name
    state.save()
