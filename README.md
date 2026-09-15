# 功能控制中心

功能控制中心是面向多客户的 Python 功能运行平台。当前版本 `2.1.2` 支持由业务脚本主动提交通用执行结果报表，运行记录可直接核对总数、成功数和失败数，详情页以中文展示逐条结论并导出 XLSX。单次报表明细默认上限为 60000，管理员可在系统设置中调整；平台仍不解释商品模型，也不接管失败项重试。

原项目的 [`features`](./features) 目录保持原样。平台兼容其中的旧式入口，但不会把商品、库存、失败项或网络重试收进平台领域；这些业务规则仍由甲方脚本负责。

## 当前能力

### 账户、客户与安全

- 一次性初始化码创建首个管理员和客户；
- Argon2id 密码哈希、随机不透明服务端会话和持久 Cookie；
- CSRF、Origin、登录限速、闲置/绝对过期、会话数量限制；
- 用户与客户多对多关联，左上角随时切换客户；
- 业务用户与系统管理员分区管理，用户和客户保持多对多关系；
- 审计记录保存操作人角色快照、客户、对象、请求路径、请求 ID、来源 IP、时间和终端信息；
- 配置密钥使用实例派生的 AES-256-GCM 密钥加密，接口只返回“是否已设置”；
- 管理区可以启用“管理员账户 + 可信网络”双门；
- 可信代理按 CIDR 判断，不盲信公网传入的转发头。

### 功能、配置、文件和依赖

- 功能定义、不可变版本、客户功能三层模型；
- ZIP、7z、RAR、TAR、TAR+Gzip、TAR+Bzip2、TAR+XZ 全静态检查，不在 Web 中 import 上传代码；允许格式可在后台勾选；
- 客户配置、客户独立数据源修订和默认文件复制；
- 上传新版本不会静默切换客户当前版本或覆盖客户当前数据源；
- `requirements.txt` 使用独立虚拟环境，相同依赖指纹跨版本复用；
- 功能包可携带 `wheels/*.whl`，可在后台切换离线依赖模式；
- 依赖准备由 Runner 持久消费，上传立即返回 `PREPARING`，不占住 HTTP 请求；
- Linux 共享虚拟环境由 root 持有并向 `fcc-script` 组提供只读执行权限，wheel 缓存不向功能进程开放。

### Runner 和日志

- Web 只创建 SQLite 持久任务，独立 Runner 启动功能子进程；
- 排队时固化功能版本、数据源修订和加密配置快照；
- 默认全局并发 2，同一客户功能最多一个活动任务；
- 可协作停止，超过宽限期后强制终止 POSIX 进程组；
- 可配置功能级和系统默认最长运行时间；
- 每次启动功能进程时注入后台当前选择的 IANA 系统时区，功能代码中的本地时间与调度口径一致；
- Runner 重启把不确定的活动任务标为 `INTERRUPTED`，不自动重试；
- 同时采集 SDK 结构化日志、stdout、stderr 和平台生命周期；
- 功能包可声明通用报表字段，并通过 `ctx.report` 提交成功、失败、无数据、跳过和未完成结果；平台不从日志文本猜测业务状态；
- 运行记录显示报表总数、成功数和失败数，详情页提供中文汇总、逐条原因和业务字段；
- 终态报表可导出含“执行汇总”“结果明细”的 Excel，停止、超时、中断、异常或条数不一致时明确标为“未完整”；
- 日志限长、清理控制字符并批量写入 SQLite；
- 浏览器通过 SSE 实时接收，支持事件序号、断线续传和去重；页面按 50 毫秒窗口批量接收并只渲染最近 2000 条，完整日志仍保存在 SQLite；
- `.log`、`.jsonl` 都从 `run_event` 生成，没有两份可能不一致的最终日志。
- 终态任务的日志默认保留 180 天，由 Runner 自动分批清理；报表明细使用同一保留期，任务摘要和报表汇总不会随明细删除。
- Web、Runner、Scheduler、Launcher 的平台程序日志独立写入 JSONL，默认保留 180 天；磁盘容量上限是可选设置，0 表示不启用。
- 运行记录支持按客户功能、状态、手动/定时、时间范围和 request ID 前缀筛选，不把业务日志误做商品查询。

### Scheduler、快捷复制和后台

