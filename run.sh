#!/usr/bin/env bash
#
# Human-Sim developer control script.
#
# One entry point for the things a person actually does with this repository:
# start the engine service and the Run Lab UI together, stop them, look at
# their logs, run a headless simulation, and run the checks CI runs.
#
# Usage: ./run.sh <command> [options]   ("./run.sh help" for the full list)

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

RUN_DIR="$ROOT/.run"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
UI_PORT="${UI_PORT:-5173}"

API_PID="$RUN_DIR/api.pid"
UI_PID="$RUN_DIR/ui.pid"
API_LOG="$RUN_DIR/api.log"
UI_LOG="$RUN_DIR/ui.log"

# ---------------------------------------------------------------- output ---

if [ -t 1 ]; then
  BOLD=$'\033[1m'; RED=$'\033[31m'; GREEN=$'\033[32m'
  YELLOW=$'\033[33m'; DIM=$'\033[2m'; OFF=$'\033[0m'
else
  BOLD=''; RED=''; GREEN=''; YELLOW=''; DIM=''; OFF=''
fi

info() { printf '%s==>%s %s\n' "$BOLD" "$OFF" "$*"; }
ok()   { printf '%s  ok%s %s\n' "$GREEN" "$OFF" "$*"; }
warn() { printf '%s warn%s %s\n' "$YELLOW" "$OFF" "$*" >&2; }
die()  { printf '%serror%s %s\n' "$RED" "$OFF" "$*" >&2; exit 1; }

# --------------------------------------------------------------- helpers ---

# The Python used for the dependency-free core. The virtualenv is only
# required for the optional service.
core_python() {
  if [ -x "$PY" ]; then printf '%s' "$PY"; else printf 'python3'; fi
}

require_venv() {
  [ -x "$PY" ] || die "no virtualenv at .venv — run: ./run.sh setup"
  "$PY" -c 'import fastapi, uvicorn' 2>/dev/null ||
    die "API dependencies missing — run: ./run.sh setup"
}

require_ui_deps() {
  command -v npm >/dev/null 2>&1 || die "npm not found (Node.js 24+ required)"
  [ -d "$ROOT/ui/node_modules" ] ||
    die "ui/node_modules missing — run: ./run.sh setup"
}

# Reads a pid file and echoes the pid only when that process is still alive.
live_pid() {
  local file="$1" pid
  [ -f "$file" ] || return 1
  pid="$(cat "$file" 2>/dev/null || true)"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  printf '%s' "$pid"
}

# Starts a command detached in its own process group so that stopping it also
# stops the children it spawns (npm -> vite, uvicorn -> reloader).
spawn() {
  local pidfile="$1" logfile="$2"; shift 2
  mkdir -p "$RUN_DIR"
  if command -v setsid >/dev/null 2>&1; then
    setsid "$@" >>"$logfile" 2>&1 &
  else
    "$@" >>"$logfile" 2>&1 &
  fi
  local pid=$!
  printf '%s\n' "$pid" >"$pidfile"
  printf '%s' "$pid"
}

# Terminates a process group, escalating to KILL if it ignores TERM.
stop_pid() {
  local name="$1" pidfile="$2" pid
  if ! pid="$(live_pid "$pidfile")"; then
    rm -f "$pidfile"
    printf '%s  --%s %s not running\n' "$DIM" "$OFF" "$name"
    return 0
  fi
  kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  local waited=0
  while kill -0 "$pid" 2>/dev/null && [ "$waited" -lt 100 ]; do
    sleep 0.1
    waited=$((waited + 1))
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -KILL "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
    warn "$name did not exit on SIGTERM; killed"
  fi
  rm -f "$pidfile"
  ok "$name stopped (pid $pid)"
}

port_owner() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti "tcp:$port" -sTCP:LISTEN 2>/dev/null | head -1
  elif command -v ss >/dev/null 2>&1; then
    ss -lptnH "sport = :$port" 2>/dev/null |
      grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2
  fi
}

http_ok() {
  local url="$1"
  if command -v curl >/dev/null 2>&1; then
    curl -fsS -m 2 -o /dev/null "$url" 2>/dev/null
  else
    "$(core_python)" - "$url" <<'PY' 2>/dev/null
import sys, urllib.request
urllib.request.urlopen(sys.argv[1], timeout=2).read()
PY
  fi
}

