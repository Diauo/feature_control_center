# 阶段 C 实现说明：Runner 和实时日志

版本：`0.0.8`  
架构基线：[`docs/architecture/0.0.5-system-design.md`](../architecture/0.0.5-system-design.md)

## 1. 本阶段闭环

阶段 C 把“点击运行”落实为持久任务，而不是由 Flask 请求线程临时持有一个 `subprocess.Popen`：

1. Web 在一个短事务内校验权限和运行条件；
2. 固化功能版本、客户数据源修订、配置值和密钥键名；
3. 配置快照用独立用途的 AES-256-GCM 密钥加密后写入 SQLite；
4. 创建 `QUEUED` 运行记录并立即向浏览器返回 `request_id`；
5. 独立 Runner 领取任务、准备一次性工作目录并启动功能子进程；
6. SDK、stdout、stderr 和平台事件按批次写入 `run_event`；
7. 前端通过 SSE 按事件序号实时消费，并可断线续传；
8. 子进程退出且输出管道排空后，Runner 才封存最终状态；
9. `.log` 和 `.jsonl` 都从同一组 `run_event` 即时生成。

平台仍然不解释商品、库存和网络重试，也不从自由文本日志推断成功或失败。`1.1.0` 起，业务脚本可以通过通用 `ctx.report` 契约明确提交逐条结果；状态判定和业务补偿仍由脚本负责。

## 2. 为什么 Web 和 Runner 必须分开

HTTP 请求有代理超时、浏览器断开、Web 线程池耗尽和 Web 进程重启等生命周期。把功能进程句柄存在 Flask 内存里，会在任何一个生命周期变化后失去停止能力。

当前实现将 SQLite 作为小规模持久队列：Web 只写 `QUEUED` 和停止请求；Runner 是活动状态和终态的唯一执行者。上传新功能的依赖准备也从 Web 请求迁到 Runner 后台线程，上传接口会快速返回 `PREPARING`。这样既没有引入 Redis、RabbitMQ 等新服务，又避免了 Web 内临时线程造成的任务丢失。

系统只允许一个健康 Runner 持有执行权。`runner_heartbeat` 保存进程、实例令牌和心跳；第二个健康实例会拒绝启动。默认全局并发是 2，同一客户功能由数据库部分唯一索引保证最多存在一个活动任务。

## 3. 运行快照

`POST /api/customer-features/{id}/runs` 在同一数据库事务内固定：

- `customer_id`；
- `customer_feature_id`；
- `feature_version_id`；
- `data_source_revision_id`；
- 配置普通值与解密后的密钥值；
- 密钥配置键名；
- 功能级或系统默认最长运行时间。

配置快照不会通过 HTTP 返回。密文 AAD 绑定 `request_id`，不能把一个任务的密文替换到另一个任务。Runner 只读取上述快照，不在执行途中追随客户功能的“当前版本”“当前数据源”或“当前配置”。因此用户排队后替换文件或配置，只会影响下一次任务。

## 4. 状态机与恢复

支持的状态为：

```text
QUEUED -> STARTING -> RUNNING -> SUCCEEDED
                             -> FAILED
                             -> STOPPING -> STOPPED
                             -> STOPPING -> TIMED_OUT
                             -> INTERRUPTED
```

- Web 创建 `QUEUED`；
- Web 收到停止操作时只写 `stop_requested_at`、`stop_reason=USER_REQUEST` 和 `STOPPING`；
- Runner 负责启动、信号、强制终止和所有终态；
- 终态不会被后续停止请求改写；
- Runner 启动时把遗留的 `STARTING/RUNNING/已领取 STOPPING` 标为 `INTERRUPTED`，保留已有日志且不自动重试；
- 尚未启动的排队任务若被停止，Runner 直接封存为 `STOPPED`，不导入功能代码。

不自动重试是有意选择。同步脚本可能对外部系统产生不可逆副作用，平台无法证明重复执行是幂等的。

## 5. 停止语义

停止分两段：