- 独立 Scheduler 进程按 SQLite 中的定时任务创建运行请求，不在调度进程中直接执行脚本；
- 日常可选择每天、每周和每月，也支持标准 5 段 Cron；全部任务使用后台配置的 IANA 系统时区；
- `定时任务 ID + 计划时点` 形成持久防重复键，Scheduler 重启或并发接管不会重复入队；
- 离线或延迟超过容差的时点明确记录为“已错过”，不会在恢复后集中补跑；
- 同一客户功能已有活动任务、功能不可用或队列已满时记录跳过原因，不重启业务脚本；
- 管理员可一次复制给多个客户；代码版本共享，但配置、密钥、定时任务、运行日志和来源客户当前数据源都不复制；
- 每个复制目标从功能版本归档内的默认文件建立自己的数据源第 1 版；单个目标失败不会留下半条记录，也不影响其他目标；
- 可折叠侧栏、可搜索的客户与时区下拉框，以及工作台内配置抽屉减少日常跳转；
- 工作台在顶部“已登记功能”汇总卡片提供通用“上传功能包”入口，点击后直接弹出上传窗口；单客户范围自动带入当前客户，全部客户范围要求明确选择目标客户；
- 功能管理可直接提交当前客户的功能并打开实时日志，避免上传与运行之间反复切换页面；
- 系统设置集中展示 Web、Runner、Scheduler 状态、平台版本、程序日志和更新记录。
- 关键保存、上传、运行、停止和下载操作使用统一的右上角状态通知；
- 系统更新位于更新记录之前，展示签名校验、持久进度、执行结果和可用回退。

## 最简单的启动方式

正式交付目标为 Linux Docker Engine + Compose v2。解压交付包后只需：

```bash
chmod +x install.sh manage.sh deployment/*.sh
./install.sh
```

脚本会验证交付文件、载入匹配的离线镜像或从源码构建、启动 Web/Runner/Scheduler、等待健康检查，并直接显示尚未使用的首次初始化信息。不需要 `.env`，也没有必须填写的 Docker 环境变量。

常用运维命令：

```bash
./manage.sh status
./manage.sh logs 200
./manage.sh backup
./manage.sh restart
./manage.sh stop
./manage.sh start
```

`data/` 是唯一持久数据目录。正常停机给 Runner 留出结束功能进程和封存日志的时间；不要使用 `kill -9` 或删除容器目录代替运维命令。完整交付入口见 [`docs/delivery/README.md`](./docs/delivery/README.md)。

## 功能包格式

后台可独立启用或停用以下格式：`.zip`、`.7z`、`.rar`、`.tar`、`.tar.gz` / `.tgz`、`.tar.bz2` / `.tbz2`、`.tar.xz` / `.txz`。正式 Docker 镜像内置校验过摘要的 7-Zip 26.03 以读取 RAR；本地开发机也必须能在 `PATH` 中找到 `7zz`。不接受加密 RAR、多卷 RAR、自解压 RAR、链接和特殊文件。无论格式如何，归档内结构相同：

```text
feature.zip / feature.7z / feature.tar.*
├── __init__.py          # 必须；字面量 __meta__ 与入口函数
├── requirements.txt     # 可选；标准 PyPI requirement
├── dataSource.xlsx      # 可选；由 data_source.filename 声明
├── helpers.py           # 可选；功能自己的模块
└── wheels/              # 可选；离线 wheel
    └── dependency.whl
```

推荐元数据和入口：

```python
__meta__ = {
    "name": "Ozon 库存同步",
    "description": "同步当前客户的数据源内容",
    "entrypoint": "run",
    "configs": {
        "batch_size": {
            "type": "integer",
            "label": "批量大小",
            "required": True,
            "min": 1,
            "max": 1000,
            "default": 100,
        },
        "api_token": {
            "type": "secret",
            "label": "接口密钥",
            "required": True,
        },
    },
    "data_source": {
        "filename": "dataSource.xlsx",
        "required": True,
        "extensions": [".xlsx"],
        "description": "业务人员维护的商品和店铺清单",
    },
}

def run(ctx):
    ctx.log.info("开始同步", requestId=ctx.request_id)
    source_path = ctx.get_data_source_path()
    token = ctx.config.get_secret("api_token")
    batch_size = ctx.config.get("batch_size", 100)

    for item in read_items(source_path):
        ctx.raise_if_cancelled()
        sync_one(item, token)
        ctx.log.info("单项处理完成", sku=item.sku, batchSize=batch_size)
```

SDK 提供：

```text
ctx.request_id
ctx.customer_id
ctx.feature_id
ctx.config.get(key, default)
ctx.config.get_secret(key)
ctx.get_data_source_path()
ctx.log.debug/info/warning/error(message, **context)
ctx.raise_if_cancelled()
```

兼容旧项目：

```python
def run(configs, ctx):
    ctx.log("开始执行")
    return True, "执行成功", {"legacy": "平台不会保存这个返回对象"}
```

