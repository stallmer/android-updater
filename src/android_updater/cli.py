import argparse
import sys

from . import adb, repo, updater, watchlist
from .direct import DirectApp


def cmd_add(args):
    cfg = watchlist.load()
    index = repo.load_index()
    for p in args.packages:
        if p not in index["packages"]:
            print(f"warning: {p} not found in F-Droid index", file=sys.stderr)
        elif p not in cfg.packages:
            cfg.packages.append(p)
            print(f"added {p}")
    watchlist.save(cfg)


def cmd_add_direct(args):
    cfg = watchlist.load()
    cfg.direct = [a for a in cfg.direct if a.package != args.package]
    cfg.direct.append(DirectApp(args.package, args.version_url, args.apk_url))
    watchlist.save(cfg)
    print(f"added {args.package} (direct)")


def cmd_remove(args):
    cfg = watchlist.load()
    cfg.packages = [p for p in cfg.packages if p not in args.packages]
    cfg.direct = [a for a in cfg.direct if a.package not in args.packages]
    watchlist.save(cfg)


def cmd_list(_args):
    for p in sorted(watchlist.load().all_packages()):
        print(p)


def _plan():
    serial = adb.connected_device()
    sdk, abis = adb.device_info(serial)
    cands = updater.find_updates(repo.load_index(), watchlist.load(),
                                 adb.installed_versions(serial), sdk, abis)
    return serial, cands


def _show(cands):
    for c in cands:
        r = c.release
        print(f"  {r.package}: {c.installed_code} -> {r.version_name} ({r.version_code})")


def cmd_check(_args):
    """Compare the watchlist against F-Droid only (no phone needed)."""
    cfg = watchlist.load()
    found = {r.package: r for r in updater.latest_releases(
        repo.load_index(), cfg, sdk=99, abis=["arm64-v8a", "armeabi-v7a", "x86_64", "x86"])}
    for p in cfg.all_packages():
        rel = found.get(p)
        print(f"{p}: latest {rel.version_name} ({rel.version_code})" if rel else f"{p}: not found")


def cmd_update(args):
    serial, cands = _plan()
    if not cands:
        print("everything is up to date")
        return
    print(f"{len(cands)} update(s) available:")
    _show(cands)
    if args.dry_run:
        return
    failed = 0
    for pkg, err in updater.apply(serial, cands).items():
        print(f"  {'ok  ' if err is None else 'FAIL'} {pkg}" + (f": {err}" if err else ""))
        failed += err is not None
    sys.exit(1 if failed else 0)


def main():
    ap = argparse.ArgumentParser(prog="android-updater", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn, help_ in [("add", cmd_add, "add apps to the watchlist"),
                            ("remove", cmd_remove, "remove apps from the watchlist")]:
        s = sub.add_parser(name, help=help_)
        s.add_argument("packages", nargs="+", metavar="PACKAGE")
        s.set_defaults(fn=fn)
    d = sub.add_parser("add-direct", help="add an app published outside F-Droid")
    d.add_argument("package")
    d.add_argument("--version-url", required=True, help="URL returning the latest versionCode as text")
    d.add_argument("--apk-url", required=True, help="APK URL; {abi} is replaced by the phone's ABI")
    d.set_defaults(fn=cmd_add_direct)
    sub.add_parser("list", help="show the watchlist").set_defaults(fn=cmd_list)
    sub.add_parser("check", help="show latest F-Droid versions of watched apps").set_defaults(fn=cmd_check)
    u = sub.add_parser("update", help="update watched apps installed on the connected phone")
    u.add_argument("--dry-run", action="store_true", help="only show what would be updated")
    u.set_defaults(fn=cmd_update)

    args = ap.parse_args()
    try:
        args.fn(args)
    except (adb.AdbError, OSError, RuntimeError) as e:
        sys.exit(f"error: {e}")
