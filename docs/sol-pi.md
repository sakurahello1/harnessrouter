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
`docker/sol-pi/package-lock.json` locks the complete npm dependency graph, including
MCP adapter 2.37.0. Registry artifacts carry SHA-512 integrity; the upstream Git
commit is fixed and its 23 extension source files are checked against
`docker/sol-pi/source.sha256`. Installation is staged and validated before replacement;
the previous installation is retained if replacement fails. Published packages are
readable/executable by isolated session users and not writable by those users.
The installer also repairs permissions when reusing a verified runtime. No unverified fallback
or floating dependency is used by this installer. The CI runtime job runs the same
installer and CLI smoke test without a provider key.

For a separately managed runner, install the same dependencies and set:

```sh
export HR_SOL_PI_BIN=/opt/sol-pi/bin/pi
export HR_SOL_PI_ENTRY=/opt/sol-pi/lib/node_modules/sol-pi/src/sol-pi/index.ts
export HR_SOL_PI_MCP_EXT=/opt/sol-pi/lib/node_modules/pi-mcp-adapter
```

An unavailable runtime fails with 503; the runner never substitutes ordinary Pi.

## Create and configure

Choose **SoL-Pi** to inspect the built-in defaults. Use **Fork and Customize** to
create an editable agent, then use **SoL-Pi mechanisms** in its settings.
Each switch is independent. All four default to enabled on this base;
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
checkpoint and excluded from user-produced file cards. `auth.json`, `models.json`
and `mcp.json` under the SoL-Pi agent directory are excluded from snapshots; they
can carry provider keys or MCP credentials. The runner rebuilds connection settings
on the next turn. Session headers are checked before resume so missing history is
reported through the existing `resume_lost` event.

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
python scripts/sol-pi/check-lock.py
python scripts/sol-pi/smoke.py
```

The smoke test uses a local scripted provider and the installed, unmodified Pi and
SoL-Pi packages. It verifies tool schemas with switches on/off, actual fused file
write and shell execution, output artifacts, conversation resume and model switch.
It also triggers the real reducer, verifies safe fallback on invalid evidence,
and checks that auxiliary-model usage is recorded once. It deletes and restores
the workspace through a credential-excluding archive and verifies that the next
CLI process retains history, including switching back to the original model.
It does not measure task quality or replace live-provider support-matrix checks.
Use `scripts/support-matrix` for provider/model-specific acceptance before deployment.

For the settings smoke check, start a local UI build on port 3187, sign in using a
Playwright CLI browser session, then run `playwright-cli run-code --filename
scripts/sol-pi/ui-smoke.js` in that session. It uses browser-local API fixtures and
checks defaults, toggling, a zero cache ratio, reducer model, serialization and reload.

### Local validation record (2026-09-25)

- Combined Gateway/Runner regression on current upstream main: 1,195 passed, 19 skipped. Run from a Linux
  path without spaces; an existing MCP bridge assertion assumes an unquoted path.
- Revised UI: type-check and production build passed. Jest contains no tests and
  was run with `--passWithNoTests`; this is not evidence of UI test coverage.
  The browser settings smoke passed default values, toggling, zero ratio, reducer
  model, save/reload, and read-only built-in defaults without custom-setting leakage.
- Final integrity lock reinstalled successfully. Official CLI smoke passed all-on,
  all-off, reducer/fallback, checkpoint restore, and model switch/back against a
  scripted endpoint. These are not live model-quality measurements.
- Dedicated Banban connection, DeepSeek V4.1 Flash: first turn, follow-up, artifact
  cards versus stored files, and forced recycle/history recall passed (4/4).
  Live model switch is n/a because only one model was authorized.
- Custom harness: stored skill and tool policy, hidden script token, produced
  `stamp.txt`, disabled `edit` unused, and a recorded DeepWiki MCP call all passed.
- Local plus final-container runs: 12 successful real turns used 39,636
  uncached input, 1,252 output and 44,160 cached input tokens.
  Assuming the user's rates are CNY per million, estimated cost is CNY 0.0068;
  this is not a provider invoice.
- Entrypoint shell syntax and Git whitespace checks passed.

Raw and reviewed matrix results and usage are in
[verification/sol-pi-2026-09-25](verification/sol-pi-2026-09-25/README.md).
The matrix column certifies only this connection/model on this local instance.
The broader catalog inherits Pi's transport coverage, not a measured compatibility
claim for every model. Forced online compaction and long-context archive/recall
quality have not been measured against a paid provider.

The core container built and passed first-start installation, login, runtime version,
non-owner execution/non-writability, health check, and the same real routing/custom
harness suites. Build flags: `WITH_DOC_PREVIEW=0`, `WITH_MEDIA=0`,
`WITH_STARTER_KITS=0`, `WITH_BUILTIN_SKILLS=0` (browser defaults to 0).
The default all-feature image was not certified: enabling bundled OfficeCLI while
turning off document preview exposed a missing ICU dependency in that existing
optional-feature combination. No claim is made about office/media starter bundles.

The container run found and fixed a real SoL-Pi installer bug: `mktemp` left the
published runtime root at 0700, preventing a session uid from executing Pi.
Fresh installation and repair of a reused 0700 runtime now pass with uid 20000;
CI also checks execution/non-writability as a different user. Windows builds also
needed recursive dependency exclusions and LF enforcement for Docker shell scripts.

Responsive audit covered built-in and custom settings at 15 widths (390–1440 px).
Only the existing sidebar +4 px finding appeared, reproduced on ordinary Pi; no
new settings-content or page overflow was found. This is not a zero-finding audit.
This remains a local integration branch, not a published deployment.
