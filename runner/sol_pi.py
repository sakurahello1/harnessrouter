"""Independent SoL-Pi backend; only the Pi transport is shared with ordinary Pi."""
import json
import math
import os
import re
from pathlib import Path

from fastapi import HTTPException

REVISION = "1559b5cb12c72da4a485bc50fe326586b216fb19"
FEATURES = ("actionFusion", "observationPack", "evidencePreservingReducer", "onlineContextCompact")


def session_present(cwd: str, session_id: str) -> bool:
    """Pi 0.85.1 reads the session header id and cwd, not a filename substring."""
    resolved = os.path.abspath(cwd)
    slug = "--" + re.sub(r"[/\\:]", "-", re.sub(r"^[/\\]", "", resolved)) + "--"
    sessions = Path(cwd) / ".harness/home/.sol-pi/agent/sessions" / slug
    for path in sessions.glob("*.jsonl"):
        try:
            with path.open(encoding="utf-8") as stream:
                header = json.loads(stream.readline())
            if (header.get("type") == "session" and header.get("id") == session_id
                    and header.get("cwd") == resolved):
                return True
        except (OSError, ValueError, AttributeError):
            continue
    return False


def normalize_config(value=None):
    value = {} if value is None else value
    if not isinstance(value, dict):
        raise HTTPException(400, "sol_pi must be an object")
    allowed = {*FEATURES, "cacheWriteReadRatio", "reducerModel"}
    if set(value) - allowed:
        raise HTTPException(400, "Unknown sol_pi fields: " + ", ".join(sorted(set(value) - allowed)))
    config = {key: value.get(key, True) for key in FEATURES}
    if any(type(v) is not bool for v in config.values()):
        raise HTTPException(400, "SoL-Pi feature switches must be boolean")
    ratio = value.get("cacheWriteReadRatio", 12.5)
    if type(ratio) not in (float, int) or not math.isfinite(ratio) or ratio < 0:
        raise HTTPException(400, "cacheWriteReadRatio must be finite and non-negative")
    config["cacheWriteReadRatio"] = ratio
    if "reducerModel" in value:
        model = value["reducerModel"]
        if not isinstance(model, str) or not model.strip():
            raise HTTPException(400, "reducerModel must be a non-empty model id")
        config["reducerModel"] = model.strip()
    return config


def build(build_pi, provider, auth, model, prompt, cwd, env, *, config=None,
          resume_session_id=None, mcp_servers=None, tools_disabled=None, vision=True):
    config = normalize_config(config)
    disabled = {x.split(" (")[0].strip() for x in tools_disabled or []}
    if config["actionFusion"] and disabled.intersection({"bash", "edit", "write"}):
        raise HTTPException(400, "Disable Action Fusion before disabling bash, edit, or write")
    if config["observationPack"] and "obs_recall" in disabled:
        raise HTTPException(400, "ObservationPack requires obs_recall")
    if config["onlineContextCompact"] and "update_plan" in disabled:
        raise HTTPException(400, "Online Context Compact requires update_plan")
    binary = os.environ.get("HR_SOL_PI_BIN", "")
    entry = Path(os.environ.get("HR_SOL_PI_ENTRY", ""))
    if not binary or not Path(binary).is_file() or not entry.is_file():
        raise HTTPException(503, "SoL-Pi is not installed; configure HR_SOL_PI_BIN and HR_SOL_PI_ENTRY")
    agent_dir = Path(env.get("HOME") or cwd) / ".sol-pi" / "agent"
    mcp_extension = os.environ.get("HR_SOL_PI_MCP_EXT", "")
    if mcp_servers and not (mcp_extension and Path(mcp_extension).exists()):
        raise HTTPException(503, "SoL-Pi MCP adapter is not installed; configure HR_SOL_PI_MCP_EXT")
    cmd = build_pi(provider, auth, model, prompt, cwd, env,
                   resume_session_id=resume_session_id, mcp_servers=mcp_servers,
                   tools_disabled=tools_disabled, vision=vision, agent_dir=agent_dir,
                   mcp_extension=mcp_extension)
    cmd[0] = binary
    route = cmd[cmd.index("--provider") + 1]
    reducer_model = config.pop("reducerModel", model)
    effective = {"version": 1, **config, "evidencePreservingReducerProvider": route,
                 "evidencePreservingReducerModel": reducer_model}
    if route == "hr" and config["evidencePreservingReducer"] and reducer_model != model:
        path = agent_dir / "models.json"
        models = json.loads(path.read_text(encoding="utf-8"))
        main = models["providers"]["hr"]["models"][0]
        models["providers"]["hr"]["models"].append({**main, "id": reducer_model, "name": reducer_model})
        path.write_text(json.dumps(models), encoding="utf-8")
    managed = Path(cwd) / ".harness" / "sol-pi"
    managed.mkdir(parents=True, exist_ok=True)
    # Inject configuration via the upstream registration API: a task-created project config
    # cannot override the harness switches. The wrapper is rewritten before every invocation.
    wrapper = managed / "extension.ts"
    wrapper.write_text(
        "import { registerConfiguredFeatures } from " + json.dumps(entry.resolve().as_posix()) + ";\n"
        "const config = " + json.dumps(effective) + ";\n"
        "export default function(pi) {\n"
        "  const observed = Object.create(pi);\n"
        "  observed.appendEntry = (type, data) => {\n"
        "    pi.appendEntry(type, data);\n"
        "    if (type === 'sol-pi-evidence-preserving-reducer-v1') {\n"
        "      const event = { type: 'sol_pi_event', kind: data.kind, reason: data.reason };\n"
        "      if (data.kind === 'provider_response') Object.assign(event, {usage: data.usage, model: data.model, provider: data.provider});\n"
        "      process.stdout.write(JSON.stringify(event) + '\\n');\n"
        "    }\n"
        "  };\n"
        "  let initialized = false;\n"
        "  pi.on('session_start', () => {\n"
        "    if (initialized) return; initialized = true;\n"
        "    registerConfiguredFeatures(observed, config);\n"
        "    process.stdout.write(JSON.stringify({type: 'sol_pi_ready', config, revision: " + json.dumps(REVISION) + "}) + '\\n');\n"
        "  });\n"
        "}\n",
        encoding="utf-8")
    (managed / "effective-config.json").write_text(json.dumps(effective, indent=2), encoding="utf-8")
    cmd[-1:-1] = ["--extension", str(wrapper)]
    return cmd