# Polls a URL until it answers, failing with the tail of the log if it never
# does. A service that dies at startup should say why, not just time out.
wait_for() {
  local name="$1" url="$2" logfile="$3" pidfile="$4" tries="${5:-100}"
  local n=0
  while [ "$n" -lt "$tries" ]; do
    if ! live_pid "$pidfile" >/dev/null; then
      printf '\n'
      warn "$name exited during startup; last log lines:"
      tail -n 20 "$logfile" >&2 || true
      return 1
    fi
    if http_ok "$url"; then return 0; fi
    sleep 0.2
    n=$((n + 1))
  done
  printf '\n'
  warn "$name did not answer $url in time; last log lines:"
  tail -n 20 "$logfile" >&2 || true
  return 1
}

# ------------------------------------------------------------- commands ----

cmd_setup() {
  info "Creating virtualenv and installing service dependencies"
  [ -d "$VENV" ] || python3 -m venv "$VENV"
  "$PY" -m pip install --quiet --upgrade pip
  "$PY" -m pip install --quiet -r requirements-api.txt
  "$PY" -m pip install --quiet -r requirements-dev.txt
  ok "Python environment ready"

  if command -v npm >/dev/null 2>&1; then
    info "Installing UI dependencies"
    (cd ui && npm ci --silent)
    ok "UI dependencies ready"
  else
    warn "npm not found; skipping UI dependencies (Node.js 24+ required)"
  fi

  printf '\nNext: %s./run.sh start%s\n' "$BOLD" "$OFF"
}

start_api() {
  require_venv
  if pid="$(live_pid "$API_PID")"; then
    ok "API already running (pid $pid)"
    return 0
  fi
  local owner
  owner="$(port_owner "$API_PORT" || true)"
  if [ -n "$owner" ]; then
    die "port $API_PORT is already in use by pid $owner"
  fi
  mkdir -p "$RUN_DIR"
  : >"$API_LOG"
  info "Starting engine API on http://$API_HOST:$API_PORT"
  local pid
  pid="$(spawn "$API_PID" "$API_LOG" \
    "$PY" -m uvicorn src.human_sim_service.api:app \
    --host "$API_HOST" --port "$API_PORT")"
  wait_for "API" "http://$API_HOST:$API_PORT/api/v1/health" \
    "$API_LOG" "$API_PID" || { rm -f "$API_PID"; return 1; }
  ok "API ready (pid $pid) — log: .run/api.log"
}

start_ui() {
  require_ui_deps
  if pid="$(live_pid "$UI_PID")"; then
    ok "UI already running (pid $pid)"
    return 0
  fi
  local owner
  owner="$(port_owner "$UI_PORT" || true)"
  if [ -n "$owner" ]; then
    die "port $UI_PORT is already in use by pid $owner"
  fi
  mkdir -p "$RUN_DIR"
  : >"$UI_LOG"
  info "Starting Run Lab UI on http://127.0.0.1:$UI_PORT"
  # vite.config.ts reads these to point its /api proxy at the engine service.
  export API_HOST API_PORT
  local pid
  pid="$(spawn "$UI_PID" "$UI_LOG" \
    npm --prefix "$ROOT/ui" run dev -- --port "$UI_PORT" --strictPort)"
  wait_for "UI" "http://127.0.0.1:$UI_PORT/" "$UI_LOG" "$UI_PID" ||
    { rm -f "$UI_PID"; return 1; }
  ok "UI ready (pid $pid) — log: .run/ui.log"
}

cmd_start() {
  local want_api=1 want_ui=1 follow=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --api-only) want_ui=0 ;;
      --ui-only)  want_api=0 ;;
      --logs|-f)  follow=1 ;;
      *) die "unknown option for start: $1" ;;
    esac
    shift
  done

  [ "$want_api" -eq 1 ] && start_api
  [ "$want_ui" -eq 1 ] && start_ui

  printf '\n'
  [ "$want_ui" -eq 1 ] &&
    printf '  Run Lab   %shttp://127.0.0.1:%s%s\n' "$BOLD" "$UI_PORT" "$OFF"
  [ "$want_api" -eq 1 ] &&
    printf '  API       %shttp://%s:%s/api/v1/health%s\n' \
      "$BOLD" "$API_HOST" "$API_PORT" "$OFF"
  printf '\n  Stop with %s./run.sh stop%s\n\n' "$BOLD" "$OFF"

  if [ "$follow" -eq 1 ]; then
    cmd_logs
  fi
}

