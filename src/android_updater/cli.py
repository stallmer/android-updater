import argparse
import plistlib
import re
import sys
from pathlib import Path

from . import adb, digest, repo, updater, watchlist
from .direct import DirectApp
from .state import State


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
    cfg = watchlist.load()
    installed = adb.installed_versions(serial)
    state = State.load()  # remember the phone's versions so `digest` works while it's unplugged
    for p in cfg.all_packages():
        if p in installed and p not in state.installed and p in state.notified:
            # first time we see this app on the phone: the digest baseline was a guess, so
            # anything newer than what's really installed counts as not yet reported
            state.notified[p] = min(state.notified[p], installed[p])
    state.installed = {p: installed[p] for p in cfg.all_packages() if p in installed}
    state.save()
    cands = updater.find_updates(repo.load_index(), cfg, installed, sdk, abis)
    return serial, cands, state


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
    serial, cands, state = _plan()
    if not cands:
        print("everything is up to date")
        return
    print(f"{len(cands)} update(s) available:")
    _show(cands)
    if args.dry_run:
        return
    failed = 0
    results = updater.apply(serial, cands)
    for c in cands:
        if results[c.release.package] is None:
            state.installed[c.release.package] = c.release.version_code
    state.save()
    for pkg, err in results.items():
        print(f"  {'ok  ' if err is None else 'FAIL'} {pkg}" + (f": {err}" if err else ""))
        failed += err is not None
    sys.exit(1 if failed else 0)


def cmd_digest(args):
    """Notify about waiting updates. Meant to run from a timer; works with the phone unplugged."""
    state = State.load()
    items = digest.pending(repo.load_index(), watchlist.load(), state)
    if not items or not (args.always or any(i.is_new for i in items)):
        state.save()
        if args.verbose:
            print("nothing new to report")
        return
    title, body = digest.render(items)
    if args.print or not digest.notify(title, body):
        print(f"{title}\n{body}")
    digest.mark_notified(items, state)
    state.save()


def _systemd_timer(schedule: str) -> None:
    units = Path.home() / ".config/systemd/user"
    units.mkdir(parents=True, exist_ok=True)
    exe = Path(sys.argv[0]).resolve()
    (units / "android-updater-digest.service").write_text(
        f"[Unit]\nDescription=Android app update digest\nAfter=network-online.target\n\n"
        f"[Service]\nType=oneshot\nExecStart={exe} digest\n")
    (units / "android-updater-digest.timer").write_text(
        f"[Unit]\nDescription=Check for Android app updates\n\n"
        f"[Timer]\nOnCalendar={schedule}\nPersistent=true\nRandomizedDelaySec=15m\n\n"
        f"[Install]\nWantedBy=timers.target\n")
    print(f"wrote units to {units}\nenable with: systemctl --user enable --now android-updater-digest.timer")


def _launchd_agent(schedule: str) -> None:
    m = re.fullmatch(r"(?:\*-\*-\*\s+)?(\d{1,2}):(\d{2})(?::\d{2})?", schedule.strip())
    if schedule == "daily":
        hour, minute = 9, 0
    elif m and int(m[1]) < 24 and int(m[2]) < 60:
        hour, minute = int(m[1]), int(m[2])
    else:
        raise RuntimeError("on macOS --schedule must be 'daily' or a daily time like '09:00' or '*-*-* 09:00'")
    label = "com.android-updater.digest"
    agents = Path.home() / "Library/LaunchAgents"
    agents.mkdir(parents=True, exist_ok=True)
    plist = agents / f"{label}.plist"
    plist.write_bytes(plistlib.dumps({
        "Label": label,
        "ProgramArguments": [str(Path(sys.argv[0]).resolve()), "digest"],
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "EnvironmentVariables": {"PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"},
    }))
    print(f"wrote {plist}\nenable with: launchctl bootstrap gui/$(id -u) {plist}")


def cmd_install_timer(args):
    (_launchd_agent if sys.platform == "darwin" else _systemd_timer)(args.schedule)


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

    g = sub.add_parser("digest", help="send a desktop notification if updates are waiting")
    g.add_argument("--always", action="store_true", help="notify even if everything was already reported")
    g.add_argument("--print", action="store_true", help="print instead of sending a notification")
    g.add_argument("-v", "--verbose", action="store_true")
    g.set_defaults(fn=cmd_digest)
    t = sub.add_parser("install-timer", help="schedule `digest` (systemd user timer on Linux, launchd agent on macOS)")
    t.add_argument("--schedule", default="daily", help="systemd OnCalendar value, or on macOS a daily time like 09:00 (default: daily)")
    t.set_defaults(fn=cmd_install_timer)

    args = ap.parse_args()
    try:
        args.fn(args)
    except (adb.AdbError, OSError, RuntimeError) as e:
        sys.exit(f"error: {e}")
