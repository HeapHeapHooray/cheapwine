import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

class Project:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir.resolve()
        self.config_path = self.root_dir / "distillery.json"
        self.prefix_path = self.root_dir / ".cheapwine"

    @classmethod
    def find_project(cls, start_dir: Optional[Path] = None) -> Optional["Project"]:
        """Searches upward from start_dir for distillery.json."""
        current = Path(start_dir or os.getcwd()).resolve()
        for parent in [current] + list(current.parents):
            if (parent / "distillery.json").exists():
                return cls(parent)
        return None

    @classmethod
    def get_or_create_project(cls, start_dir: Optional[Path] = None) -> "Project":
        """Gets existing project or creates a project instance at the current directory."""
        project = cls.find_project(start_dir)
        if project:
            return project
        return cls(Path(start_dir or os.getcwd()))

    def exists(self) -> bool:
        """Checks if distillery.json exists in this project root."""
        return self.config_path.exists()

    def load_config(self) -> Dict[str, Any]:
        """Loads and returns the settings from distillery.json."""
        if not self.exists():
            return self.get_default_config()
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            raise RuntimeError(f"Failed to read distillery.json: {e}")

    def save_config(self, config: Dict[str, Any]):
        """Saves config to distillery.json."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            raise RuntimeError(f"Failed to write distillery.json: {e}")

    def get_default_config(self) -> Dict[str, Any]:
        """Returns the default project settings."""
        return {
            "name": self.root_dir.name,
            "wine_arch": "win64",
            "wine_version": "system",
            "win_version": "win10",
            "runner": "wine",
            "latencyflex": False,
            "winetricks": [],
            "env": {
                "WINEDEBUG": "-all"
            },
            "apps": {}
        }

    def init_project_files(self, wine_arch: str = "win64", win_version: str = "win10", runner: str = "wine", runner_version: str = None, latencyflex: bool = False) -> bool:
        """Initializes distillery.json if not present."""
        if self.exists():
            return False
        
        config = self.get_default_config()
        config["wine_arch"] = wine_arch
        config["win_version"] = win_version
        config["runner"] = runner
        config["latencyflex"] = latencyflex
        if runner_version:
            config["runner_version"] = runner_version
        self.save_config(config)
        return True

    def get_app(self, app_name: str) -> Optional[Dict[str, Any]]:
        """Gets app configuration from distillery.json."""
        config = self.load_config()
        return config.get("apps", {}).get(app_name)

    def add_app(self, app_name: str, exe_path: str, args: list = None, env: dict = None, workdir: str = None, win_version: str = None, wine_arch: str = None, runner: str = None, runner_version: str = None, winetricks: list = None, latencyflex: bool = None) -> Dict[str, Any]:
        """Adds or updates an app in distillery.json."""
        config = self.load_config()
        if "apps" not in config:
            config["apps"] = {}
            
        app_config = {
            "exe": exe_path,
            "args": args or [],
            "env": env or {},
        }
        if workdir:
            app_config["workdir"] = workdir
        if win_version:
            app_config["win_version"] = win_version
        if wine_arch:
            app_config["wine_arch"] = wine_arch
        if runner:
            app_config["runner"] = runner
        if runner_version:
            app_config["runner_version"] = runner_version
        if winetricks:
            app_config["winetricks"] = winetricks
        if latencyflex is not None:
            app_config["latencyflex"] = latencyflex
            
        config["apps"][app_name] = app_config
        self.save_config(config)
        return app_config

    def remove_app(self, app_name: str) -> bool:
        """Removes an app from distillery.json. Returns True if removed, False otherwise."""
        config = self.load_config()
        apps = config.get("apps", {})
        if app_name in apps:
            del apps[app_name]
            config["apps"] = apps
            self.save_config(config)
            return True
        return False