cmd_stop() {
  local want_api=1 want_ui=1
  while [ $# -gt 0 ]; do
    case "$1" in
      --api-only) want_ui=0 ;;
      --ui-only)  want_api=0 ;;
      *) die "stop takes: --api-only | --ui-only" ;;
    esac
    shift
  done
  info "Stopping services"
  [ "$want_ui" -eq 1 ] && stop_pid "UI" "$UI_PID"
  # Stopping the API ends every run it holds: runs live in its memory and
  # there is no rehydration path. Closing the UI is the safe half of this.
  [ "$want_api" -eq 1 ] && stop_pid "API" "$API_PID"
  return 0
}

cmd_restart() {
  cmd_stop
  printf '\n'
  cmd_start "$@"
}

cmd_status() {
  local pid
  printf '%sHuman-Sim services%s\n\n' "$BOLD" "$OFF"
  if pid="$(live_pid "$API_PID")"; then
    if http_ok "http://$API_HOST:$API_PORT/api/v1/health"; then
      printf '  API  %srunning%s   pid %s  http://%s:%s\n' \
        "$GREEN" "$OFF" "$pid" "$API_HOST" "$API_PORT"
    else
      printf '  API  %sstarting%s  pid %s  (health check not answering yet)\n' \
        "$YELLOW" "$OFF" "$pid"
    fi
  else
    printf '  API  %sstopped%s\n' "$DIM" "$OFF"
  fi
  if pid="$(live_pid "$UI_PID")"; then
    printf '  UI   %srunning%s   pid %s  http://127.0.0.1:%s\n' \
      "$GREEN" "$OFF" "$pid" "$UI_PORT"
  else
    printf '  UI   %sstopped%s\n' "$DIM" "$OFF"
  fi
  printf '\n'
}

cmd_logs() {
  local files=()
  case "${1:-all}" in
    api) files=("$API_LOG") ;;
    ui)  files=("$UI_LOG") ;;
    all) files=("$API_LOG" "$UI_LOG") ;;
    *)   die "logs takes: api | ui | all" ;;
  esac
  local existing=()
  for f in "${files[@]}"; do [ -f "$f" ] && existing+=("$f"); done
  [ "${#existing[@]}" -gt 0 ] || die "no logs yet — start something first"
  info "Following logs (Ctrl-C to stop; services keep running)"
  tail -n 40 -f "${existing[@]}"
}

cmd_sim() {
  "$(core_python)" -m sims.simple_sim "$@"
}

cmd_scenario() {
  local scenario="${1:-scenarios/two_islands.json}"
  shift || true
  [ -f "$scenario" ] || die "no scenario file at $scenario"
  "$(core_python)" -m sims.simple_sim --scenario "$scenario" "$@"
}

# Runs held by the service, which keep going after this command returns.
cmd_lab() {
  API_HOST="$API_HOST" API_PORT="$API_PORT" \
    HUMAN_SIM_API="${HUMAN_SIM_API:-http://$API_HOST:$API_PORT}" \
    HUMAN_SIM_UI="${HUMAN_SIM_UI:-http://127.0.0.1:$UI_PORT}" \
    "$(core_python)" -m sims.lab "$@"
}

cmd_test() {
  local target="${1:-all}" failed=0
  if [ "$target" = "all" ] || [ "$target" = "py" ]; then
    info "Python test suite"
    "$(core_python)" -m unittest discover -v || failed=1
  fi
  if [ "$target" = "all" ] || [ "$target" = "ui" ]; then
    if [ -d "$ROOT/ui/node_modules" ]; then
      info "UI test suite"
      (cd ui && npm test --silent) || failed=1
    else
      warn "ui/node_modules missing; skipping UI tests"
    fi
  fi
  [ "$failed" -eq 0 ] || die "tests failed"
  ok "tests passed"
}