旧式 `(bool, message, data)` 只使用布尔值和消息；`data` 不进入平台。平台不提供失败商品表或“重跑失败项”接口。

## 文件入参语义

平台只管理文件，不打开 Excel、CSV 或其他业务格式。功能包通过 `__meta__.data_source.filename` 声明脚本期望的相对路径：

- 首次给客户登记功能时，包内默认文件复制成这个客户自己的第 1 个修订；
- 用户替换文件时，新建不可变修订并切换当前指针；
- A 客户和 B 客户可以共享代码版本，但各自拥有配置和数据源；
- 创建运行记录时固定当前修订 ID；
- Runner 把该修订内容覆盖到元数据声明路径；
- `ctx.get_data_source_path()` 返回同一文件的绝对路径；
- 排队后替换文件只影响下一次运行。

快捷复制不会复制来源客户当前文件。目标客户初始文件的字节来自共享功能版本 ZIP 内的默认数据源，但数据库中会创建目标客户自己的独立修订记录；目标客户之后下载、替换和运行时只访问自己的修订链。

## 定时任务语义

Scheduler 和 Runner 是两个不同进程。Scheduler 的职责只到“到点创建一条 `QUEUED` 运行记录”为止，Runner 才负责物化文件、启动脚本、采集日志和停止进程。因此定时触发与前台点击运行具有相同的运行快照、进程控制和最终日志边界。

- 业务人员可以维护自己已关联客户的定时任务；
- 普通周期由页面生成 Cron，高级用户可以直接填写 5 段 Cron；
- 所有计划时间使用 `system.timezone`，页面按该时区显示下次执行时间；
- 修改系统时区后，Scheduler 从“当前时间”重新计算所有启用任务，不追溯旧时点；
- `scheduler.misfire_grace_seconds` 是允许的到点延迟，默认 60 秒；超过后记一次“已错过”并计算未来时点；
- 系统不做离线补跑、不做平台级失败项重跑，也不替脚本判断某个商品是否应该再次同步。

## 运行、停止和最终日志

任务状态：

```text
QUEUED -> STARTING -> RUNNING -> SUCCEEDED / FAILED
                             -> STOPPING -> STOPPED / TIMED_OUT
                             -> INTERRUPTED
```

点击停止时，Web 只持久化停止意图。Runner 创建取消标记并在 Docker/Linux 中对进程组发送 `SIGTERM`。脚本应在合理的业务边界调用 `ctx.raise_if_cancelled()`；若脚本不配合，宽限期后会收到 `SIGKILL`。

“已停止”只说明本机 Python 进程停止。已经提交到第三方平台的数据不会自动回滚。Runner 也不会自动重试中断任务，因为平台无法证明外部操作幂等。

实时日志页面展示四种来源：

- `SDK`：`ctx.log.*`；
- `STDOUT`：普通 `print`；
- `STDERR`：异常栈或显式错误输出；
- `PLATFORM`：排队、启动、停止、超时和最终状态。

每个任务都有唯一 `request_id` 和连续事件序号。终态只会在输出管道排空后写入。

### 日志保留与自动清理

- 默认保留期是 180 天，可在“系统设置 → Runner 与日志”修改；
- 保留期从任务的 `finished_at` 计算，不从排队时间或单条日志时间计算；
- `0` 表示关闭自动清理，允许范围为 0 到 3650 天；
- 只清理已经进入终态且达到保留期的 `run_event`，不会碰排队中、运行中或停止中的任务；
- 清理后仍保留 request ID、客户、功能版本、数据源修订、最终状态、开始/完成时间和最终事件序号；
- 运行记录会明确标记“日志已清理”，详情页不再提供下载；直接请求下载接口会返回 `410 RUN_LOGS_PURGED`；
- Runner 启动后会立即检查一次，之后通常每小时检查；大量到期记录按小批次删除，避免长时间占有 SQLite 写锁。

SQLite 删除记录后会优先复用释放出来的页，但数据库文件不会保证立刻变小。系统不在业务运行期间自动执行全库 `VACUUM`，因为它可能长时间占锁并需要额外临时磁盘空间；如确需压缩物理文件，应在停止容器并完成备份后由维护人员执行。

## 后台系统设置

以下配置都在页面中保存到 SQLite，无需修改容器环境变量：

