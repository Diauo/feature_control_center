# Linux 一键部署

## 1. 适用范围

部署目标为单台 Linux 服务器。系统以一个 Docker 容器运行 Web、Runner 和 Scheduler，以宿主机 `data/` 目录保存全部业务数据。不要把同一份 `data/` 同时挂载给两套运行中的系统。

推荐基线：

- Ubuntu 24.04 LTS、Debian 12 或同等维护状态的 x86_64/arm64 Linux；
- 2 核 CPU、4 GiB 内存、10 GiB 可用磁盘起步；
- Docker Engine 26 或更高版本，Docker Compose v2；
- 服务器时间同步正常；
- 对外入口由 HTTPS 反向代理提供，8080 端口不直接暴露到全网。

实际磁盘容量按功能包、依赖、数据源、日志保留天数和更新回退数量评估。OZON/pandas 依赖会明显增加运行环境缓存。

## 2. 部署前检查

```bash
uname -a
date
docker version
docker compose version
docker info
```

如果 `docker info` 失败，先由服务器管理员安装并启动 Docker。交付脚本不会擅自修改 Linux 软件源、防火墙或 Docker 守护进程配置，这是为了避免在未知发行版上造成不可逆的主机变更。

## 3. 解压与校验

```bash
mkdir -p /opt/feature-control-center
cd /opt/feature-control-center
unzip /交付包所在路径/功能控制中心-2.1.2-交付包.zip
cd 功能控制中心-2.1.2
chmod +x install.sh manage.sh deployment/*.sh
sha256sum -c checksums.sha256
```

校验必须全部显示 `OK`。任意一项失败，都应停止部署并重新取得交付包。

## 4. 一键安装

```bash
./install.sh
```

安装脚本是幂等的：重复执行不会清空 `data/`。脚本依次完成：

1. 检查 Linux、Docker 和 Compose；
2. 校验交付文件；
3. 识别 x86_64 或 arm64；
4. 优先载入匹配的离线镜像，没有镜像时从源代码构建；
5. 启动容器并等待健康检查；
6. 首次安装时输出 `/setup` 地址和一次性验证码。

如果终端输出初始化信息，应立即保存并完成初始化。验证码使用后失效。之后可用下列命令再次查看尚未使用的初始化信息：

```bash
./manage.sh setup-code
```

## 5. 访问与端口

默认监听宿主机 `8080`：

```text
http://服务器IP:8080
```

正式公网部署应使用 `https://业务域名`，由 Nginx、Caddy 或公司的现有网关反向代理到 `127.0.0.1:8080`。如果反向代理与容器不在同一台主机，应通过防火墙只允许代理节点访问 8080。

## 6. 安装后检查

```bash
./manage.sh status
curl --fail http://127.0.0.1:8080/api/health/live
./manage.sh logs 100
```

浏览器进入系统设置，确认：

- Web、Runner、Scheduler 状态正常；
- 系统时区正确；
- 任务日志与程序日志保留天数符合项目要求；
- 允许的功能包格式符合实际使用；
- 配置管理访问限制在 HTTPS 和代理配置完成后再开启。

容器服务和平台程序日志以 UTC 作为稳定基线。功能任务启动时会自动读取后台“系统时区”并注入自己的进程，不需要也不应在 `docker-compose.yml` 里另写固定地区时区。

## 7. 日常命令

```bash
./manage.sh status
./manage.sh logs 200
./manage.sh restart
./manage.sh stop
./manage.sh start
./manage.sh backup
```

不要用 `kill -9` 代替 `manage.sh stop`。正常停止给 Runner 留出终止脚本和封存日志的时间。

## 8. 迁移旧数据

不要直接复制运行中的 `fcc.db`。应在旧服务器执行 `./manage.sh backup`，把 `.tar.gz` 和 `.sha256` 一起传到新服务器，完成空系统安装后再执行：

```bash
./manage.sh restore /安全路径/fcc-data-时间-manual.tar.gz
```

完整流程见 `05-备份恢复与迁移.md`。

## 9. 卸载边界

停止并删除容器：

```bash
docker compose down
```

该命令不删除宿主机 `data/`。只有在已取得可恢复备份且书面确认不再保留数据时，才能手工删除 `data/` 和 `backups/`。交付脚本故意不提供“一键清空”命令。