1. Runner 创建取消标记，并向 POSIX 进程组发送 `SIGTERM`；SDK 的信号处理器将其转换为协作取消，脚本应在批次或单项边界调用 `ctx.raise_if_cancelled()`；
2. 超过后台配置的宽限期仍未退出时，Runner 对整个进程组发送 `SIGKILL`。

容器内功能进程使用独立会话/进程组。甲方已确认现有脚本不会自行创建子进程，但进程组终止仍作为防御边界。Windows 本地开发使用可用的进程终止能力；正式 Docker/Linux 交付才具有完整的 TERM/KILL 两段语义。

“已停止”只表示本机功能进程不再执行。已经提交给外部平台的库存或订单变更不会自动回滚，平台也不会伪造业务事务。

## 6. SDK 与兼容层

推荐入口：

```python
def run(ctx):
    ctx.log.info("开始同步", batch="A-01")
    source = ctx.get_data_source_path()
    token = ctx.config.get_secret("api_token")

    for row in load_rows(source):
        ctx.raise_if_cancelled()
        sync_one(row, token)
        ctx.log.info("商品处理完成", sku=row.sku)
```

稳定能力：

- `ctx.request_id`、`ctx.customer_id`、`ctx.feature_id`；
- `ctx.config.get(key, default)`；
- `ctx.config.get_secret(key)`；
- `ctx.get_data_source_path()`；
- `ctx.log.debug/info/warning/error(message, **context)`；
- `ctx.report.start/success/failed/no_data/skipped/unfinished/complete()`；
- `ctx.raise_if_cancelled()`。

数据源会覆盖到元数据声明的包内相对路径，同时 `get_data_source_path()` 返回该绝对路径。脚本仍决定文件格式和读取方式。

兼容原项目的 `run(configs, ctx)`、`ctx.log(message, level)` 以及旧的 `FeatureExecutionContext` 类型导入。旧入口返回 `(bool, message, data)` 时，Runner 只使用布尔值和消息确定进程成功/失败，不记录返回数据，避免把不受控的大对象或密钥写入平台。新脚本不应依赖这个兼容返回值。

SDK 不提供商品模型、业务状态枚举映射或失败项重试 API。`ctx.report` 只接收功能包声明的通用字段和五种平台展示状态，不参与业务判断。

## 7. 日志模型

每条 `run_event` 包含：

- `request_id`；
- 单任务严格递增的 `sequence`；
- 毫秒时间戳；
- `DEBUG/INFO/WARNING/ERROR`；
- `PLATFORM/SDK/STDOUT/STDERR`；
- 文本消息；
- JSON 上下文。

Runner 限制单条消息和上下文大小，移除不适合持久日志的控制字符，并按条数或时间窗口批量提交。大而不换行的 stdout/stderr 也采用有限长度读取，不会无限增长内存。

SSE 使用事件 `id` 对应 `sequence`，支持浏览器 `Last-Event-ID` 和显式 `after` 游标。每轮读取都使用短数据库会话，不在一个长连接中占有 SQLite 事务。终态事件在 stdout/stderr 读取线程结束、待写批次刷新后才生成。

## 8. 进程与文件安全

功能 ZIP 在上传时静态验证，执行前再次校验包 SHA-256，并在一次性目录中拒绝路径穿越和符号链接。数据源修订也再次校验 SHA-256。

正式镜像中：

- Web 使用 `fcc`（UID 10001）；
- Runner 只在无网络监听的后台以 root 启动，并仅保留文件权限调整、降权和终止进程所需 capability；
- 功能子进程在启动前切换到 `fcc-script`（UID 10002），清空附加组并设置 `no_new_privs`；
- 共享虚拟环境由 root 持有，`fcc-script` 只有读取和执行权限；共享 wheel 缓存仍为 root 私有；
- `/data/tmp/runs` 由 root 持有，只向 `fcc-script` 组开放穿越权限，不允许功能进程枚举或写入父目录；
- `fcc-script` 不能读取 `fcc.db`、`instance.key` 或其他任务的 `0700` 工作目录；
- 子进程只继承最小环境变量和经过校验的系统时区，不继承 Web/Runner 的任意宿主环境；
- 明文运行配置只存在于该任务目录，结束后整个目录删除。

