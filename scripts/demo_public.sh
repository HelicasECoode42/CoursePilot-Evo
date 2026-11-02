#!/usr/bin/env bash
# CoursePilot 公开 demo 一键启动 / 停止 / 状态（macOS）。
#
# 用法
#   scripts/demo_public.sh start [--caffeinate]   按顺序拉起 Java 8081 -> Python 8000 -> 生产构建 + vite preview 5173 -> cloudflared 隧道
#   scripts/demo_public.sh stop                    停止这些进程（先 TERM，等 15 秒不退再 KILL）
#   scripts/demo_public.sh status                  查看各组件与公网地址
#
# 配置与密钥都不在仓库里
#   ~/.config/coursepilot/demo.env   指向真实配置文件的一行指针（本身不含密钥）
#   真实配置文件                      data/private/stack.env（被 .gitignore 覆盖）
#   隧道配置                          ~/.cloudflared/config.yml（隧道 ID 与凭据文件路径）
# 日志与 PID 文件：~/Library/Logs/coursepilot/（每次 start 覆盖上一次的日志）
#
# 公网演示只跑生产构建（web/dist，经 vite preview），不跑 Vite 开发服务器：
#   - dev 服务器会暴露源码、HMR 与 WebSocket，不适合放到公网；
#   - preview 只服务构建产物，带安全响应头（CSP、nosniff、X-Frame-Options 等），/api 转发到 8000。
# 本脚本不打印任何密钥值，只输出组件状态、端口、HTTP 状态码和路径。
# --caffeinate 会用 caffeinate -i 防止 Mac 因空闲睡眠断开服务；stop 时一并停掉。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO_ENV="$HOME/.config/coursepilot/demo.env"
LOG_DIR="$HOME/Library/Logs/coursepilot"
TUNNEL_NAME="coursepilot-demo"
PUBLIC_HOST="coursepilot.helicase.xin"
PUBLIC_URL="https://$PUBLIC_HOST"
# 启动前必须存在的环境变量名（只列名字，绝不打印值）
REQUIRED_VARS=(CP_SERVICE_KEY CP_MODEL_BASE_URL CP_MODEL_API_KEY CP_MODEL_ID CP_JAVA_BASE_URL CP_CORS_ORIGINS)
# 启动顺序：Java 先于 Python（网关启动后要能连上 Java），Vite 之后，最后开隧道
COMPONENTS=(java api web tunnel)
STOP_ORDER=(tunnel web api java caffeinate)

die() {
  echo "错误：$*" >&2
  exit 1
}

usage() {
  sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

# ---------- 端口与进程 ----------

port_pids() { lsof -nP -t -iTCP:"$1" -sTCP:LISTEN 2>/dev/null || true; }

port_up() { [ -n "$(port_pids "$1")" ]; }

# 组件当前的全部相关 PID：PID 文件里记录的 + 端口/进程名查到的（脚本不是它启动的也能停）
comp_pids() {
  local name=$1 pidfile="$LOG_DIR/$1.pid" recorded="" found=""
  if [ -f "$pidfile" ]; then
    recorded="$(cat "$pidfile" 2>/dev/null || true)"
    kill -0 "$recorded" 2>/dev/null || recorded=""
  fi
  case "$name" in
    java) found="$(port_pids 8081)" ;;
    api) found="$(port_pids 8000)" ;;
    web) found="$(port_pids 5173)" ;;
    tunnel) found="$(pgrep -f "cloudflared tunnel.* run $TUNNEL_NAME" || true)" ;;
    *) found="" ;;
  esac
  printf '%s\n%s\n' "$recorded" "$found" | sed '/^$/d' | sort -u
}

# 后台启动：日志覆盖写入，PID 写入 PID 文件；nohup 让它不随终端退出
launch() {
  local name=$1 dir=$2
  shift 2
  (
    cd "$dir"
    nohup "$@" >"$LOG_DIR/$name.log" 2>&1 </dev/null &
    echo $! >"$LOG_DIR/$name.pid"
  )
}

# 等端口监听；等待期间进程先退出则直接失败并指向日志
wait_port() {
  local port=$1 limit=$2 name=$3 i
  for ((i = 0; i < limit; i++)); do
    port_up "$port" && return 0
    [ -n "$(comp_pids "$name")" ] || die "$name 进程已退出，看日志：$LOG_DIR/$name.log"
    sleep 1
  done
  die "$name 在 ${limit} 秒内没有监听 ${port}，看日志：$LOG_DIR/$name.log"
}

