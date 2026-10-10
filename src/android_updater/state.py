"""Small JSON state: what the phone had last time we saw it, and what a digest already reported."""
import json
from dataclasses import dataclass, field

from .paths import STATE_DIR, STATE_FILE


@dataclass
class State:
    installed: dict[str, int] = field(default_factory=dict)  # package -> versionCode on phone
    notified: dict[str, int] = field(default_factory=dict)   # package -> versionCode last put in a digest

    @classmethod
    def load(cls) -> "State":
        try:
            raw = json.loads(STATE_FILE.read_text())
        except (OSError, ValueError):
            return cls()
        return cls(raw.get("installed", {}), raw.get("notified", {}))

    def save(self) -> None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps({"installed": self.installed, "notified": self.notified}, indent=2))
        tmp.replace(STATE_FILE)