cmd_lint() {
  local failed=0
  info "flake8"
  if [ -x "$VENV/bin/flake8" ]; then
    "$VENV/bin/flake8" src sims tests || failed=1
  else
    "$(core_python)" -m flake8 src sims tests || failed=1
  fi
  if [ -d "$ROOT/ui/node_modules" ]; then
    info "TypeScript typecheck"
    (cd ui && npm run typecheck --silent) || failed=1
  else
    warn "ui/node_modules missing; skipping typecheck"
  fi
  [ "$failed" -eq 0 ] || die "lint failed"
  ok "lint clean"
}

cmd_build() {
  require_ui_deps
  info "Building UI"
  (cd ui && npm run build)
  ok "UI built to ui/dist"
}

cmd_check() {
  cmd_lint
  printf '\n'
  cmd_test
}

cmd_clean() {
  info "Removing run artifacts"
  cmd_stop >/dev/null 2>&1 || true
  rm -rf "$RUN_DIR"
  find "$ROOT/src" "$ROOT/sims" "$ROOT/tests" -name '__pycache__' -type d \
    -prune -exec rm -rf {} + 2>/dev/null || true
  rm -rf "$ROOT/ui/dist"
  ok "cleaned"
}

cmd_help() {
  cat <<EOF
${BOLD}Human-Sim control script${OFF}

  ${BOLD}./run.sh <command> [options]${OFF}

${BOLD}Services${OFF}
  setup                 Create .venv, install Python + UI dependencies
  start [opts]          Start the engine API and the Run Lab UI
      --api-only          only the engine service
      --ui-only           only the web UI
      --logs, -f          follow logs after starting
  stop [opts]           Stop services (default both)
      --ui-only           leave the engine running, and its runs with it
      --api-only          stop the engine; every run it holds is lost
  restart [opts]        Stop, then start again (same options as start)
  status                Show what is running
  logs [api|ui|all]     Follow service logs (Ctrl-C leaves them running)

${BOLD}Simulation${OFF}
  sim [args...]         Headless run inside this command: sims.simple_sim
                        e.g. ./run.sh sim --population 1000 --ticks 240 --seed 42
  scenario [file] [..]  Run a scenario (default scenarios/two_islands.json)

${BOLD}Long-lived runs${OFF}   (held by the engine service, outlive this shell)
  lab start [opts]      Create a run and set the engine advancing it
                        e.g. ./run.sh lab start --scenario scenarios/two_islands.json --pace 1h
  lab list              Every run the service is holding
  lab watch <id>        Print metrics periodically; Ctrl-C leaves it running
  lab play|pause <id>   Start or stop the engine advancing a run
  lab snapshot <id>     Export full state as JSON (--out FILE)
  lab delete <id>...    Stop runs and release their memory
      --all               every idle run (add --running to take those too)
  Attach a browser to any of them at ${DIM}http://127.0.0.1:${UI_PORT}/?run=<id>${OFF}

${BOLD}Checks${OFF}
  test [py|ui|all]      Run the test suites
  lint                  flake8 + TypeScript typecheck
  check                 lint, then test
  build                 Production build of the UI

${BOLD}Housekeeping${OFF}
  clean                 Stop services, remove .run/, __pycache__, ui/dist
  help                  This message

${BOLD}Environment${OFF}
  API_HOST (${API_HOST})  API_PORT (${API_PORT})  UI_PORT (${UI_PORT})

Logs and pid files live in ${DIM}.run/${OFF}
EOF
}

# ------------------------------------------------------------------ main ---

command="${1:-help}"
shift || true

case "$command" in
  setup)             cmd_setup "$@" ;;
  start|up)          cmd_start "$@" ;;
  stop|down)         cmd_stop "$@" ;;
  restart)           cmd_restart "$@" ;;
  status|ps)         cmd_status "$@" ;;
  logs|log)          cmd_logs "$@" ;;
  sim|run)           cmd_sim "$@" ;;
  scenario)          cmd_scenario "$@" ;;
  lab)               cmd_lab "$@" ;;
  test)              cmd_test "$@" ;;
  lint)              cmd_lint "$@" ;;
  check)             cmd_check "$@" ;;
  build)             cmd_build "$@" ;;
  clean)             cmd_clean "$@" ;;
  help|-h|--help)    cmd_help ;;
  *) printf '%serror%s unknown command: %s\n\n' "$RED" "$OFF" "$command" >&2
     cmd_help >&2
     exit 1 ;;
esac
