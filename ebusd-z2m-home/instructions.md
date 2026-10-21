# ebusd-z2m-home — Investigation & Refactor Plan

Status: IMPLEMENTED (2026-10-21; Tasks A-F code complete, images built locally; registry push/deploy pending the deployment host). Written 2026-10-21 after full code read.
Audience: user (for review) + AI agents (for implementation).

---

## 1. Current architecture (what exists today)

One app, three microservices, built from one multi-stage `Dockerfile` with a shared
`libs/libs.py` copied into every image root as `libs.py`.

| Service | Image | Entry | Role |
|---|---|---|---|
| watcher | `parasolnikov/watcher:0.6` | `watcher/ebusd_monitor.py` | MQTT → InfluxDB (ebusd/zigbee/esp/tasmota) + boiler-poll watchdog |
| controller | `parasolnikov/controller:0.6` | `controler/z2m_monitor.py` | Control loop: read schedule+temps from Influx → set TRV valves + boiler override |
| frontend | `parasolnikov/frontend:0.6` | `frontend/web.py` (Flask, 5002) | Schedule editor table, writes `time_measurement` to Influx |

**Data flow:**
```
ebusd (boiler bus) ──MQTT──▶ watcher ──▶ InfluxDB 'heat'
zigbee2mqtt (TRVs) ──MQTT──▶ watcher ──▶ InfluxDB 'heat'
esp/tasmota sensors ─MQTT──▶ watcher ──▶ InfluxDB 'heat'

controller loop (every 120 s):
  read 'time_measurement' (schedule, newest point)   from Influx
  read latest temps (per room, last 5 points)        from Influx
  compute temp_diff per room → publish:
    zigbee2mqtt/<addr>/set {current_heating_setpoint}
    ebusd/BAI/SetModeOverride/set 0;<settemp>;<WODA>;-;-;<PIEC_OFF>;0;<WODAOFF>;-;0;0;0
  write decision to measurement 'settings'

frontend:
  reads 'time_measurement', renders room×period table
  POST /post writes ONE field but re-creates the whole point with hardcoded defaults
```

**Runtime (hardcoded, from AGENTS.md):** MQTT = RabbitMQ MQTT plugin `192.168.0.230:11883`,
InfluxDB 1.8 `192.168.0.230:8086` db `heat` user/pass `username`/`password`, ebusd bridge at
`192.168.0.221:9999` (via ebusd container). Deployed via `infra/docker-compose.yml`.

---

## 2. Investigation findings — bugs & design problems

### 2.1 Watcher (issue #1: gets stuck, never restarts, silent topics)

1. **Topic substring matching** — `libs/libs.py:26-31` loops `if topic in msg.topic`:
   `"FlowTemp"` is a substring of `"FlowTempDesired"`, so one message resets the
   watchdog timer of the other topic (and `"HwcTemp"` vs `"HwcTempDesired"`,
   `"StorageTemp"` vs `"StorageTempDesired"`). Must match exact final topic segment.
2. **Watchdog publish is unreliable** — `check_boiler_messages.init()` (`libs.py:72-79`)
   creates a client, `loop_start()`, publishes `?3`, then immediately `loop_stop()`.
   The message can be dropped before the network loop flushes it. Also each retry
   creates a NEW client with a random client_id; no `on_disconnect`/reconnect handling.
3. **Thread dies silently, container stays up** — if `connect_mqtt` raises (broker not
   up yet after PC reboot), the `check_boiler_messages` thread dies; `t2`
   (`mqtt_to_influxdb` → `loop_forever()`) keeps the process alive, so Docker
   `restart: unless-stopped` never kicks in. Result: no `?3` re-requests are ever sent,
   ebusd only publishes on change/request → data goes stale forever = "stuck".
4. **No connection health check** — paho 1.6.1 auto-reconnects the subscriber, but nothing
   detects "connected but no data", and nothing re-sends the initial `?3` burst on reconnect.
