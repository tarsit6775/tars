"""
╔══════════════════════════════════════════════════════════╗
║      TARS — Home Automation (Home Assistant)             ║
╠══════════════════════════════════════════════════════════╣
║  Control smart home devices via Home Assistant REST API. ║
║  Supports: lights, switches, scenes, climate, sensors.  ║
╚══════════════════════════════════════════════════════════╝
"""

import json
import logging
import urllib.request

logger = logging.getLogger("tars.home")


class HomeAutomation:
    """Home Assistant integration for TARS."""

    def __init__(self, config):
        ha_cfg = config.get("home_automation", {})
        self.enabled = ha_cfg.get("enabled", False)
        self.base_url = ha_cfg.get("homeassistant_url", "").rstrip("/")
        self.token = ha_cfg.get("homeassistant_token", "")

    def execute(self, action, entity_id=None, data=None):
        """Execute a Home Assistant action.
        
        Returns standard tool result dict.
        """
        if not self.enabled:
            return {"success": False, "error": True, "content": "Home automation disabled. Set home_automation.enabled: true in config.yaml."}

        if not self.base_url or not self.token:
            return {"success": False, "error": True, "content": "Home Assistant not configured. Set homeassistant_url and homeassistant_token in config.yaml."}

        try:
            if action == "list":
                return self._list_devices()
            elif action == "status":
                return self._get_status(entity_id)
            elif action == "turn_on":
                return self._call_service("homeassistant", "turn_on", entity_id, data)
            elif action == "turn_off":
                return self._call_service("homeassistant", "turn_off", entity_id, data)
            elif action == "set":
                return self._set_state(entity_id, data)
            elif action == "scene":
                return self._call_service("scene", "turn_on", entity_id)
            else:
                return {"success": False, "error": True, "content": f"Unknown action: {action}"}
        except Exception as e:
            return {"success": False, "error": True, "content": f"Home automation error: {e}"}

    def _api_request(self, path, method="GET", payload=None):
        """Make a request to the Home Assistant API."""
        url = f"{self.base_url}/api{path}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        data = json.dumps(payload).encode() if payload else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())

    def _list_devices(self):
        """List all devices and their states."""
        states = self._api_request("/states")

        # Group by domain
        devices = {}
        for state in states:
            entity_id = state["entity_id"]
            domain = entity_id.split(".")[0]
            if domain in ("light", "switch", "climate", "cover", "fan", "media_player",
                          "scene", "automation", "sensor", "binary_sensor", "lock"):
                if domain not in devices:
                    devices[domain] = []
                name = state.get("attributes", {}).get("friendly_name", entity_id)
                devices[domain].append(f"  {entity_id}: {name} — {state['state']}")

        lines = ["## Smart Home Devices\n"]
        for domain, items in sorted(devices.items()):
            lines.append(f"### {domain.title()} ({len(items)})")
            lines.extend(items[:20])  # Cap per domain
            if len(items) > 20:
                lines.append(f"  ... and {len(items) - 20} more")
            lines.append("")

        total = sum(len(v) for v in devices.values())
        return {"success": True, "content": "\n".join(lines) + f"\nTotal: {total} devices"}

    def _get_status(self, entity_id):
        """Get status of a specific entity."""
        if not entity_id:
            return {"success": False, "error": True, "content": "entity_id required for status check."}

        state = self._api_request(f"/states/{entity_id}")
        name = state.get("attributes", {}).get("friendly_name", entity_id)
        attrs = state.get("attributes", {})

        info = [f"**{name}** ({entity_id})", f"State: {state['state']}"]
        for key in ("brightness", "color_temp", "temperature", "current_temperature",
                     "humidity", "battery_level", "unit_of_measurement"):
            if key in attrs:
                info.append(f"{key}: {attrs[key]}")

        return {"success": True, "content": "\n".join(info)}

    def _call_service(self, domain, service, entity_id, data=None):
        """Call a Home Assistant service."""
        if not entity_id:
            return {"success": False, "error": True, "content": "entity_id required."}

        payload = {"entity_id": entity_id}
        if data:
            payload.update(data)

        self._api_request(f"/services/{domain}/{service}", method="POST", payload=payload)
        return {"success": True, "content": f"{service.replace('_', ' ').title()} → {entity_id}"}

    def _set_state(self, entity_id, data):
        """Set device attributes (brightness, temperature, etc.)."""
        if not entity_id:
            return {"success": False, "error": True, "content": "entity_id required."}
        if not data:
            return {"success": False, "error": True, "content": "data dict required (e.g., {brightness: 128})."}

        domain = entity_id.split(".")[0]

        # Map to appropriate service
        if domain == "light":
            return self._call_service("light", "turn_on", entity_id, data)
        elif domain == "climate":
            return self._call_service("climate", "set_temperature", entity_id, data)
        elif domain == "cover":
            if "position" in data:
                return self._call_service("cover", "set_cover_position", entity_id, data)
        elif domain == "fan":
            if "speed" in data or "percentage" in data:
                return self._call_service("fan", "set_percentage", entity_id, data)

        # Generic fallback
        return self._call_service(domain, "turn_on", entity_id, data)
