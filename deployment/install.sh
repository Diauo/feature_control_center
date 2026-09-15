#!/usr/bin/env sh
set -eu

PRODUCT_NAME="功能控制中心"
ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
LOCK_DIR="$ROOT_DIR/.install.lock"

say() {
  printf '%s\n' "$*"
}

fail() {
  printf '错误：%s\n' "$*" >&2
  exit 1
}

cleanup() {
  rmdir "$LOCK_DIR" 2>/dev/null || true
}

wait_for_health() {
  timeout_seconds=${1:-240}
  elapsed=0
  while [ "$elapsed" -lt "$timeout_seconds" ]; do
    state=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' feature-control-center 2>/dev/null || true)
    case "$state" in
      healthy|running) return 0 ;;
      unhealthy|exited|dead)
        docker compose -f "$ROOT_DIR/docker-compose.yml" logs --tail=80 app >&2 || true
        return 1
        ;;
    esac
    sleep 3
    elapsed=$((elapsed + 3))
  done
  docker compose -f "$ROOT_DIR/docker-compose.yml" logs --tail=80 app >&2 || true
  return 1
}

[ "$(uname -s 2>/dev/null || true)" = "Linux" ] || fail "一键安装脚本仅支持 Linux 服务器。"
command -v docker >/dev/null 2>&1 || fail "未检测到 Docker。请先按 docs/delivery/01-Linux一键部署.md 安装 Docker Engine。"
docker compose version >/dev/null 2>&1 || fail "未检测到 Docker Compose v2 插件。"
docker info >/dev/null 2>&1 || fail "Docker 服务未启动，或当前账号没有 Docker 权限。"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  fail "已有安装或运维操作正在执行，请稍后再试。"
fi
trap cleanup EXIT HUP INT TERM

cd "$ROOT_DIR"
umask 077
mkdir -p data backups
chmod 700 data backups 2>/dev/null || true

if [ -f checksums.sha256 ]; then
  say "[1/5] 校验交付文件……"
  sha256sum -c checksums.sha256 >/dev/null || fail "交付文件校验失败，请重新获取完整交付包。"
else
  say "[1/5] 未找到 checksums.sha256，跳过交付文件校验。"
fi

case "$(uname -m)" in
  x86_64|amd64) platform="linux-amd64" ;;
  aarch64|arm64) platform="linux-arm64" ;;
  *) fail "不支持的服务器架构：$(uname -m)" ;;
esac

version=$(tr -d '[:space:]' < VERSION)
image_archive="images/feature-control-center-${version}-${platform}.tar"
if [ -f "$image_archive" ]; then
  say "[2/5] 载入离线镜像……"
  docker load -i "$image_archive" >/dev/null
  say "[3/5] 离线镜像已就绪。"
else
  say "[2/5] 交付包未携带 ${platform} 镜像，将从源代码构建。"
  say "[3/5] 构建过程需要服务器可以访问 Docker Hub、GitHub、sqlite.org 和 Python/npm 软件源……"
  docker compose build --pull app
fi

say "[4/5] 启动 Web、Runner 与 Scheduler……"
docker compose up -d --no-build app

say "[5/5] 等待健康检查……"
if ! wait_for_health 240; then
  fail "服务没有通过健康检查。请执行 ./manage.sh logs 查看原因。"
fi

say ""
say "${PRODUCT_NAME}已启动。"
say "访问地址：http://服务器IP:8080"
if docker compose exec -T -u 0 app sh -c 'test -f /data/first-run.txt' >/dev/null 2>&1; then
  say ""
  say "首次初始化信息："
  docker compose exec -T -u 0 app cat /data/first-run.txt
else
  say "现有数据已保留，可直接使用原账号登录。"
fi
say ""
say "常用命令：./manage.sh status | logs | backup | restart"
