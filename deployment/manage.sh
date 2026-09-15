#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
COMPOSE_FILE="$ROOT_DIR/docker-compose.yml"
LOCK_DIR="$ROOT_DIR/.maintenance.lock"
BACKUP_DIR="$ROOT_DIR/backups"

say() {
  printf '%s\n' "$*"
}

fail() {
  printf '错误：%s\n' "$*" >&2
  exit 1
}

compose() {
  docker compose -f "$COMPOSE_FILE" "$@"
}

require_docker() {
  command -v docker >/dev/null 2>&1 || fail "未检测到 Docker。"
  docker compose version >/dev/null 2>&1 || fail "未检测到 Docker Compose v2 插件。"
  docker info >/dev/null 2>&1 || fail "Docker 服务未启动，或当前账号没有 Docker 权限。"
}

acquire_lock() {
  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    fail "已有安装、备份或恢复操作正在执行。"
  fi
  trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT HUP INT TERM
}

container_exists() {
  docker inspect feature-control-center >/dev/null 2>&1
}

container_running() {
  [ "$(docker inspect --format '{{.State.Running}}' feature-control-center 2>/dev/null || true)" = "true" ]
}

wait_for_health() {
  timeout_seconds=${1:-180}
  elapsed=0
  while [ "$elapsed" -lt "$timeout_seconds" ]; do
    state=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' feature-control-center 2>/dev/null || true)
    case "$state" in
      healthy|running) return 0 ;;
      unhealthy|exited|dead) return 1 ;;
    esac
    sleep 3
    elapsed=$((elapsed + 3))
  done
  return 1
}

image_reference() {
  reference=$(compose images -q app 2>/dev/null | sed -n '1p')
  [ -n "$reference" ] || reference=$(docker image inspect feature-control-center:"$(tr -d '[:space:]' < "$ROOT_DIR/VERSION")" --format '{{.Id}}' 2>/dev/null || true)
  [ -n "$reference" ] || fail "未找到系统镜像，请先执行 ./install.sh。"
  printf '%s' "$reference"
}

stop_for_maintenance() {
  WAS_RUNNING=0
  if container_running; then
    WAS_RUNNING=1
    compose stop -t 35 app >/dev/null
  fi
}

resume_after_maintenance() {
  if [ "${WAS_RUNNING:-0}" -eq 1 ]; then
    compose up -d --no-build app >/dev/null
    wait_for_health 180 || fail "维护操作完成，但服务重新启动后未通过健康检查。"
  fi
}