5. **Initial request burst** — watcher never requests values at startup; it relies on
   `check_boiler_messages` timing out (5 min) first. Should request all topics on connect.
6. `timers` dict shared between 2 threads (GIL makes it work, but it's fragile; the
   check thread increments every second forever, no monotonic clock).
7. Minor: `client_id` global is generated once and reused; paho forbids two live clients
   with same id (broker kicks one) — with the per-retry new client this is a real risk.
8. No logging framework — print only; hard to see why it's stuck.

### 2.2 Controller (issue #2: acts on stale data, no fallback)

1. **Uses newest point regardless of age** — `return_current_temps()` computes
   `time_difference` but `regulate_temp()` (`libs.py:216-218`) blindly uses
   `current_temps[pokoj][0]['value']`. If a sensor stops publishing, the loop keeps
   reacting to old values forever → boiler pushed to 50-60°C for no reason.
2. **`time_difference.seconds` is broken** — `libs.py:298` uses `.seconds` which excludes
   days: a reading 26 h old reports as 2 h old. Must use `total_seconds()`.
3. **Empty results crash** — `current_temps[pokoj][0]` → `IndexError` when a room has
   no points at all (e.g. new sensor, Influx restarted). One bad room kills the whole
   loop (no try/except around the loop).
4. **All control params hardcoded in `Heating_main`** — valve temps (16/24), WODA,
   diff tables (`podiff`/`jodiff`), boiler override string. Changing them requires
   rebuild. User wants config via API/UI stored in Influx.
5. **Room→measurement mapping is crossed** (`libs.py:280-286`): `Kuchnia`←`esp/sypialnia`,
   `Sypialnia`←`esp/kuchnia` (documented gotcha, likely sensor-vs-topic mixup; must be
   configurable, not hardcoded).
6. **Z2M device addresses hardcoded** in `topics_z2m` — should be config too.
7. Boiler command is sent on EVERY loop (every 120 s) even if nothing changed; harmless
   but noisy; the override re-asserts itself so fine for fail-safe, but needs care when
   adding "hold" behavior.
8. `return_current_settings()` returns string `'ERROR'` on bad time — caller would crash
   on `settings.items()`; there's a `settings[pokoj] != 0` check but `'ERROR'` case
   is unhandled (`.items()` on string raises AttributeError).

### 2.3 Frontend (issue #3: poor UI, unsafe writes, hardcoded config)

1. **Editing one cell resets everything else to defaults** — `web.py:9-45`
   `measurments_preparation_sent` rebuilds the ENTIRE `time_measurement` point with
   hardcoded defaults and changes only one field. Any single edit silently wipes other
   cells' custom values. Critical.
2. **Defaults duplicated** in `web.py` and `temp_sending_to_influx.py` (and the commented
   block) — drift risk. Defaults belong in one place (config module).
3. **Broken template JS** — `site2.html`: duplicate `id` on two spans per cell,
   `input.replaceWith(para.id)` replaces input with a string, `para` is detached from DOM
   at that point, `row_n`/`coll_n` macro indexing fragile. The "max" span does nothing.
4. **Period times (MorningHour/DayHour/...) are stored as TAGS** — tags are indexed;
   editing them in Influx creates new series and the old point's fields are lost/mixed.
   Times must be FIELDS in the same point, or a separate measurement.
5. **No editing of controller params** (valve temps, WODA, diff tables, fallback), no
   room→sensor mapping UI, no live status view, no save feedback.
6. `static_folder='/app'` doesn't match Dockerfile WORKDIR `/user/src/app` (harmless but wrong).

### 2.4 Infra / repo

- `infra/compose_mqtt_home.yml` swaps `watcher`↔`controller` image names and pins `:0.5`
  (known bug from AGENTS.md; must be fixed in this refactor, bump to `:0.7`). The
  `frontend` service is missing entirely from compose.
- No healthchecks on any service.
- `infra/docker-compose.yml` only `include:`s infra compose files — it does NOT include
  `compose_mqtt_home.yml`, so the documented `docker compose up -d` entrypoint doesn't
  start the app services; deployment is manual/inconsistent.
