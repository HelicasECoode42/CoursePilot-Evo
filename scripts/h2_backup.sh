#!/usr/bin/env bash
# H2 文件库的离线备份与恢复（模块 B 的存储）。
#
#   scripts/h2_backup.sh backup              复制一份到备份目录（时间戳命名，保留最近 N 份）
#   scripts/h2_backup.sh restore <备份文件>  用备份覆盖当前库（原库先挪到 *.before-restore-时间戳）
#
# 安全约束：
# - 只做离线复制。Java 服务在端口上监听时（即库可能正被写入），两个子命令都拒绝执行，
#   不做"看起来能用"的热拷贝。先停服务再备份/恢复。
# - 备份文件与目录一律 600 / 700，不进仓库（data/ 已被 .gitignore 覆盖）。
# - 不打印数据内容，只打印路径、大小、结果。
#
# 可覆盖的环境变量（测试或换路径用）：
#   CP_H2_DB_FILE       库文件，默认 java-environment/data/coursepilot.mv.db
#   CP_H2_BACKUP_DIR    备份目录，默认 data/private/backups
#   CP_H2_BACKUP_KEEP   保留份数，默认 14
#   CP_JAVA_PORT        Java 服务端口，默认 8081
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_FILE="${CP_H2_DB_FILE:-$ROOT/java-environment/data/coursepilot.mv.db}"
BACKUP_DIR="${CP_H2_BACKUP_DIR:-$ROOT/data/private/backups}"
KEEP="${CP_H2_BACKUP_KEEP:-14}"
JAVA_PORT="${CP_JAVA_PORT:-8081}"

die() { echo "h2_backup: $*" >&2; exit 1; }

java_listening() {
  command -v lsof >/dev/null 2>&1 || die "需要 lsof 来判断 Java 服务是否在运行"
  lsof -nP -iTCP:"$JAVA_PORT" -sTCP:LISTEN >/dev/null 2>&1
}

require_java_stopped() {
  if java_listening; then
    die "端口 $JAVA_PORT 仍在监听（Java 服务在运行），拒绝操作。请先停止服务再重试。"
  fi
}

timestamp() { date +%Y%m%d-%H%M%S; }

cmd_backup() {
  [ -f "$DB_FILE" ] || die "库文件不存在：$DB_FILE"
  require_java_stopped

  umask 077
  mkdir -p "$BACKUP_DIR"
  chmod 700 "$BACKUP_DIR"

  local ts dest tmp
  ts="$(timestamp)"
  dest="$BACKUP_DIR/coursepilot-$ts.mv.db"
  [ ! -e "$dest" ] || die "备份文件已存在（同一秒内重复运行？）：$dest"
  tmp="$dest.tmp"

  cp "$DB_FILE" "$tmp"
  chmod 600 "$tmp"
  cmp -s "$DB_FILE" "$tmp" || { rm -f "$tmp"; die "复制校验失败，已删除不完整的副本"; }
  mv "$tmp" "$dest"

  # 只保留最近 KEEP 份（文件名含时间戳，字典序即时间序）。
  local old
  old="$(ls -1 "$BACKUP_DIR"/coursepilot-*.mv.db 2>/dev/null | sort -r | tail -n +$((KEEP + 1)) || true)"
  if [ -n "$old" ]; then
    while IFS= read -r f; do rm -f -- "$f"; done <<< "$old"
  fi

  echo "备份完成：$dest（$(wc -c < "$dest" | tr -d ' ') 字节，保留最近 $KEEP 份）"
}

cmd_restore() {
  local src="${1:-}"
  [ -n "$src" ] || die "用法：restore <备份文件>"
  [ -f "$src" ] || die "备份文件不存在：$src"
  # MVStore 文件头以 "H:" 开头；不是 H2 文件就不覆盖。
  [ "$(head -c 2 "$src")" = "H:" ] || die "不是 H2 MVStore 文件：$src"
  require_java_stopped

  umask 077
  mkdir -p "$(dirname "$DB_FILE")"
  if [ -f "$DB_FILE" ]; then
    local keep="$DB_FILE.before-restore-$(timestamp)"
    mv "$DB_FILE" "$keep"
    chmod 600 "$keep"
    echo "原库已保存为：$keep"
  fi

  cp "$src" "$DB_FILE.tmp"
  chmod 600 "$DB_FILE.tmp"
  mv "$DB_FILE.tmp" "$DB_FILE"
  echo "恢复完成：$DB_FILE（来自 $src）"
}

case "${1:-}" in
  backup) cmd_backup ;;
  restore) shift; cmd_restore "${1:-}" ;;
  *) die "用法：$0 backup | restore <备份文件>" ;;
esac