# 等日志出现某句话（cloudflared 没有本地端口，以「隧道已注册」为就绪）
wait_log() {
  local pattern=$1 limit=$2 name=$3 i
  for ((i = 0; i < limit; i++)); do
    grep -q "$pattern" "$LOG_DIR/$name.log" 2>/dev/null && return 0
    [ -n "$(comp_pids "$name")" ] || die "$name 进程已退出，看日志：$LOG_DIR/$name.log"
    sleep 1
  done
  die "$name 在 ${limit} 秒内未完成连接，看日志：$LOG_DIR/$name.log"
}

# ---------- 各组件的启动方式 ----------

start_java() {
  launch java "$REPO/java-environment" ./mvnw -B spring-boot:run
  wait_port 8081 180 java
}

start_api() {
  # 网关在 cloudflared 后面，客户端 IP 只能从 CF-Connecting-IP 取（另一处代码读这个开关）
  export CP_TRUST_CF_CONNECTING_IP=true
  launch api "$REPO/agent-runtime" "$REPO/.venv/bin/python" -m uvicorn agent_runtime.api.app:app --host 127.0.0.1 --port 8000
  wait_port 8000 60 api
}

# 生产构建：前端同源访问 /api，所以 VITE_API_BASE_URL 固定为 "/"
build_web() {
  local log="$LOG_DIR/web-build.log"
  echo "web：生产构建中（输出 ${log}）..."
  (cd "$REPO/web" && VITE_API_BASE_URL="/" npm run build >"$log" 2>&1) || die "web 生产构建失败，看日志：$log"
}

start_web() {
  build_web
  export COURSEPILOT_TUNNEL_HOST="$PUBLIC_HOST,www.$PUBLIC_HOST"
  launch web "$REPO/web" ./node_modules/.bin/vite preview --host 127.0.0.1 --port 5173 --strictPort
  wait_port 5173 60 web
}

start_tunnel() {
  launch tunnel "$HOME" cloudflared tunnel --config "$HOME/.cloudflared/config.yml" run "$TUNNEL_NAME"
  wait_log "Registered tunnel connection" 60 tunnel
}

# ---------- 前置检查与配置 ----------

load_env() {
  [ -f "$DEMO_ENV" ] || die "缺少 ${DEMO_ENV}。请创建它，只需一行：COURSEPILOT_SECRETS_FILE=<真实配置文件的绝对路径>。真实配置文件需要这些变量名：${REQUIRED_VARS[*]}"
  set -a
  # shellcheck disable=SC1090
  . "$DEMO_ENV"
  [ -f "${COURSEPILOT_SECRETS_FILE:-}" ] || die "demo.env 指向的配置文件不存在（COURSEPILOT_SECRETS_FILE）"
  # shellcheck disable=SC1090
  . "$COURSEPILOT_SECRETS_FILE"
  set +a
  local missing=() v
  for v in "${REQUIRED_VARS[@]}"; do
    [ -n "${!v:-}" ] || missing+=("$v")
  done
  [ ${#missing[@]} -eq 0 ] || die "配置文件缺少这些变量（只列名字）：${missing[*]}"
  # Java 读 COURSEPILOT_SERVICE_KEY；与网关的 CP_SERVICE_KEY 取同一个值
  export COURSEPILOT_SERVICE_KEY="$CP_SERVICE_KEY"
}

check_prereqs() {
  local t
  for t in curl lsof nohup cloudflared; do
    command -v "$t" >/dev/null 2>&1 || die "找不到命令 $t"
  done
  [ -f "$HOME/.cloudflared/config.yml" ] || die "缺少 ~/.cloudflared/config.yml"
  [ -x "$REPO/.venv/bin/python" ] || die "缺少 $REPO/.venv（先按 agent-runtime/README.md 安装）"
  [ -x "$REPO/web/node_modules/.bin/vite" ] || die "web 依赖未安装：先在 web/ 目录运行 npm ci"
  command -v npm >/dev/null 2>&1 || die "找不到命令 npm（web 生产构建需要）"
  [ -x "$REPO/java-environment/mvnw" ] || die "缺少 java-environment/mvnw"
}

# Java 需要 JDK 21+；优先用系统里已安装的 21 以上版本
pick_java() {
  local home
  home="$(/usr/libexec/java_home -v 21+ 2>/dev/null || true)"
  [ -n "$home" ] || die "未找到 JDK 21+（见 java-environment/README.md）"
  export JAVA_HOME="$home"
}

build_java_if_needed() {
  if [ ! -d "$REPO/java-environment/target/classes" ]; then
    echo "java：首次编译（mvnw compile）..."
    (cd "$REPO/java-environment" && ./mvnw -B -q -DskipTests compile) || die "Java 编译失败"
  fi
}

# ---------- 状态与公网检查 ----------

# 只返回 HTTP 状态码；失败时输出 000
http_code() { curl -s -o /dev/null -w '%{http_code}' "$@" 2>/dev/null || true; }

public_check() {
  local get post i
  for ((i = 0; i < 20; i++)); do
    get="$(http_code --max-time 10 "$PUBLIC_URL/")"
    [ "$get" = 200 ] && break
    sleep 3
  done
  post="$(http_code --max-time 15 -X POST -H 'Content-Type: application/json' -d '{}' "$PUBLIC_URL/api/v1/sessions")"
  echo "公网 GET $PUBLIC_URL/ -> $get"
  echo "公网 POST $PUBLIC_URL/api/v1/sessions -> $post"
  [ "$get" = 200 ] && [ "$post" = 201 ]
}

cmd_start() {
  local caffeinate=0 arg
  for arg in "$@"; do
    case "$arg" in
      --caffeinate) caffeinate=1 ;;
      *) die "start 不认识参数：${arg}（可用：--caffeinate）" ;;
    esac
  done
  load_env
  check_prereqs
  pick_java
  mkdir -p "$LOG_DIR"
  build_java_if_needed

  local name
  for name in "${COMPONENTS[@]}"; do
    if [ -n "$(comp_pids "$name")" ]; then
      echo "${name}：已在运行，跳过"
      continue
    fi
    echo "${name}：启动中..."
    "start_$name"
    echo "${name}：就绪"
  done

  if [ "$caffeinate" = 1 ] && [ -z "$(comp_pids caffeinate)" ]; then
    launch caffeinate "$HOME" caffeinate -i
    echo "caffeinate：已启动（防止空闲睡眠）"
  fi

  echo "本地 http://127.0.0.1:5173 -> $(http_code --noproxy '*' --max-time 10 http://127.0.0.1:5173/)"
  if public_check; then
    echo "公网地址：$PUBLIC_URL/ （检查通过）"
  else
    die "公网检查未通过。隧道刚连接时可能需要几十秒；稍后运行 status 复查。"
  fi
}