- 允许的归档格式、上传、解压和数据源大小边界；
- PyPI 源、依赖命令超时、缓存上限和离线模式；
- Runner 最大并发、队列上限、轮询；
- Runner 心跳、失联判定；
- 停止宽限期；
- 日志批量大小、刷新间隔、消息和上下文上限；
- 运行日志保留天数，默认 180 天，0 表示不自动清理；
- 系统默认最长运行时间；
- 平台程序日志保留天数（默认 180 天）和可选容量上限；
- 签名系统更新包大小上限，默认 500 MiB；
- 系统名称、IANA 时区、会话闲置/绝对期限、敏感操作复验窗口和每用户会话数；
- Scheduler 轮询、心跳、失联判定和错过容差。

功能配置页还可以为某个客户功能单独设置最长运行时间。

## 签名系统更新

“系统设置 → 系统更新”接受扩展名为 `.fcup` 的更新包。它不是普通 ZIP 上传，也不会覆盖正在运行的程序目录：

1. Web 以流式方式接收文件，并检查大小、路径、条目数、解压总量和压缩比；
2. 使用交付包内置的 Ed25519 公钥验证规范化清单签名，再逐一核对所有 wheel 的大小和 SHA-256；
3. 只允许比当前版本新的、明确兼容当前版本、Python 版本和 Linux 架构一致的更新；
4. 管理员输入当前密码后提交安装；有任何排队、运行或停止中的任务时拒绝开始；
5. 容器中的稳定 Launcher 停止 Web、Runner、Scheduler，在新目录离线安装 wheel；安装过程不访问 PyPI；
6. Launcher 使用 SQLite Online Backup API 创建一致性备份并执行完整性检查，再运行数据库迁移和候选版本预检；
7. 新版本的 Web 就绪且 Runner、Scheduler 都产生新鲜心跳后，Launcher 原子切换当前版本指针；
8. 安装、迁移或健康检查失败时，Launcher 自动恢复更新前数据库和程序版本；中途断电时，下次启动先读取恢复标记并保守回退。

更新进度和结果保存在 SQLite 中，浏览器断线或服务重启不会丢失。页面每两秒恢复读取。`data/releases`、`data/backups` 和原始 `.fcup` 都位于持久卷中，因此重建容器不会抹掉业务数据或更新记录。

页面提供的“保留数据回退”与失败时自动回退含义不同：

- **安装失败自动回退**会恢复迁移前数据库，因为候选版本从未对外接管；
- **管理员主动回退**只切换回清单声明兼容的上一程序版本，保留当前 SQLite 数据，不用旧备份覆盖后来产生的业务记录；
- 若数据库迁移不能向后兼容，制作更新包时不得加入 `--rollback-compatible`，页面不会提供主动回退。

### 制作更新包

签名私钥必须保存在开发方的离线受控目录，绝不能复制到源码、Docker 镜像、客户服务器或 `.fcup` 文件。仓库只包含对应公钥。更换信任公钥、Launcher、Python、系统库或 7-Zip 属于**基础镜像升级**，不能通过同一信任边界内的 `.fcup` 自我替换。

首次建立某条发布信任链时，可在隔离机器执行 `fcc-update-package generate-key --private-key /secure/offline/update-signing-private.pem --public-key backend/app/update_public_key.pem`。生成工具拒绝覆盖已有密钥；公钥进入基础交付包，私钥另行离线备份并限制访问。

先构建前端并将静态文件放入 `backend/app/web/static`，再在与正式镜像相同的 Python 3.14 与目标架构下构建应用及所有依赖 wheel，形成完全离线的 wheelhouse。示例：

```bash
cd frontend
npm ci
npm run build
cd ..
rm -rf backend/app/web/static
cp -R frontend/dist backend/app/web/static

python -m build --wheel backend
python -m pip download --only-binary=:all: --dest wheelhouse backend/dist/feature_control_center-2.1.3-py3-none-any.whl

fcc-update-package build \
  --wheelhouse wheelhouse \
  --private-key /secure/offline/update-signing-private.pem \
  --output feature-control-center-2.1.3-linux-x86_64.fcup \
  --version 2.1.3 \
  --compatible-from '>=2.1.2,<3.0.0' \
  --platform linux_x86_64 \
  --python-version 3.14 \
  --database-revision 0010_report_limit \
  --notes-file release-notes.txt \
  --rollback-compatible
```

`wheelhouse` 必须且只能包含一个目标版本的 `feature-control-center` wheel，并包含其全部间接依赖的兼容 wheel。生成工具不会覆盖已有文件。上传前应在同架构的全新交付容器副本上完成一次升级和回退演练。
上面是从本版 `2.1.2` 制作后续版 `2.1.3` 的发布示例；制作实际版本时，必须同步替换 wheel 文件名、`--output`、`--version`、`--compatible-from` 和 `--database-revision`，不得直接照抄版本号。