- `ebusd-z2m-home/heating.py`, `oldlibsfromcontainer.py`, `temp_sending_to_influx.py`,
  `readmeas.py` are legacy/dev — leave as-is (or move to `other/`), do NOT run.

---

## 3. Refactor plan

### 3.1 Target structure

```
ebusd-z2m-home/
  Dockerfile                    # keep 3 targets; bump version to 0.7
  build.sh                      # bump version=0.7
  libs/
    __init__.py                 # (only needed if libs becomes a package; otherwise keep flat)
    libs.py                     # split into:
    config.py                   # config schema + defaults + read/write Influx + validation
    influx.py                   # connection, push_to_db, read_from_db (keep same signatures)
    mqtt.py                     # robust persistent MQTT client (reconnect, on_connect hooks)
    heating.py                  # PURE control logic: inputs → decision dict (no I/O) — unit-testable
    libs.py                     # backward-compat re-export (temp, then delete)
  watcher/
    ebusd_monitor.py            # rewritten watcher
  controler/
    z2m_monitor.py              # rewritten controller loop
  frontend/
    web.py                      # REST API (Flask)
    templates/index.html        # single clean UI page (rewrite, drop site2.html/site.html)
  requirements.txt              # unchanged (paho-mqtt, influxdb, flask, pika)

infra/
  docker-compose.yml            # default entrypoint: adds compose_mqtt_home.yml to includes
  compose_mqtt_home.yml         # fixed: correct images, :0.7, frontend service, healthcheck
  deploy.sh                     # NEW: single-command pull+up+ps (+ logs mode)
```

Keep Python 3.10+ (`match`/`case` ok). No new deps.

### 3.2 Config in InfluxDB (single source of truth)

Measurement `config`, tag `section` ∈ {`schedule`, `controller`, `rooms`}, one point per
section (overwrite on save). Fields:

- `schedule` (replaces tags-on-time_measurement!):
  `MorningHour, DayHour, EveningHour, NightHour` ("HH:MM" strings)
  + `{Room}{Period}Hour` floats, Room ∈ {Jozef, Kuchnia, Salon, Sypialnia}, Period ∈ {Morning, Day, Evening, Night}.
  - **Backward compat**: on first run, config module seeds `config/schedule` from the
    newest `time_measurement` point if it exists; frontend/controller read ONLY `config/*`.
  - 0.0 = off (existing convention).
- `controller`:
  `valve_off_temp` (16.0), `valve_on_temp` (24.0),
  `settemp_min` (40) — boiler fallback setpoint when nothing valid,
  `podiff` (JSON string: `{"-0.25":45,"-0.5":50,"-2":60}` — threshold:settemp, current semantics),
  `jodiff` (JSON string: `{"-0.5":40,"-1":45,"-2":50}`),
  `max_sensor_age_s` (default 900 = 15 min),
  `fallback_mode` ∈ {`hold`, `safe`, `skip`} (see 3.4),
  `loop_interval_s` (120),
  `room_priority` ("Jozef" — room whose diff table/override takes precedence, replacing hardcoded Jozef-vs-others logic)
- `water` (DHW / hot water heating config — replaces hardcoded `WODA`/`WODAOFF` in `Heating_main`):
  `woda` (42.0) — hot water setpoint while a window is active,
  `woda_off` (0.0) — hot water setpoint otherwise (0 = off),
  `water_times` — JSON list of `{"start":"HH:MM","end":"HH:MM"}` windows when the boiler
  heats water; supports midnight-spanning windows (same logic as schedule periods).
  Empty list `[]` = always `woda` (current behavior). Replaces the legacy
  `water_times = ['5:00', '16:00']` idea from root `heating.py`.
- `rooms`: fields `{Room}` = JSON string `{"measurement": "esp/tem", "value_name": "value", "zigbee": "0xa4c1384e6bcc60c6"}`.
  - This fixes the crossed `Kuchnia`↔`Sypialnia` mapping and makes Z2M addresses configurable.