stop_one() {
  local name=$1 pids p i
  pids="$(comp_pids "$name")"
  if [ -z "$pids" ]; then
    echo "${name}：未运行"
    rm -f "$LOG_DIR/$name.pid"
    return 0
  fi
  for p in $pids; do kill -TERM "$p" 2>/dev/null || true; done
  for ((i = 0; i < 15; i++)); do
    [ -z "$(comp_pids "$name")" ] && break
    sleep 1
  done
  pids="$(comp_pids "$name")"
  if [ -n "$pids" ]; then
    for p in $pids; do kill -KILL "$p" 2>/dev/null || true; done
    echo "${name}：TERM 后仍在运行，已 KILL"
  else
    echo "${name}：已停止"
  fi
  rm -f "$LOG_DIR/$name.pid"
}

cmd_stop() {
  local name
  for name in "${STOP_ORDER[@]}"; do
    stop_one "$name"
  done
}

cmd_status() {
  local name pids state
  for name in "${COMPONENTS[@]}"; do
    pids="$(comp_pids "$name" | tr '\n' ' ')"
    if [ -z "$pids" ]; then
      echo "${name}：未运行"
      continue
    fi
    case "$name" in
      java) port_up 8081 && state="8081 已监听" || state="启动中" ;;
      api) port_up 8000 && state="8000 已监听" || state="启动中" ;;
      web) port_up 5173 && state="5173 已监听（vite preview）" || state="启动中" ;;
      tunnel) grep -q "Registered tunnel connection" "$LOG_DIR/tunnel.log" 2>/dev/null && state="隧道已连接" || state="进程在，连接未确认" ;;
    esac
    echo "${name}：运行中（PID ${pids% }）· $state"
  done
  if [ -n "$(comp_pids caffeinate)" ]; then
    echo "caffeinate：运行中（防止空闲睡眠）"
  fi
  echo "本地 http://127.0.0.1:5173 -> $(http_code --noproxy '*' --max-time 5 http://127.0.0.1:5173/)"
  echo "公网 $PUBLIC_URL/ -> $(http_code --max-time 10 "$PUBLIC_URL/")（530/1033 表示隧道未连）"
  echo "日志目录：$LOG_DIR"
}

case "${1:-}" in
  start)
    shift
    cmd_start "$@"
    ;;
  stop) cmd_stop ;;
  status) cmd_status ;;
  *)
    usage
    exit 1
    ;;
esac