## 登录状态为何可以保存

浏览器保存高强度随机、`HttpOnly` 会话 Cookie；SQLite `session` 表保存 HMAC 摘要、闲置期限、绝对期限和吊销状态。页面刷新、浏览器重开、容器重启或重新构建镜像不会无故丢失登录。

以下情况会要求重新登录：超时、用户停用或权限变化、密码修改、管理员强制下线、Cookie 被删除、域名/HTTP/HTTPS 边界变化，或数据库与 `instance.key` 不配套。

`localStorage` 只记录最后选择的客户 ID，不保存会话 Token、密码或密钥。

## 数据、迁移和备份

```text
data/
├── fcc.db
├── fcc.db-wal          # 运行时可能存在
├── fcc.db-shm          # 运行时可能存在
├── instance.key        # 必须与数据库一起备份
├── first-run.txt       # 仅未初始化时存在
├── runtime-cache/      # 可复用 Python 环境
├── system-logs/        # Web、Runner、Scheduler、Launcher 每日 JSONL
├── updates/             # 原始更新包、Launcher 心跳和待执行请求
├── releases/            # 已验证并安装的平台版本及当前版本指针
├── backups/             # 更新前 SQLite 一致性备份与中断恢复标记
└── tmp/runs/            # 运行中一次性工作目录
```

迁移机器时先停止容器，再复制**整个 `data` 目录**。不能只复制 `fcc.db`；丢失 `instance.key` 会使现有会话、配置密钥和运行快照不可解密。运行中直接复制单个 SQLite 文件也可能遗漏 WAL 内容。

应用启动自动执行 Alembic。业务代码不能用 `create_all()` 绕开迁移。

## 公网与脚本隔离边界

默认 `LAN_HTTP` 只用于局域网验收。公网必须由反向代理终止 HTTPS，再切换 `PUBLIC_HTTPS` 并登记可信代理/管理网络。

正式容器有三个进程身份：启动器/Runner、`fcc` Web、`fcc-script` 功能脚本。脚本用户不能读取数据库、实例密钥或其他任务目录；子进程也不继承 Web/Runner 的任意环境变量。Runner 本身不监听网络。

这不是任意恶意代码的虚拟机沙箱。功能脚本必须访问业务网络，无法统一禁网；上传功能仍是管理员级高风险操作。系统的目标是限制误操作和入侵后的横向读取面，而不是声称在同一容器内安全执行完全不可信代码。

## 本地开发

后端要求 Python 3.13+。正式镜像固定 Python 3.14.4 和 SQLite 3.53.4。

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".\backend[test]"

# 终端 1
.\.venv\Scripts\fcc-web --data-dir .\data --host 127.0.0.1 --port 8080

# 终端 2
.\.venv\Scripts\fcc-runner --data-dir .\data

# 终端 3
.\.venv\Scripts\fcc-scheduler --data-dir .\data
```

Windows 本地开发没有 Linux UID 隔离，正式隔离边界以 Docker/Linux 为准。

前端：

```powershell
cd frontend
npm ci
npm run dev
```

## 主要接口

```text
POST /api/customer-features/{id}/runs
POST /api/runs/{request_id}/stop
GET  /api/runs?customerId={id}&customerFeatureId=&status=&triggerSource=&queuedFrom=&queuedTo=&requestId=
GET  /api/runs/{request_id}
GET  /api/runs/{request_id}/events?after={sequence}
GET  /api/runs/{request_id}/events/stream
GET  /api/runs/{request_id}/log.log
GET  /api/runs/{request_id}/log.jsonl
GET  /api/schedules?customerId={id}
POST /api/schedules
PUT  /api/schedules/{id}
DELETE /api/schedules/{id}
POST /api/admin/customer-features/{id}/copy
GET  /api/admin/system/updates
POST /api/admin/system/updates/packages
POST /api/admin/system/updates/{id}/apply
POST /api/admin/system/updates/rollback
```

## 尚未实现

- 高可用和多 Runner 集群；
- 任何平台级失败商品或失败项重跑。

阶段 E 的部署、备份恢复、功能开发和验收文档见 [`docs/delivery/README.md`](./docs/delivery/README.md)。阶段 D 的实现与边界见 [`docs/implementation/phase-d.md`](./docs/implementation/phase-d.md)。Runner 状态语义仍见 [`docs/implementation/phase-c.md`](./docs/implementation/phase-c.md)，日志保留补充说明见 [`docs/implementation/0.0.9-log-retention.md`](./docs/implementation/0.0.9-log-retention.md)。
