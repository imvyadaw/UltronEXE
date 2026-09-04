"""Hardware Extra Control tool registry
=======================================
Wires system_control/hardware/{fan_control,gpu_control,speaker_control,
microphone_control}.py into the AI tool-calling loop. These 4 modules
existed with working implementations but had no tool schema entry and
no dispatch handler, so the model could never actually call them.
Same pattern as ai/monitoring_control_tools.py: lazy singletons + a
flat HARDWARE_EXTRA_TOOLS / HARDWARE_EXTRA_DIRECT_HANDLERS pair, merged
at the bottom of ai/tools_schema.py and ai/tool_runtime.py respectively.

Naming: every tool is prefixed `hwx_` (hardware-extra) to avoid
colliding with any existing hardware-adjacent tool set.

Confirm-gating: enforcement lives at each underlying method's own
`confirm: bool = False` parameter (set_cooling_policy,
set_app_graphics_preference, set_speaker_enabled, set_mic_enabled) -
same convention as every other _DIRECT_HANDLERS-routed module. Calling
without confirm=True returns a `requires_confirmation` preview instead
of acting.
"""

from typing import Dict


def _tool(name: str, description: str, properties: dict = None, required: list = None) -> dict:
    """Identical shape to ai/tools_schema.py's `_tool()` helper. Duplicated
    on purpose - see ai/network_control_tools.py's docstring for why (avoids
    a circular import since tools_schema.py imports *from* this module)."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
        },
    }


def _pick(d: dict, keys: list) -> dict:
    """Filter a raw tool-call args dict down to the keys a method accepts,
    dropping missing/None entries so the method's own defaults apply."""
    return {k: d[k] for k in keys if k in d and d[k] is not None}


# ---------------------------------------------------------------------------
# Lazy singletons
# ---------------------------------------------------------------------------
_instances: Dict[str, object] = {}


