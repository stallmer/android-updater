# android-updater

A command-line tool that updates third-party Android apps on a USB-connected phone using `adb`. No root and no on-device app store are needed.

You keep a **watchlist** of apps. Plug in your phone and run `update`: the tool installs watched apps that are missing from the phone, and downloads and installs newer releases of the ones already there. A **digest** command, run from a systemd timer, sends a desktop notification when a watched app has a new version, so you know when it is worth plugging in.

## Where apps come from

- **F-Droid** (default): versions and APKs come from the F-Droid repo index, and each APK's SHA-256 is verified before install.
- **Direct sources**: for apps published outside F-Droid (for example Grayjay). You give a URL that returns the latest `versionCode` as plain text and an APK URL template.
- **GitHub releases**: for apps that publish APKs on GitHub (for example FairEmail). You give the repo, a regex that picks one APK from the latest release, and optionally a regex that extracts the `versionCode` from the release tag.

## Requirements

- Linux or macOS, Python 3.11+
- `adb` (Arch: `sudo pacman -S android-tools`; macOS: `brew install android-platform-tools`)
- USB debugging enabled on the phone (Settings → Developer options)
- Desktop notifications (optional; the digest prints to stdout without them): `notify-send` on Linux, built in (`osascript`) on macOS

## Install

```
git clone git@github.com:stallmer/android-updater.git
cd android-updater
python -m venv .venv
.venv/bin/pip install -e .
```

The examples below assume `android-updater` is on your `PATH` (or use `.venv/bin/android-updater`).

## Usage

### Build your watchlist

```
android-updater add org.fdroid.fdroid org.mozilla.fennec_fdroid   # F-Droid package names
android-updater add-direct com.futo.platformplayer \
  --version-url https://releases.grayjay.app/version.txt \
  --apk-url 'https://releases.grayjay.app/app-{abi}-release.apk'
android-updater add-github eu.faircode.email --repo M66B/FairEmail --asset 'github-release\.apk$'
android-updater list
android-updater remove org.fdroid.fdroid
```

Package names are the IDs in the app's F-Droid page URL (`f-droid.org/packages/<package>`). In `--apk-url`, `{abi}` is replaced with the phone's CPU architecture (`arm64-v8a`, etc.), or `universal` if none match.

For `add-github`, the package name must be the app's real `applicationId` (for example from `app/build.gradle`, or `adb shell pm list packages`), because it is matched against the apps installed on the phone. `--asset` must match exactly one APK in the latest release. GitHub releases don't expose the `versionCode`, so it is read from the release tag with `--code-pattern` (group 1; default: the trailing digits, so tag `1.2338` gives 2338).

### Check what's latest (no phone needed)

```
android-updater check
```

### Update the phone

Plug in the phone, accept the USB debugging prompt, then:

```
android-updater update --dry-run   # show what would be updated
android-updater update             # download, verify, and install
```

Apps on the watchlist that are missing from the phone are installed, and installed ones older than the latest release are upgraded. Apps are never downgraded or uninstalled. One failed install does not stop the others, and the exit code is non-zero if any failed.

### Get notified about updates

```
android-updater digest             # notify if something new is waiting
android-updater digest --print     # print instead of notifying
android-updater digest --always    # notify even if already reported

android-updater install-timer      # Linux: write systemd user units (default: daily)
systemctl --user enable --now android-updater-digest.timer

android-updater install-timer      # macOS: write a launchd agent (default: daily at 09:00)
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.android-updater.digest.plist
```

Use `install-timer --schedule "*-*-* 09:00"` for a different time (on Linux, then `systemctl --user daemon-reload`; on macOS only `daily` or a daily `HH:MM` is supported, and you must `launchctl bootout` and `bootstrap` again). The units point at the absolute path of the installed script, so rerun `install-timer` if you move the project or recreate the virtualenv.

How the digest works:

- Each time you run `update` (including `--dry-run`), the tool records which versions your watched apps have on the phone, so it can compare while the phone is unplugged.
- A notification is sent only when at least one app has a release newer than the last digest reported. It lists every pending app and marks the new ones, so a daily timer does not repeat itself.
- Before the tool has seen your phone, an app's first sighting is recorded silently as a baseline and only later releases trigger a notification.

## Files

| Path | Contents |
| --- | --- |
| `~/.config/android-updater/config.toml` | The watchlist (hand-editable) |
| `~/.cache/android-updater/` | Cached F-Droid index and downloaded APKs |
| `~/.local/state/android-updater/state.json` | Last-known phone versions and what digests already reported |
| `~/.config/systemd/user/android-updater-digest.{service,timer}` | Written by `install-timer` on Linux |
| `~/Library/LaunchAgents/com.android-updater.digest.plist` | Written by `install-timer` on macOS |

The standard `XDG_CONFIG_HOME`, `XDG_CACHE_HOME` and `XDG_STATE_HOME` variables are respected (also on macOS, which uses the same `~/.config` etc. defaults).

Config format:

```toml
packages = [
  "org.fdroid.fdroid",
]

[[app]]
package = "com.futo.platformplayer"
version_url = "https://releases.grayjay.app/version.txt"
apk_url = "https://releases.grayjay.app/app-{abi}-release.apk"
```

## Limitations

- **Signing keys must match.** Android refuses to update an app signed with a different key than the installed one. An app you installed from Play or from the developer's site generally cannot be updated with F-Droid's rebuild; the install fails with `INSTALL_FAILED_UPDATE_INCOMPATIBLE`. Use the app's own release channel (a direct or GitHub source) in that case.
- **The F-Droid index is not signature-verified yet.** It is fetched over HTTPS and checked against the hash in `entry.json`, but `entry.jar` is not verified against F-Droid's key.
- **Direct and GitHub sources have no hash check.** Protection comes from HTTPS and Android's signature check. For direct sources the version URL must return the APK's real `versionCode`; for GitHub sources the tag must encode it. The GitHub API is called unauthenticated (60 requests per hour).
- **Stable releases only.** F-Droid beta/release-channel versions are skipped.
- **Work profiles and Secure Folder.** On some phones (notably Samsung) `adb` prints permission errors for secondary users. Only apps in the main profile are seen and updated.
- **One device at a time.** If several are connected, the tool stops and lists them.
- Some phones show an extra on-device confirmation for `adb install`.
