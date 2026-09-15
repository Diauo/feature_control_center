#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VERSION=$(tr -d '[:space:]' < "$ROOT_DIR/VERSION")
OUTPUT_DIR=${1:-"$ROOT_DIR/delivery-assets/images"}

fail() {
  printf '错误：%s\n' "$*" >&2
  exit 1
}

[ "$(uname -s 2>/dev/null || true)" = "Linux" ] || fail "镜像封装脚本必须在 Linux 构建机运行。"
command -v docker >/dev/null 2>&1 || fail "未检测到 Docker。"
docker info >/dev/null 2>&1 || fail "Docker 服务不可用。"

case "$(uname -m)" in
  x86_64|amd64) docker_platform="linux/amd64"; artifact_platform="linux-amd64" ;;
  aarch64|arm64) docker_platform="linux/arm64"; artifact_platform="linux-arm64" ;;
  *) fail "不支持的构建机架构：$(uname -m)" ;;
esac

mkdir -p "$OUTPUT_DIR"
archive="$OUTPUT_DIR/feature-control-center-${VERSION}-${artifact_platform}.tar"
image="feature-control-center:${VERSION}"

cd "$ROOT_DIR"
printf '[1/3] 构建 %s……\n' "$image"
docker build --pull --platform "$docker_platform" -t "$image" .

printf '[2/3] 执行容器启动检查……\n'
temporary_data=$(mktemp -d)
container="fcc-delivery-check-$$"
cleanup() {
  docker rm -f "$container" >/dev/null 2>&1 || true
  rm -rf "$temporary_data"
}
trap cleanup EXIT HUP INT TERM
docker run -d --name "$container" -p 127.0.0.1::8080 -v "$temporary_data:/data" "$image" >/dev/null
elapsed=0
while [ "$elapsed" -lt 180 ]; do
  state=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container")
  [ "$state" = "healthy" ] && break
  if [ "$state" = "unhealthy" ] || [ "$state" = "exited" ] || [ "$state" = "dead" ]; then
    docker logs "$container" >&2 || true
    fail "镜像启动检查失败。"
  fi
  sleep 3
  elapsed=$((elapsed + 3))
done
[ "$(docker inspect --format '{{.State.Health.Status}}' "$container")" = "healthy" ] || fail "镜像启动检查超时。"
docker rm -f "$container" >/dev/null
rm -rf "$temporary_data"
trap - EXIT HUP INT TERM

printf '[3/3] 导出离线镜像：%s……\n' "$archive"
docker save -o "$archive" "$image"
sha256sum "$archive" > "$archive.sha256"
printf '完成。请重新运行 tools/build_delivery.py 生成带镜像的离线交付 ZIP。\n'
