import json
import pathlib
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from server import Auth, BACKENDS, _build_pi, _sol_pi_to_claude, _sol_pi_eof
from sol_pi import FEATURES, build, normalize_config


@pytest.fixture
def installed(tmp_path, monkeypatch):
    binary = tmp_path / "pi"
    entry = tmp_path / "upstream.ts"
    binary.touch()
    entry.write_text("export const createSolPiExtension = () => {};", encoding="utf-8")
    monkeypatch.setenv("HR_SOL_PI_BIN", str(binary))
    monkeypatch.setenv("HR_SOL_PI_ENTRY", str(entry))
    return tmp_path, {"HOME": str(tmp_path / ".harness/home")}


def launch(installed, **kw):
    root, env = installed
    return build(_build_pi, "openai-api", Auth(api_key="test", base_url="http://localhost/v1", api_format="openai"),
                 "main-model", "hello", str(root), env, **kw)


def test_independent_identity_and_storage(installed):
    root, env = installed
    cmd = launch(installed, resume_session_id="session-123")
    assert cmd[0] == str(root / "pi")
    assert BACKENDS["sol-pi"]["normalize"] is not BACKENDS["pi"]["normalize"]
    assert pathlib.Path(env["PI_CODING_AGENT_DIR"]).parts[-2:] == (".sol-pi", "agent")
    assert not (root / ".harness/home/.pi").exists()
    assert cmd[cmd.index("--session-id") + 1] == "session-123"
    cfg = json.loads((root / ".harness/sol-pi/effective-config.json").read_text())
    assert all(cfg[k] for k in FEATURES)
    assert cfg["evidencePreservingReducerProvider"] == "hr"
    assert cfg["evidencePreservingReducerModel"] == "main-model"


@pytest.mark.parametrize("mask", range(16))
def test_all_switch_combinations_reach_upstream_factory(installed, mask):
    flags = {k: bool(mask & (1 << i)) for i, k in enumerate(FEATURES)}
    launch(installed, config=flags)
    wrapper = (installed[0] / ".harness/sol-pi/extension.ts").read_text()
    cfg = json.loads((installed[0] / ".harness/sol-pi/effective-config.json").read_text())
    assert {k: cfg[k] for k in FEATURES} == flags
    assert "registerConfiguredFeatures(observed, config)" in wrapper


def test_reducer_registered_on_same_connection(installed):
    launch(installed, config={"reducerModel": "small-model", "cacheWriteReadRatio": 0})
    models = json.loads((pathlib.Path(installed[1]["PI_CODING_AGENT_DIR"]) / "models.json").read_text())
    assert [m["id"] for m in models["providers"]["hr"]["models"]] == ["main-model", "small-model"]


@pytest.mark.parametrize("tool", ["bash", "write", "edit", "obs_recall", "update_plan"])
def test_switches_cannot_bypass_tool_policy(installed, tool):
    with pytest.raises(HTTPException) as exc:
        launch(installed, tools_disabled=[tool])
    assert exc.value.status_code == 400


def test_missing_runtime_does_not_fall_back_to_pi(monkeypatch, tmp_path):
    monkeypatch.delenv("HR_SOL_PI_BIN", raising=False)
    with pytest.raises(HTTPException) as exc:
        launch((tmp_path, {"HOME": str(tmp_path)}))
    assert exc.value.status_code == 503


@pytest.mark.parametrize("cfg", [{"actionFusion": "false"}, {"x": True}, {"cacheWriteReadRatio": -1},
                                     {"cacheWriteReadRatio": float("inf")}, {"reducerModel": ""}])
def test_invalid_config_rejected(cfg):
    with pytest.raises(HTTPException):
        normalize_config(cfg)


def test_original_pi_loads_no_sol_pi(installed):
    root, env = installed
    cmd = _build_pi("openai", Auth(api_key="test"), "main", "hi", str(root), env)
    assert cmd[0] == "pi" and "--extension" not in cmd
    assert pathlib.Path(env["PI_CODING_AGENT_DIR"]).parts[-2:] == (".pi", "agent")


def test_compaction_continuation_has_one_terminal_event_and_aux_usage():
    state = {"model": "main", "final": "", "_sol_pi_ready": {"revision": "test"}}
    for text in ["first phase", "final answer"]:
        _sol_pi_to_claude({"type": "message_end", "message": {"role": "assistant", "model": "main",
                           "content": [{"type": "text", "text": text}], "usage": {"input": 10, "output": 2}}}, state)
        assert _sol_pi_to_claude({"type": "agent_end"}, state) == []
    _sol_pi_to_claude({"type": "sol_pi_event", "kind": "provider_response", "provider": "hr",
                       "model": "small", "usage": {"input": 100, "output": 5}}, state)
    _sol_pi_to_claude({"type": "sol_pi_event", "kind": "applied", "usage": {"input": 100}}, state)
    result, = _sol_pi_eof(state, 0)
    assert result["result"] == "final answer"
    assert result["usage"]["input_tokens"] == 20
    assert result["sol_pi"]["auxiliary_usage"]["hr/small"]["input"] == 100


def test_premature_exit_is_not_success():
    result, = _sol_pi_eof({"model": "main"}, 0)
    assert result["is_error"]