### 3.3 Watcher rewrite (fixes issue #1)

Requirements:
- ONE persistent MQTT client (`loop_start()`) shared by subscriber and watchdog.
  `connect_mqtt()` gains `reconnect_delay_set(1, 30)`, unique client_id per process,
  `on_disconnect` logs reason code.
- `on_connect`: subscribe `["zigbee2mqtt/+", "ebusd/bai/+", "esp/+", "tele/+/SENSOR"]`
  AND publish `?3` to `ebusd/bai/<name>/get` for every topic in `topics` (initial burst,
  replaces wait-for-timeout).
- Exact topic matching: extract last segment of `msg.topic` (e.g. `FlowTemp` from
  `ebusd/bai/FlowTemp`) and look up in dict. `FlowTempDesired` must NOT reset `FlowTemp`.
- Watchdog thread: per-topic `last_seen` = `time.monotonic()`, updated in `on_message`.
  Every 10 s check: if `now - last_seen > 15*60` (override with `EBUSD_SILENCE_TIMEOUT`) → publish `?3` to that topic's `/get`
  (exponential backoff, max 1 retry per 60 s per topic, log each retry).
- **Self-heal / restart policy** (the "stuck" fix):
  - `on_disconnect` → paho auto-reconnects; if disconnected > 60 s, log loudly.
  - Wrap `mqtt_to_influxdb` main loop in try/except that logs and re-raises → process
    exits → Docker `restart: unless-stopped` restarts it. Threads must be daemon=False
    and joined, or simply run watchdog in main thread.
  - Influx write failures: catch, log, retry once, never crash the MQTT loop.
- Docker: add `healthcheck` (e.g. python one-liner checking last-seen freshness is
  complex; simplest: expose `/healthz` on a tiny HTTP port? NO — avoid Flask dep in
  watcher. Use `docker-compose` healthcheck hitting MQTT? Keep simple: rely on
  restart policy + logs. If healthcheck desired: write last_seen timestamp to a file,
  healthcheck tests `[ $(date +%s) -lt $(cat /tmp/last_seen)+600 ]`).
- Logging: `logging` module, INFO/ERROR levels, timestamps (helps debugging stuck state).

Acceptance: stop ebusd container → after 15 min watcher logs retries; start ebusd → data
resumes within 10 s. Kill broker → watcher logs disconnect, reconnects on broker up.
`docker kill` watcher → compose restarts it.

### 3.4 Controller rewrite (fixes issue #2)

Pure logic in `libs/heating.py`:
```
decide(schedule_for_now, rooms_config, latest_temps, controller_config) -> decision
decision = {
  'rooms': {room: {'temp', 'age_s', 'setpoint', 'diff', 'valve': 'open'|'close',
                   'stale': bool, 'action': 'keep'|'open'|'close'}},
  'boiler': {'settemp': float, 'piec_off': 0|1, 'override': "0;..;..;..." },
  'water': {'active': bool, 'temp': float},   # active = now within a water_times window
  'fallback_active': bool, 'reason': str,
  'valid_rooms': [...], 'stale_rooms': [...]
}
```
Loop (`z2m_monitor.py`), every `loop_interval_s`:
1. Load config (schedule, controller, water, rooms) from Influx via config module (fail: keep
   previous decision, log error, continue — never crash).
2. For each room fetch last temp from Influx (`SELECT value FROM <meas> ORDER BY time DESC LIMIT 1`).
   - `age_s` via `(now - t).total_seconds()` (fixes `.seconds` bug).
   - **No points at all** → treat as stale (age = ∞).
3. Water window: `water.active = is_now_in_windows(water_times)` (empty list = always
   active). Boiler override uses `woda` when active, `woda_off` otherwise — replaces the
   hardcoded `WODA=42`/`WODAOFF=0` in `Heating_main`.