create_backup() {
  label=${1:-manual}
  restart_after=${2:-yes}
  mkdir -p "$BACKUP_DIR"
  chmod 700 "$BACKUP_DIR" 2>/dev/null || true
  [ -d "$ROOT_DIR/data" ] || fail "数据目录不存在。"
  stamp=$(date -u '+%Y%m%dT%H%M%SZ')
  filename="fcc-data-${stamp}-${label}.tar.gz"
  target="$BACKUP_DIR/$filename"
  reference=$(image_reference)
  if [ "$restart_after" = "yes" ]; then
    stop_for_maintenance
  fi
  uid=$(id -u)
  gid=$(id -g)
  if docker info --format '{{json .SecurityOptions}}' 2>/dev/null | grep -q 'name=rootless'; then
    uid=0
    gid=0
  fi
  if ! docker run --rm --entrypoint python \
    -e BACKUP_NAME="$filename" -e HOST_UID="$uid" -e HOST_GID="$gid" \
    -v "$ROOT_DIR/data:/source:ro" -v "$BACKUP_DIR:/backup" \
    "$reference" -c '
import os, pathlib, stat, tarfile
source = pathlib.Path("/source")
target = pathlib.Path("/backup") / os.environ["BACKUP_NAME"]
partial = target.with_name(target.name + ".partial")
partial.unlink(missing_ok=True)
for item in source.rglob("*"):
    mode = item.lstat().st_mode
    if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
        raise SystemExit(f"数据目录含不允许备份的文件类型：{item.relative_to(source)}")
try:
    with tarfile.open(partial, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        for item in sorted(source.iterdir(), key=lambda value: value.name):
            archive.add(item, arcname=item.name, recursive=True)
    os.chmod(partial, 0o600)
    os.chown(partial, int(os.environ["HOST_UID"]), int(os.environ["HOST_GID"]))
    os.replace(partial, target)
finally:
    partial.unlink(missing_ok=True)
'; then
    if [ "$restart_after" = "yes" ]; then
      resume_after_maintenance || true
    fi
    fail "备份创建失败，数据目录没有被修改。"
  fi
  if ! sha256sum "$target" > "$target.sha256"; then
    rm -f "$target" "$target.sha256"
    if [ "$restart_after" = "yes" ]; then
      resume_after_maintenance || true
    fi
    fail "备份校验文件生成失败。"
  fi
  chmod 600 "$target.sha256" 2>/dev/null || true
  if [ "$restart_after" = "yes" ]; then
    resume_after_maintenance
  fi
  printf '%s' "$target"
}

restore_backup() {
  archive=${1:-}
  [ -n "$archive" ] || fail "用法：./manage.sh restore <备份文件.tar.gz>"
  [ -f "$archive" ] || fail "备份文件不存在：$archive"
  archive=$(readlink -f "$archive")
  if [ -f "$archive.sha256" ]; then
    (cd "$(dirname "$archive")" && sha256sum -c "$(basename "$archive").sha256") || fail "备份文件校验失败。"
  else
    fail "找不到配套的 $(basename "$archive").sha256，拒绝恢复未经校验的备份。"
  fi
  say "恢复会停止系统，并以备份内容替换当前 data 目录。"
  printf '请输入 RESTORE 继续：'
  read -r answer
  [ "$answer" = "RESTORE" ] || fail "已取消恢复。"

  reference=$(image_reference)
  stop_for_maintenance
  if ! safety_backup=$(create_backup pre-restore no); then
    resume_after_maintenance || true
    fail "无法创建恢复前安全备份，恢复已终止。"
  fi
  say "当前数据已安全备份到：$safety_backup"

  stamp=$(date -u '+%Y%m%dT%H%M%SZ')
  candidate="$ROOT_DIR/.restore-candidate-$stamp"
  previous="$ROOT_DIR/data.before-restore-$stamp"
  failed="$ROOT_DIR/data.failed-restore-$stamp"
  mkdir -p "$candidate"
  if ! docker run --rm --entrypoint python \
    -v "$archive:/backup/input.tar.gz:ro" -v "$candidate:/candidate" \
    "$reference" -c '
import pathlib, stat, tarfile
target = pathlib.Path("/candidate").resolve()
with tarfile.open("/backup/input.tar.gz", "r:gz") as archive:
    members = archive.getmembers()
    if not members:
        raise SystemExit("备份文件为空")
    for member in members:
        path = pathlib.PurePosixPath(member.name)
        if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
            raise SystemExit(f"备份含不安全路径：{member.name}")
        if member.issym() or member.islnk() or member.isdev() or member.isfifo():
            raise SystemExit(f"备份含不安全文件类型：{member.name}")
    archive.extractall(target, members=members, filter="data")
'; then
    rm -rf "$candidate"
    resume_after_maintenance || true
    fail "备份内容不安全或无法解压，恢复已终止。"
  fi
  if [ ! -f "$candidate/fcc.db" ]; then
    rm -rf "$candidate"
    resume_after_maintenance || true
    fail "备份中缺少 fcc.db，恢复已终止。"
  fi
  if ! docker run --rm --entrypoint python \
    -v "$candidate:/data" "$reference" \
    -m app.preflight --data-dir /data --public-url http://localhost:8080 >/dev/null; then
    rm -rf "$candidate"
    resume_after_maintenance || true
    fail "备份数据未通过应用预检，恢复已终止。"
  fi

  if ! mv "$ROOT_DIR/data" "$previous"; then
    rm -rf "$candidate"
    resume_after_maintenance || true
    fail "无法移动当前数据目录，恢复已终止。"
  fi
  if ! mv "$candidate" "$ROOT_DIR/data"; then
    mv "$previous" "$ROOT_DIR/data" || true
    resume_after_maintenance || true
    fail "无法切换恢复数据，系统已尝试换回原目录。"
  fi
  if compose up -d --no-build app >/dev/null && wait_for_health 180; then
    say "恢复完成。恢复前的数据保留在：$previous"
    say "确认业务无误后，可手工删除该目录。"
    return 0
  fi

  say "新数据未通过启动检查，正在自动恢复原数据……" >&2
  compose stop -t 10 app >/dev/null 2>&1 || true
  mv "$ROOT_DIR/data" "$failed"
  mv "$previous" "$ROOT_DIR/data"
  compose up -d --no-build app >/dev/null
  wait_for_health 180 || fail "自动回退后服务仍未恢复，请保留现场并联系技术支持。"
  fail "恢复失败，系统已回到恢复前状态。失败数据保留在：$failed"
}

usage() {
  cat <<'EOF'
用法：./manage.sh <命令>

  start                 启动系统
  stop                  安全停止系统
  restart               重启系统
  status                查看容器与健康状态
  logs [行数]           查看容器最近日志，默认 200 行
  setup-code            查看尚未使用的首次初始化信息
  backup                停机一致性备份整个业务数据目录
  restore <文件>        校验并恢复备份；失败时自动回退
  admin-access-reset    将配置管理访问限制恢复为仅账户权限
  verify                校验交付包文件完整性
EOF
}

require_docker
cd "$ROOT_DIR"
command=${1:-help}
case "$command" in
  start)
    acquire_lock
    compose up -d --no-build app
    wait_for_health 180 || fail "服务未通过健康检查。"
    say "系统已启动：http://服务器IP:8080"
    ;;
  stop)
    acquire_lock
    compose stop -t 35 app
    ;;
  restart)
    acquire_lock
    compose restart -t 35 app
    wait_for_health 180 || fail "服务未通过健康检查。"
    ;;
  status)
    compose ps
    say "健康状态：$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' feature-control-center 2>/dev/null || printf '未创建')"
    ;;
  logs)
    lines=${2:-200}
    case "$lines" in *[!0-9]*|'') fail "日志行数必须是正整数。" ;; esac
    compose logs --tail="$lines" app
    ;;
  setup-code)
    container_exists || fail "系统尚未安装。"
    compose exec -T -u 0 app sh -c 'test -f /data/first-run.txt && cat /data/first-run.txt' || fail "初始化信息不存在，系统可能已经完成初始化。"
    ;;
  backup)
    acquire_lock
    target=$(create_backup manual yes)
    say "备份完成：$target"
    say "校验文件：$target.sha256"
    ;;
  restore)
    acquire_lock
    restore_backup "${2:-}"
    ;;
  admin-access-reset)
    acquire_lock
    container_exists || fail "系统尚未安装。"
    compose exec -T -u 0 app fccctl --data-dir /data admin-access reset
    ;;
  verify)
    [ -f checksums.sha256 ] || fail "交付包中没有 checksums.sha256。"
    sha256sum -c checksums.sha256
    ;;
  help|-h|--help) usage ;;
  *) usage; fail "未知命令：$command" ;;
esac
