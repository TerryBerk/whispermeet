"""Configuration models."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml


class AutoStartMode(Enum):
    """Auto-start behavior for monitored apps."""

    AUTO = "true"
    PROMPT = "prompt"
    DISABLED = "false"


@dataclass
class MonitoredApp:
    """Configuration for a monitored application."""

    name: str
    bundle_id: str
    window_patterns: list[str]
    auto_start: AutoStartMode = AutoStartMode.PROMPT


@dataclass
class AppConfig:
    """Application configuration."""

    apps: list[MonitoredApp] = field(default_factory=list)
    transcripts_dir: Path = field(
        default_factory=lambda: Path.home() / "Transcripts"
    )

    @classmethod
    def default(cls) -> "AppConfig":
        """Create default configuration."""
        return cls(
            apps=[
                MonitoredApp(
                    name="Zoom",
                    bundle_id="us.zoom.xos",
                    window_patterns=["Zoom Meeting", "Zoom Webinar"],
                ),
                MonitoredApp(
                    name="Telegram",
                    bundle_id="ru.keepcoder.Telegram",
                    window_patterns=["Voice Chat", "Video Chat"],
                ),
                MonitoredApp(
                    name="Telemost (Arc)",
                    bundle_id="company.thebrowser.Browser",
                    window_patterns=["Telemost", "telemost.yandex"],
                ),
            ]
        )

    @classmethod
    def load(cls, path: Path) -> "AppConfig":
        """Load configuration from YAML file."""
        if not path.exists():
            return cls.default()

        with open(path) as f:
            data = yaml.safe_load(f)

        apps = [
            MonitoredApp(
                name=app["name"],
                bundle_id=app["bundle_id"],
                window_patterns=app["window_patterns"],
                auto_start=AutoStartMode(app.get("auto_start", "prompt")),
            )
            for app in data.get("apps", [])
        ]

        return cls(apps=apps)