4. Stale handling per room — `fallback_mode`:
   - `skip`: exclude room from diff calculation; valve → keep current (do not command),
     reason logged. Boiler decision uses only valid rooms.
   - `safe`: exclude from diff; valve → OPEN (fail warm), boiler NOT boosted by it.
   - `hold`: use last value but mark stale; excluded from boiler boost logic anyway
     (never boost boiler because of stale data).
   - Default: `skip`.
5. Boiler fallback: if NO valid room → do NOT change valve states; re-send last override
   or, if none, send `settemp_min` + `piec_off=0`; set `fallback_active` + reason.
6. Only publish valve messages for rooms whose desired state CHANGED (or config changed);
   always re-publish boiler override every N loops (N=10, i.e. ~20 min) to keep override alive.
7. Write each decision to Influx measurement `decisions` (fields: settemp, piec_off,
   water_active, woda_temp, per-room diff/stale flags, fallback_active) for Grafana/UI history.
   Also keep writing the legacy `settings` measurement (`Heating_temp` integer + per-room
   valve target floats) so existing Grafana panels keep working.
8. Keep Influx writes (`push_to_db`) with per-call client (current pattern works), but
   wrap in try/except; never let DB errors kill the loop.

Acceptance: stop an esp sensor → its room marked stale in `decisions`, valves/boiler not
boosted by it; if ALL sensors stale → fallback message logged, boiler at settemp_min,
no crash. 26-h-old reading must be reported as stale (regression test for `total_seconds`).
Outside a `water_times` window the override must contain `woda_off`, inside → `woda`
(verify via MQTT or `decisions`).

### 3.5 Frontend rewrite (fixes issue #3)

REST API (Flask, port 5002), JSON:
- `GET /api/config` → all four sections (schedule, controller, water, rooms) merged, with
  current defaults applied if missing.
- `PUT /api/config` → body `{section, values}` (or full config); validate:
  - HH:MM format for times; floats for temps; rooms exist; JSON strings parse;
  - reject unknown fields; on error return 400 with message.
  - Writes validated point to Influx `config` (tag `section`), overwrite.
- `GET /api/status` → latest temp+age per room (from Influx), last `decisions` point,
  MQTT boiler values (from watcher-written measurements) — read-only, poll every 30 s.
- `GET /` → `index.html`.

UI (single page, vanilla JS + fetch, no frameworks — keep image tiny):
- Tab "Schedule": grid Room × {Morning, Day, Evening, Night} with editable cells +
  row for period start times (MorningHour etc.) editable; Save button per change (or
  one Save); show validation errors inline; 0 = off.
- Tab "Controller": form for valve_off_temp, valve_on_temp, settemp_min,
  diff tables (as small key/value lists), max_sensor_age_s, fallback_mode (select),
  loop_interval_s, room_priority.
- Tab "Water": woda, woda_off + editable list of time windows (start/end HH:MM,
  add/remove rows, empty list = always on).
- Tab "Rooms": per room: display name → measurement, value_name, zigbee address.
- Tab "Status": current temps + age (colored when stale), boiler fields (FlowTemp etc.),
  last decision summary (which valves open/closed, settemp, fallback flag).
- All reads/writes via `GET/PUT /api/config`; no hardcoded defaults in template.

Acceptance: editing one schedule cell does NOT alter other cells (verify via Influx);
PUT with invalid data returns 400 and shows error in UI; after PUT, controller picks new
config within one loop interval; status tab shows staleness coloring.

### 3.6 Shared libs split (keep in `libs/libs.py` initially? — NO, split now)

- `libs/influx.py`: `get_influx_client(connection)`, `push_to_db(db, points, connection)`,
  `read_from_db(db, measurement, connection, limit)`, plus `read_latest(measurement,
  field, connection)` helper. Keep `connection` dict format for compat.
- `libs/mqtt.py`: `connect_mqtt(client_id, broker, port, on_connect=None,
  on_message=None) -> client` with reconnect settings; `publish(client, topic, msg)`.
