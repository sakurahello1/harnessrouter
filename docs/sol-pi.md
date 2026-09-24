# SoL-Pi agent

SoL-Pi is an independent base and runner backend (`sol-pi`). It reuses Pi's provider
transport but has its own pinned runtime, configuration, extension entrypoint and
session/skill directory. Existing `pi` harnesses do not load these mechanisms.

## Installation

For the self-hosted container, include `sol-pi` in `HR_BACKENDS` (included in this
branch's default). On startup the installer places it in
`$TOOLS/sol-pi-runtime`, separately from ordinary Pi. The runtime uses Pi 0.85.1 and
[NVlabs/SoL-Pi commit 1559b5c](https://github.com/NVlabs/SoL-Pi/tree/1559b5cb12c72da4a485bc50fe326586b216fb19).
Both are MIT licensed. The normal Pi installation is not upgraded or replaced.

For a separately managed runner, install the same dependencies and set:

```sh
export HR_SOL_PI_BIN=/opt/sol-pi/bin/pi
export HR_SOL_PI_ENTRY=/opt/sol-pi/lib/node_modules/sol-pi/src/sol-pi/index.ts
export HR_SOL_PI_MCP_EXT=/opt/sol-pi/lib/node_modules/pi-mcp-adapter
```

An unavailable runtime fails with 503; the runner never substitutes ordinary Pi.

## Create and configure

Choose **SoL-Pi** when creating an agent, then use **SoL-Pi mechanisms** in its
settings. Each switch is independent. All four default to enabled on this base;
explicit `false` disables a mechanism. Ordinary Pi has no SoL-Pi settings.

The custom harness API accepts this implementation-specific extension:

```json
{
  "name": "SoL-Pi experiment",
  "base": "sol-pi",
  "default_model": "deepseek-v4.1-flash",
  "sol_pi": {
    "actionFusion": true,
    "observationPack": true,
    "evidencePreservingReducer": true,
    "onlineContextCompact": true,
    "cacheWriteReadRatio": 12.5
  }
}
```

POST `/v1/harnesses` creates it; PUT `/v1/harnesses/{id}` updates it. Reads return
`solPi` alongside `base: "sol-pi"`. Task execution uses the returned harness id
as usual. A built-in `/sol-pi/v1/responses` run uses all four defaults; create a
custom agent to change them. This is a local implementation extension, not a UHP
standard change. The settings take effect on the next process/turn.

| Setting | Effect |
| --- | --- |
| `actionFusion` | Add `then_run` to `write` and `edit` |
| `observationPack` | Archive large observations and expose `obs_recall` |
| `evidencePreservingReducer` | Delegate diagnostic-log extraction with exact evidence verification |
| `onlineContextCompact` | Expose `update_plan` and evaluate native compaction at completed steps |
| `cacheWriteReadRatio` | Finite non-negative ratio for the compaction gate; zero is valid |
| `reducerModel` | Optional model on the same provider/API connection; absent uses the Task model |

Set the cache ratio for the provider actually used; 12.5 is the upstream default,
not a claim about DeepSeek pricing. A custom reducer model must speak the same
API format and be accessible through the same connection. For custom endpoints,
its model metadata currently inherits the main model's registration. No separate
API key or upstream default reducer route is silently introduced.

Action Fusion cannot be enabled while `bash`, `edit` or `write` is disabled.
ObservationPack requires `obs_recall`; context compaction requires `update_plan`.
Contradictory policies fail before the model starts.

## State, traces and accounting

SoL-Pi sessions and skills live under `.harness/home/.sol-pi/agent`. Pi retains
`.harness/home/.pi/agent`. The runner writes a managed wrapper that supplies the
effective configuration through upstream's public registration API, so `.pi/sol-pi.json`
inside a task cannot override agent switches. Effective settings are saved in
`.harness/sol-pi/effective-config.json`. These paths are inside the normal session
checkpoint and excluded from user-produced file cards.

SoL-Pi emits its terminal result only when the process settles, including turns
automatically continued after compaction. Reducer decisions and tagged model usage
are preserved as `system/sol_pi_reducer` trace events. The result and turn record
carry `sol_pi.auxiliary_usage`, separate from main-model usage. **Existing cost
widgets report main-model cost, not total SoL-Pi cost**: analysis must price this
additional usage by reducer model. Native Pi compaction accounting retains the
upstream behavior. Benchmark cost comparisons require auditing both before use.

## Verification

```sh
python -m pytest runner/tests/test_sol_pi.py runner/tests/test_pi_normalize.py -q
python -m pytest gateway/tests/test_sol_pi_backend.py -q
python scripts/sol-pi/smoke.py
```

The smoke test uses a local scripted provider and the installed, unmodified Pi and
SoL-Pi packages. It verifies tool schemas with switches on/off, actual fused file
write and shell execution, output artifacts, conversation resume and model switch.
It also triggers the real reducer, verifies safe fallback on invalid evidence,
and checks that auxiliary-model usage is recorded once.
It does not measure task quality or replace live-provider support-matrix checks.
Use `scripts/support-matrix` for provider/model-specific acceptance before deployment.

For the settings smoke check, start a local UI build on port 3187, sign in using a
Playwright CLI browser session, then run `playwright-cli run-code --filename
scripts/sol-pi/ui-smoke.js` in that session. It uses browser-local API fixtures and
checks defaults, toggling, a zero cache ratio, reducer model, serialization and reload.

### Local integration acceptance (2026-09-25)

- Gateway regression suite: 613 passed, 17 skipped.
- Runner regression suite: 518 passed, 2 skipped. Run from a Linux path without
  spaces; an existing MCP bridge assertion assumes an unquoted path.
- UI: dependency installation, TypeScript check and production build passed.
  This checkout has no Jest test cases; the settings interaction smoke passed,
  and the rendered desktop settings were visually checked.
- Official CLI smoke: all-on, all-off and reducer/fallback scenarios passed,
  including the exact isolated global installation layout used by the installer.
- Entrypoint shell syntax and Git whitespace checks passed.

This is a local integration branch, not a deployment. Docker is unavailable on
the validation host, so the complete image has not been built. Paid-provider runs,
forced online compaction, observation archive/recall behavior and checkpoint recycle
remain deployment acceptance work. No benchmark quality or speed claim is made.