def _get(key: str):
    if key in _instances:
        return _instances[key]

    if key == "fan":
        from system_control.hardware.fan_control import FanControl

        obj = FanControl()
    elif key == "gpu":
        from system_control.hardware.gpu_control import GPUControl

        obj = GPUControl()
    elif key == "speaker":
        from system_control.hardware.speaker_control import SpeakerControl

        obj = SpeakerControl()
    elif key == "microphone":
        from system_control.hardware.microphone_control import MicrophoneControl

        obj = MicrophoneControl()
    else:
        raise KeyError(f"Unknown hardware_extra tool key: {key}")

    _instances[key] = obj
    return obj


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------
HARDWARE_EXTRA_TOOLS = [
    # -- FanControl --
    _tool(
        "hwx_fan_get_thermal_zones",
        "Read generic ACPI thermal-zone temperatures where the firmware exposes them. No admin needed.",
    ),
    _tool(
        "hwx_fan_get_cooling_policy",
        "Get the current system cooling policy (active vs passive) for the active power scheme.",
    ),
    _tool(
        "hwx_fan_set_cooling_policy",
        "Set the system cooling policy to 'active' (fan-first, cooler/louder) or 'passive' "
        "(throttle-first, quieter). Confirm-gated, needs admin.",
        {
            "policy": {"type": "string", "enum": ["active", "passive"]},
            "on_battery": {"type": "boolean"},
            "confirm": {"type": "boolean"},
        },
        ["policy"],
    ),
    _tool(
        "hwx_fan_get_rpm",
        "Attempt to read direct fan RPM. Always reports unsupported - no vendor-neutral Windows API exists for this.",
    ),
    _tool(
        "hwx_fan_set_speed",
        "Attempt to set direct fan speed/duty-cycle. Always reports unsupported - "
        "use hwx_fan_set_cooling_policy instead.",
        {"percent": {"type": "integer"}, "confirm": {"type": "boolean"}},
        ["percent"],
    ),
    # -- GPUControl --
    _tool(
        "hwx_gpu_get_info",
        "Get vendor-neutral GPU identity/driver info for every adapter (NVIDIA/AMD/Intel/integrated).",
    ),
    _tool(
        "hwx_gpu_get_nvidia_status",
        "Get live GPU utilization, temperature, VRAM usage, and power draw via nvidia-smi. NVIDIA-only.",
    ),
    _tool(
        "hwx_gpu_list_processes",
        "List processes currently using the GPU and their VRAM usage. NVIDIA-only, via nvidia-smi.",
    ),
    _tool(
        "hwx_gpu_get_app_graphics_preference",
        "Get which GPU (let_windows_decide / power_saving / high_performance) an app is set to launch on.",
        {"exe_path": {"type": "string"}},
        ["exe_path"],
    ),
    _tool(
        "hwx_gpu_set_app_graphics_preference",
        "Set which GPU a specific app (by full exe path) launches on. Confirm-gated.",
        {
            "exe_path": {"type": "string"},
            "preference": {"type": "string", "enum": ["let_windows_decide", "power_saving", "high_performance"]},
            "confirm": {"type": "boolean"},
        },
        ["exe_path", "preference"],
    ),
    # -- SpeakerControl --
    _tool(
        "hwx_speaker_list",
        "List all currently-known playback (render) devices: id, name, and default status.",
    ),
    _tool(
        "hwx_speaker_get_volume",
        "Get current volume (0-100) for a specific output device, or the default if omitted.",
        {"device_id": {"type": "string"}},
    ),
    _tool(
        "hwx_speaker_set_volume",
        "Set volume (0-100) for a specific output device, or the default if omitted. Not confirm-gated.",
        {"level": {"type": "integer"}, "device_id": {"type": "string"}},
        ["level"],
    ),
    _tool(
        "hwx_speaker_get_mute",
        "Get mute state for a specific output device, or the default if omitted.",
        {"device_id": {"type": "string"}},
    ),
    _tool(
        "hwx_speaker_set_mute",
        "Mute/unmute a specific output device, or the default if omitted. Not confirm-gated.",
        {"muted": {"type": "boolean"}, "device_id": {"type": "string"}},
        ["muted"],
    ),
    _tool(
        "hwx_speaker_play_test_tone",
        "Play a short beep on the current default output device.",
    ),
    _tool(
        "hwx_speaker_list_pnp_devices",
        "List the underlying PnP audio-output hardware (for use with hwx_speaker_set_enabled).",
    ),
    _tool(
        "hwx_speaker_set_enabled",
        "Enable or disable an output device's underlying PnP device. Confirm-gated, needs admin - "
        "silences that device for every app until re-enabled.",
        {"instance_id": {"type": "string"}, "enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["instance_id", "enabled"],
    ),
    # -- MicrophoneControl --
    _tool(
        "hwx_mic_list",
        "List all currently-known recording (capture) devices: id, name, and default status.",
    ),
    _tool(
        "hwx_mic_get_mute",
        "Get mute state for a microphone (default, or a specific device_id).",
        {"device_id": {"type": "string"}},
    ),
    _tool(
        "hwx_mic_set_mute",
        "Mute/unmute a microphone (default, or a specific device_id). Not confirm-gated.",
        {"muted": {"type": "boolean"}, "device_id": {"type": "string"}},
        ["muted"],
    ),
    _tool(
        "hwx_mic_get_volume",
        "Get current input volume/gain (0-100) for a microphone.",
        {"device_id": {"type": "string"}},
    ),
    _tool(
        "hwx_mic_set_volume",
        "Set input volume/gain (0-100) for a microphone. Not confirm-gated.",
        {"level": {"type": "integer"}, "device_id": {"type": "string"}},
        ["level"],
    ),
    _tool(
        "hwx_mic_list_pnp_devices",
        "List the underlying PnP audio-input hardware (for use with hwx_mic_set_enabled).",
    ),
    _tool(
        "hwx_mic_set_enabled",
        "Enable or disable a microphone's underlying PnP device. Confirm-gated, needs admin - "
        "cuts off every app's access to that mic until re-enabled.",
        {"instance_id": {"type": "string"}, "enabled": {"type": "boolean"}, "confirm": {"type": "boolean"}},
        ["instance_id", "enabled"],
    ),
    _tool(
        "hwx_mic_get_apps_using",
        "Get which apps currently have the microphone open right now.",
    ),
]

# ---------------------------------------------------------------------------
# Direct handlers
# ---------------------------------------------------------------------------
HARDWARE_EXTRA_DIRECT_HANDLERS = {
    # -- FanControl --
    "hwx_fan_get_thermal_zones": lambda d, _k="fan", _m="get_thermal_zones", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "hwx_fan_get_cooling_policy": lambda d, _k="fan", _m="get_cooling_policy", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "hwx_fan_set_cooling_policy": lambda d, _k="fan", _m="set_cooling_policy", _p=[
        "policy",
        "on_battery",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "hwx_fan_get_rpm": lambda d, _k="fan", _m="get_fan_rpm", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "hwx_fan_set_speed": lambda d, _k="fan", _m="set_fan_speed", _p=["percent", "confirm"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    # -- GPUControl --
    "hwx_gpu_get_info": lambda d, _k="gpu", _m="get_gpu_info", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "hwx_gpu_get_nvidia_status": lambda d, _k="gpu", _m="get_nvidia_status", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "hwx_gpu_list_processes": lambda d, _k="gpu", _m="list_gpu_processes", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "hwx_gpu_get_app_graphics_preference": lambda d, _k="gpu", _m="get_app_graphics_preference", _p=[
        "exe_path"
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "hwx_gpu_set_app_graphics_preference": lambda d, _k="gpu", _m="set_app_graphics_preference", _p=[
        "exe_path",
        "preference",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- SpeakerControl --
    "hwx_speaker_list": lambda d, _k="speaker", _m="list_speakers", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "hwx_speaker_get_volume": lambda d, _k="speaker", _m="get_device_volume", _p=["device_id"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "hwx_speaker_set_volume": lambda d, _k="speaker", _m="set_device_volume", _p=["level", "device_id"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "hwx_speaker_get_mute": lambda d, _k="speaker", _m="get_device_mute", _p=["device_id"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "hwx_speaker_set_mute": lambda d, _k="speaker", _m="set_device_mute", _p=["muted", "device_id"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "hwx_speaker_play_test_tone": lambda d, _k="speaker", _m="play_test_tone", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "hwx_speaker_list_pnp_devices": lambda d, _k="speaker", _m="list_speaker_devices_pnp", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "hwx_speaker_set_enabled": lambda d, _k="speaker", _m="set_speaker_enabled", _p=[
        "instance_id",
        "enabled",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    # -- MicrophoneControl --
    "hwx_mic_list": lambda d, _k="microphone", _m="list_microphones", _p=[]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "hwx_mic_get_mute": lambda d, _k="microphone", _m="get_mic_mute", _p=["device_id"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "hwx_mic_set_mute": lambda d, _k="microphone", _m="set_mic_mute", _p=["muted", "device_id"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "hwx_mic_get_volume": lambda d, _k="microphone", _m="get_mic_volume", _p=["device_id"]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "hwx_mic_set_volume": lambda d, _k="microphone", _m="set_mic_volume", _p=["level", "device_id"]: getattr(
        _get(_k), _m
    )(**_pick(d, _p)),
    "hwx_mic_list_pnp_devices": lambda d, _k="microphone", _m="list_mic_devices_pnp", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
    "hwx_mic_set_enabled": lambda d, _k="microphone", _m="set_mic_enabled", _p=[
        "instance_id",
        "enabled",
        "confirm",
    ]: getattr(_get(_k), _m)(**_pick(d, _p)),
    "hwx_mic_get_apps_using": lambda d, _k="microphone", _m="get_apps_using_microphone", _p=[]: getattr(_get(_k), _m)(
        **_pick(d, _p)
    ),
}