- `libs/config.py`: `DEFAULTS` (single source of the schedule+controller+rooms defaults),
  `load_config(connection)`, `save_config(connection, section, values)`,
  `validate_section(section, values) -> (ok, errors)`, `schedule_for_now(schedule, t)`.
  Seeding from legacy `time_measurement` on first run.
- `libs/heating.py`: pure `decide()` (no I/O) + `override_string(settemp, piec_off, woda_value)` builder
  (`0;<settemp>;<WODA>;-;-;<PIEC_OFF>;0;<WODAOFF>;-;0;0;0`) + `is_now_in_windows(windows, t)` helper.
- `libs/libs.py`: temporary re-export shim so nothing breaks during transition, then remove.

Dockerfile: copy the whole `libs/` dir and add `libs/` to path? Simplest: keep the
"copy `libs/libs.py` to app root as `libs.py`" trick but ALSO copy `libs/*.py` to app
root and use `from libs import ...` consistently (imports work because files sit in app
root). For pure modules inside libs.py-split files, they must import each other via
`from libs import x` — same rule. Update Dockerfile `COPY libs/. .` before service COPY.

### 3.7 Build & deploy tooling (single-command build/push/deploy)

**Build — `ebusd-z2m-home/build.sh`** (rewrite; one command builds & pushes all images):
- `set -euo pipefail`; loop over `frontend controller watcher`.
- Version from env `VERSION` (default `0.7`); flags: `--no-push`, `--only=<target>`,
  `-v/--version <x>`, `-h/--help`.
- `docker image build --pull --tag parasolnikov/<target>:$VERSION --target <target> .`
  then `docker image push` (skip on `--no-push`).
- No `:latest` tag — compose always pins an exact version.
- Fail fast on build error (exit non-zero, prints which target failed).

