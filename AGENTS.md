# AGENTS.md

Personal home-automation / heating-control repo. No tests, lint, formatter, CI, or Makefile exist — verify changes by reading code and (when possible) running against the live services.

## Where the real code lives

- `ebusd-z2m-home/` — the active system (current working dir). A single multi-stage `Dockerfile` builds three images from the shared `libs/` package (`influx.py`, `mqtt.py`, `config.py`, `heating.py`; `libs/libs.py` is a legacy re-export shim):
  - `frontend` → `frontend/web.py` (Flask REST config/status API + schedule editor, port 5002)
  - `controller` → `controler/z2m_monitor.py` → `libs.decide()` (heating control loop, `DRY_RUN=1` supported)
  - `watcher` → `watcher/ebusd_monitor.py` (MQTT→InfluxDB + boiler polling/watchdog)
- Root `heating.py`, `mqtt_home_pub.py`, `mqtt_home_sub.py`, `rab.py`, `rth.py`, `other/` — older standalone experiments; `ebusd-z2m-home/heating.py` is a copy of root `heating.py`. Prefer `ebusd-z2m-home/`.
- `infra/` — deployments. `infra/docker-compose.yml` uses Compose `include:` (requires Compose v2.20+); run `docker compose up -d` from inside `infra/`.
- `infra/ebusdocker/ebusd-configuration/` — vendored upstream ebusd config (has its own `.github/`); do not treat as this project's code.
- `cpp_driver/` — host/RPi-only 64x32 RGB LED matrix clients (not containerized).

## Build & deploy

- Build/push images: `cd ebusd-z2m-home && ./build.sh` (pushes `parasolnikov/<target>:0.7` to Docker Hub; use `--no-push`, `--only=<target>`, `-v <version>`). Note the dir is spelled `controler` but the Docker target is `controller`.
- Deploy: `cd infra && ./deploy.sh` (pull + `up -d` + `ps`); `./deploy.sh logs` streams the three app services. `infra/compose_mqtt_home.yml` pins `:0.7` with correct image names and includes the frontend.
- ebusd config is mounted from an absolute host path `/root/mqtt_home/...`, so infra assumes the repo sits at `/root/mqtt_home`.

## Runtime topology (all IPs/creds are hardcoded)

- MQTT = RabbitMQ MQTT plugin at `192.168.0.230:11883` (1883 in-network; mgmt 15672). Do not use root `mqtt_home_pub.py`, which points at stale `192.168.0.30:1883`.
- InfluxDB 1.8 at `192.168.0.230:8086`, database `heat`, placeholder user/pass `username`/`password`.
- ebusd reads boiler bus `192.168.0.221:9999`, publishes `ebusd/bai/...`; Zigbee2MQTT `zigbee2mqtt/<ieee-addr>/...`; ESP sensors `esp/<name>`; Tasmota `tele/<name>/SENSOR`.
- Boiler is driven by publishing to `ebusd/BAI/SetModeOverride/set` with `0;<settemp>;<WODA>;-;-;<PIEC_OFF>;0;<WODAOFF>;-;0;0;0`.

## Gotchas

- Requires Python 3.10+ (`match`/`case` in `libs.measurments_preparation_sent`). Docker base is `python:3-slim-bookworm`.
- Imports are `from libs import ...`; in the images the whole `libs/` package is copied to `/user/src/app/libs`. Running `readmeas.py` from a checkout does not resolve this the same way.
- Runtime config lives in Influx measurement `config` (tag `section` ∈ {`schedule`, `controller`, `water`, `rooms`}). `config/schedule` is seeded once from the legacy `time_measurement` point. Room→measurement mapping and Zigbee addresses are in `config/rooms`.
- Watcher watchdog re-requests any ebusd topic silent for 15 minutes (`EBUSD_SILENCE_TIMEOUT`, default 900 s) by publishing `?3` and requests all topics on MQTT connect. Controller writes each decision to measurement `decisions`.
- Hardcoded/placeholder credentials throughout; env vars are only used in root `mqtt_home_pub.py`.
- Generated files are committed (`**/__pycache__/*.pyc`, `heat.out`, `infra/z2m/data/*.db|*.json`).
- `cpp_driver/build.sh` compiles `reciever_printer.cpp` against `/home/p/rpi-rgb-led-matrix`; `buc.sh` references `matrix_influx_c.c`, which does not exist.
