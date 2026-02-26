"""
PathTransformer - Converts absolute paths to template variables and back

Solves the problem of different absolute paths between devices by using
template variables such as ${PROJECTS}, ${HOME}, ${CLAUDE_DIR}.
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional


class PathTransformer:
    """Converts absolute paths to portable template variables and back"""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the PathTransformer with device path mappings.

        Args:
            config_path: Path to path_mappings.json (optional, uses default if None)
        """
        if config_path is None:
            # Use default config in the project directory
            project_root = Path(__file__).parent.parent
            config_path = project_root / "config" / "path_mappings.json"

        self.config_path = Path(config_path)
        self.mappings = self._load_mappings()
        self.current_device = self.mappings.get("currentDevice", "desktop")

    def _load_mappings(self) -> Dict:
        """Load path mappings from config file, or return defaults if not found."""
        if not self.config_path.exists():
            # Return default configuration
            return {
                "devices": {
                    "desktop": {
                        "USER": os.environ.get("USERNAME", "user"),
                        "HOME": str(Path.home()),
                        "PROJECTS": str(Path.home() / "Documents" / "projetos"),
                        "CLAUDE_DIR": str(Path.home() / ".claude")
                    }
                },
                "currentDevice": "desktop"
            }

        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_mappings(self):
        """Save current mappings to the config file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.mappings, f, indent=2)

    def normalize(self, absolute_path: str, source_device: Optional[str] = None) -> str:
        """
        Convert an absolute path to a template variable path.

        Args:
            absolute_path: Absolute path (e.g. C:\\Users\\alice\\Documents\\projects\\my-app)
            source_device: Source device ID (uses currentDevice if None)

        Returns:
            Template path (e.g. ${PROJECTS}/my-app)

        Examples:
            >>> transformer.normalize("C:\\Users\\alice\\Documents\\projects\\my-app")
            "${PROJECTS}/my-app"
            >>> transformer.normalize("C:\\Users\\alice\\.claude")
            "${CLAUDE_DIR}"
        """
        if not absolute_path:
            return absolute_path

        device_id = source_device or self.current_device

        if device_id not in self.mappings["devices"]:
            raise ValueError(f"Device '{device_id}' not found in configuration")

        mapping = self.mappings["devices"][device_id]

        # Normalize slashes to Unix style
        path = absolute_path.replace("\\", "/")

        # Try substituting variables in order of specificity
        # (most specific first to avoid partial replacements)
        sorted_vars = sorted(
            mapping.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )

        for var, value in sorted_vars:
            value_normalized = value.replace("\\", "/")
            if path.startswith(value_normalized):
                relative = path[len(value_normalized):].lstrip("/")
                if relative:
                    return f"${{{var}}}/{relative}"
                else:
                    return f"${{{var}}}"

        # No match found — return original path
        return absolute_path

    def denormalize(self, template_path: str, target_device: Optional[str] = None) -> str:
        """
        Convert a template variable path to an absolute local path.

        Args:
            template_path: Template path (e.g. ${PROJECTS}/my-app)
            target_device: Target device ID (uses currentDevice if None)

        Returns:
            Absolute path on the target device (e.g. D:\\Projects\\my-app)

        Examples:
            >>> transformer.denormalize("${PROJECTS}/my-app", "laptop")
            "D:\\Projects\\my-app"
        """
        if not template_path:
            return template_path

        device_id = target_device or self.current_device

        if device_id not in self.mappings["devices"]:
            raise ValueError(f"Device '{device_id}' not found in configuration")

        mapping = self.mappings["devices"][device_id]
        result = template_path

        # Replace all template variables
        for var, value in mapping.items():
            result = result.replace(f"${{{var}}}", value)

        # Convert to OS path separators
        result = result.replace("/", "\\")

        return result

    def add_device(self, device_id: str, user: str, home: str,
                   projects: str, claude_dir: Optional[str] = None):
        """
        Add a new device to the configuration.

        Args:
            device_id: Unique device identifier
            user: OS username
            home: User's home directory
            projects: Projects directory
            claude_dir: .claude directory (optional, derived from home if None)
        """
        if claude_dir is None:
            claude_dir = str(Path(home) / ".claude")

        self.mappings["devices"][device_id] = {
            "USER": user,
            "HOME": home,
            "PROJECTS": projects,
            "CLAUDE_DIR": claude_dir
        }

        self.save_mappings()

    def set_current_device(self, device_id: str):
        """Set the current active device."""
        if device_id not in self.mappings["devices"]:
            raise ValueError(f"Device '{device_id}' not found in configuration")

        self.mappings["currentDevice"] = device_id
        self.current_device = device_id
        self.save_mappings()

    def list_devices(self) -> Dict[str, Dict[str, str]]:
        """Return all configured devices."""
        return self.mappings["devices"]

    def set_default_repo(self, url: str):
        """Save the default Git repository URL to the configuration."""
        self.mappings['defaultRepo'] = url
        self.save_mappings()

    def get_default_repo(self) -> Optional[str]:
        """Return the default Git repository URL, or None if not configured."""
        return self.mappings.get('defaultRepo')

    def validate_mappings(self) -> tuple[bool, list[str]]:
        """
        Validate the path mappings configuration.

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        if "devices" not in self.mappings:
            errors.append("Missing 'devices' key in configuration")
            return False, errors

        if not self.mappings["devices"]:
            errors.append("No devices configured")

        for device_id, mapping in self.mappings["devices"].items():
            required_keys = ["USER", "HOME", "PROJECTS", "CLAUDE_DIR"]
            for key in required_keys:
                if key not in mapping:
                    errors.append(f"Device '{device_id}' missing required key: {key}")

        current = self.mappings.get("currentDevice")
        if current and current not in self.mappings["devices"]:
            errors.append(f"Current device '{current}' not found in devices")

        return len(errors) == 0, errors