**Deploy — `infra/deploy.sh`** (new):
- `set -euo pipefail`; runs from `infra/` (script resolves its own dir).
- `docker compose pull watcher controller frontend` (only app images — the included
  infra files build/pull their own images, don't pull the whole stack).
- `docker compose up -d --remove-orphans`, then `docker compose ps`.
- `./deploy.sh logs` → `docker compose logs -f --tail=100` for the 3 services.

**Compose — `infra/`** (fix the mess):
- `infra/compose_mqtt_home.yml`: fix swapped image names, pin `:0.7`, add the MISSING
  `frontend` service (ports `5002:5002`), `restart: unless-stopped` on all three,
  commented-out watcher healthcheck (file-based freshness via `/tmp/last_seen` —
  enable only after Task B lands, otherwise it would restart-loop the container).
- `infra/docker-compose.yml`: add `- compose_mqtt_home.yml` to its `include:` list so
  `docker compose up -d` from `infra/` starts the whole stack (matches AGENTS.md; today
  only the app services are missing from the default entrypoint).
- Requires Compose v2.20+ (include support) — already documented in AGENTS.md.

---

## 4. Task breakdown for the implementing agent

Order matters: libs first, then watcher, then controller, then frontend, then infra.

**Task A — libs split + config module**
1. Create `libs/influx.py`, `libs/mqtt.py`, `libs/config.py`, `libs/heating.py` (pure decide()).
2. `libs/libs.py` becomes a re-export shim.
3. Config module with defaults, validation, Influx read/write, legacy seeding.
4. Update Dockerfile to copy all libs; bump nothing else yet.

**Task B — watcher rewrite** (see 3.3 + acceptance tests). Include logging + file
timestamp `/tmp/last_seen` for optional healthcheck.

**Task C — controller rewrite** (see 3.4 + acceptance). Move ALL hardcoded params to
`config/controller`; pure logic in `libs/heating.py`; decisions to `decisions` measurement.
Add a dry-run env var `DRY_RUN=1` that logs decisions but publishes nothing (useful to
verify against live services without touching the boiler).

**Task D — frontend rewrite** (see 3.5 + acceptance). Drop `site.html`/`site2.html`,
single `index.html`. Include the Water tab (woda/woda_off/windows).

**Task E — infra**: fix compose names/version, add frontend service, wire
`compose_mqtt_home.yml` into `docker-compose.yml` includes, push `:0.7`, redeploy with
`infra/deploy.sh`, verify with `docker logs -f` for each service.

**Task F — build & deploy scripts** (can be done NOW, independent of code refactor):
rewrite `ebusd-z2m-home/build.sh` (single command, flags, fail-fast) and create
`infra/deploy.sh` per 3.7. Verify: `./build.sh --no-push` builds all 3 targets locally;
`./deploy.sh` pulls+up the stack.

---

## 5. Hard rules / gotchas for the agent (from AGENTS.md + findings)

- No tests/lint exist; verify by reading code + running against live services
  (192.168.0.230, credentials above). Use DRY_RUN where publishing matters.
- Python 3.10+; keep deps unchanged (paho-mqtt 1.6.1 API: `client.reconnect_delay_set`
  exists; `mqtt.Client(client_id)` with `mqtt.CallbackAPIVersion` is NOT available in 1.x).
- Imports: `from libs import ...`; in images all `libs/*.py` live at app root.
- Boiler override format: `0;<settemp>;<WODA>;-;-;<PIEC_OFF>;0;<WODAOFF>;-;0;0;0`.
- 0.0 in schedule = room off. Valves: publish `{"current_heating_setpoint": "<temp>"}`
  (string, not number!) to `zigbee2mqtt/<addr>/set` (note: current code stringifies — keep).
- Do NOT touch root `heating.py`, `oldlibsfromcontainer.py`, `temp_sending_to_influx.py`,
  `readmeas.py`, `infra/ebusdocker/ebusd-configuration` (vendored).
- Commit generated files as before (repo convention), but prefer not adding new noise.
- `ebusd/bai/+` also delivers `.../get` REQUEST echoes (subscription catches our own
  `?3` triggers) — exact-match on the last topic segment; skip topics containing `/get`.

## 6. Review checklist for user (after implementation)

- [ ] Watcher: kill ebusd container, wait 6 min → retries logged; restart ebusd → values flow again.
- [ ] Watcher: reboot PC → all three services come up, `?3` burst sent on connect, no stuck silence.
- [ ] Controller: unplug/kill one esp sensor → its room goes stale (log + `decisions`), boiler not boosted by it; all sensors stale → fallback (settemp_min), no crash.
- [ ] Controller: verify `decisions` measurement written each loop; check Grafana.
- [ ] Frontend: edit single cell → other cells unchanged (check Influx); bad input → 400 + inline error; times editable; controller params editable; water tab (woda/woda_off/windows) editable; status tab live.
- [ ] Water: outside a water window override contains woda_off, inside → woda; changing windows via UI takes effect within one loop interval.
- [ ] Build: `./build.sh` in ebusd-z2m-home builds+pushes all 3 images in one command; `./build.sh --no-push --only=watcher` works.
- [ ] Deploy: `./deploy.sh` in infra pulls + ups the stack and shows `docker compose ps` with correct image↔service mapping; `./deploy.sh logs` streams logs.
- [ ] Infra: `docker compose ps` shows all three app services + included infra, all `restart: unless-stopped`, healthchecks green (watcher healthcheck enabled after Task B).

## 7. Prompt template for future agent sessions

> You are working on the mqtt_home repo, ebusd-z2m-home app (3 Docker microservices:
> watcher, controller, frontend sharing libs/). Read AGENTS.md and
> ebusd-z2m-home/instructions.md FIRST — the instructions file is the plan and current
> state of the refactor. Implement Task <X> from section 4, following section 3 design
> and section 5 rules. Verify against the live services where possible (MQTT broker
> 192.168.0.230:11883, Influx 8086 heat username/password, ebusd 192.168.0.221). Do not
> modify files outside ebusd-z2m-home/ and infra/. Do not commit unless asked. Report
> what you changed and how you verified it.