这是一道面向可信管理员上传代码的强隔离边界，不是对恶意代码的完整虚拟机沙箱。脚本必须联网同步业务，因而不能统一禁网；获得管理员上传权限的人仍可能上传会访问网络或消耗资源的代码。公网部署必须继续保护管理员账户、管理区网络门和 HTTPS。

## 9. 数据表和接口

新增表：

- `run`：快照、状态机、进程控制和最终状态；
- `run_event`：唯一事实日志；
- `run_report`：一次运行的报表声明、完整性和汇总计数；
- `run_report_item`：脚本逐条提交的业务结果；
- `runner_heartbeat`：单 Runner 执行权和健康信息。

新增接口：

```text
POST /api/customer-features/{id}/runs
POST /api/runs/{request_id}/stop
GET  /api/runs?customerId={id}
GET  /api/runs/{request_id}
GET  /api/runs/{request_id}/events?after={sequence}
GET  /api/runs/{request_id}/events/stream
GET  /api/runs/{request_id}/log.log
GET  /api/runs/{request_id}/log.jsonl
GET  /api/runs/{request_id}/report
GET  /api/runs/{request_id}/report/items
GET  /api/runs/{request_id}/report.xlsx
```

所有接口继续使用服务端会话。创建和停止需要 CSRF；读取、SSE 和下载都逐任务校验用户与客户的关联关系。已停用客户的历史日志仍可由原有授权关系查看，但不能创建新任务。

## 10. 后台设置

Runner 参数保存在 `system_setting`，不要求甲方编辑 Docker 环境变量：并发数、队列上限、轮询、心跳、失联判定、停止宽限期、日志批量、日志刷新间隔、消息/上下文上限和系统默认超时都可以在“系统设置”修改。功能配置页可以覆盖该功能的最长运行时间。

## 11. 当前不包含

- 从任意日志自动识别失败商品，或由平台重跑失败项；
- 业务网络重试；
- 功能快捷复制；
- 定时任务和错过触发策略；
- 完整日志筛选；
- 在线备份恢复；
- 高可用或多 Runner 集群。

快捷复制与定时任务属于后续阶段。复制时目标客户仍必须从功能版本的默认数据源建立自己的修订，不能复制来源客户当前数据源。

> `0.0.9` 补充：终态任务日志现已支持默认 180 天、后台可配置的自动保留和分批清理。实现和边界见 [`0.0.9-log-retention.md`](./0.0.9-log-retention.md)。

> `1.0.2` 补充：运行详情使用 50 毫秒接收窗口合并 SSE 日志更新，浏览器只保留最近 2000 条可见记录。被省略的历史记录没有从数据库删除，`.log` 与 `.jsonl` 下载仍包含保留期内的完整日志。终态页面会从最后 2000 条附近开始读取，避免恢复历史任务时创建无上限 DOM。

> `1.1.0` 补充：功能包可在 `__meta__.report` 声明 1—30 个通用业务字段。Runner 通过原有带随机令牌的子进程事件通道接收 `report.start`、`report.item` 和 `report.complete`，服务端再次校验字段、类型、数量和长度后写入独立报表表；结构化报表不会混入 `run_event`，因此日志实时性和既有 SSE 游标语义不变。入口函数正常返回时 SDK 自动发出完成标记；停止、超时、中断、异常、数量不一致或校验失败会使报表封存为 `INCOMPLETE`。报表明细与运行日志共用保留期限并同步清理，`run_report` 汇总继续保留。Excel 下载逐任务校验客户权限并记录审计，文本单元格防止公式注入。

## 12. 验证结果

- 后端：23 项测试全部通过；覆盖率 70%；
- 前端：5 项单元测试全部通过；
- TypeScript：`vue-tsc` 与 `tsc` 通过；
- 前端生产构建：Vite 构建通过并同步到 Flask 静态目录；
- Docker：当前开发机没有 Docker CLI，Linux 镜像、UID 降权和真实 POSIX 信号仍需在交付验收机做镜像级冒烟。
