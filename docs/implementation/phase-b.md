# 阶段 B 实现说明：功能、配置和数据源

版本：`0.0.7`  
架构基线：[`docs/architecture/0.0.5-system-design.md`](../architecture/0.0.5-system-design.md)

## 1. 阶段边界

本阶段建立“什么代码、属于哪个客户、用哪份配置和数据源、依赖是否准备完成”的闭环。系统仍不启动业务脚本。可停止子进程、运行快照、实时日志和最终日志属于阶段 C；快捷复制与定时任务属于阶段 D。

平台没有商品模型、失败项模型或失败项重跑接口。数据源对平台始终是不透明字节，业务列、库存含义与脚本内部重试都由功能作者负责。

## 2. 功能的三层模型

| 模型 | 是否可变 | 作用 |
| --- | --- | --- |
| `feature_definition` | 名称身份稳定 | 表示“同一个功能” |
| `feature_version` | 不可变 | 保存 ZIP、元数据、配置/数据源 schema、依赖环境和校验摘要 |
| `customer_feature` | 可变指针 | 表示某客户当前使用的版本、启用状态、独立配置和数据源 |

同名功能包会产生同一定义下的新版本；同一包内容不能重复登记。上传新版本不会让已有客户静默升级。管理员需要明确选择“用于当前客户”。这避免业务人员上传测试包后直接影响正在使用的客户。

## 3. 静态包检查

`FeaturePackageInspector` 全程使用 `zipfile`、`ast.parse` 和 `ast.literal_eval`：

1. 限制压缩包字节数、条目数、单条目大小、解压总量和压缩比；
2. 拒绝绝对路径、`..`、反斜杠、NUL、Unicode 归一化歧义、盘符、重复/大小写冲突路径；
3. 拒绝符号链接和加密 ZIP；
4. 校验 CRC；
5. 要求根目录 `__init__.py`；
6. 只读取一次字面量 `__meta__`，确认入口函数在顶层声明；
7. 不 import 模块，因此上传包中的顶层网络请求、文件操作和异常都不会执行；
8. `requirements.txt` 只接受规范 requirement，拒绝 pip 参数、URL、VCS 和本地路径。

兼容旧包的 `configs: {key: (default, description)}` 形式以及 `dataSource.*` 推断。旧 `customer` 字段被忽略并生成警告，因为归属必须由管理员在平台上选择。疑似密钥的旧默认值会被丢弃，避免把包内明文迁入数据库。

## 4. 客户配置

支持 `string`、`text`、`integer`、`number`、`boolean`、`enum` 和 `secret`。包登记时与用户保存时使用同一套类型、枚举和范围规则。

普通值以 JSON 保存。`secret` 使用 AES-256-GCM 加密：

- 加密密钥从 `instance.key` 按独立用途派生；
- 每次写入使用随机 96 位 nonce；
- AAD 绑定 `customer_feature_id + config_key`，密文不能被换到另一个客户功能或配置键；
- 查询接口只返回 `isSet`，从不返回密钥明文；
- 审计只记录变更键名，不记录值；
- 修改配置必须是管理员、通过管理区网络门且在重新认证有效期内。

内部 `capture_execution_inputs` 已能解析配置并捕获版本 ID、数据源版本 ID，为阶段 C 在创建运行记录时固化快照准备边界；当前没有把解密接口暴露给 HTTP。

## 5. 客户独立数据源

默认文件属于不可变 `feature_version`。首次给客户登记功能时，系统把默认文件的内容复制进该客户自己的 `customer_feature_data_source_revision` 第 1 版。此后：

- 下载只读取客户功能的当前版本；
- 替换创建新的不可变版本并原子切换当前指针；
- 旧版本保留，便于阶段 C 的运行快照和后续审计；
- 文件扩展名按元数据允许列表检查，平台不打开或改写文件；
- 新代码版本默认保留客户当前文件；格式不兼容时要求管理员明确使用新版默认文件，否则拒绝切换。

所以 A 客户和 B 客户可以共享同一代码版本，但不会共享可变数据源。阶段 D 快捷复制必须复用同一原则：目标客户从 ZIP 默认文件创建自己的第 1 版，绝不能复制来源客户当前文件。

## 6. 依赖环境

存在 `requirements.txt` 时，系统以“Python 主次版本 + 运行平台标签 + 规范依赖文本 + 包内 wheel 摘要”计算请求指纹。相同指纹复用同一 `runtime_environment`，跨功能版本和客户不重复安装；不同 CPU/操作系统不会误用同一二进制环境。

真实构建器：

1. 在 `/data/runtime-cache/environments/<fingerprint>` 创建独立 venv；
2. 用 venv 自身的 pip 下载二进制 wheel；
3. 再用 `--no-index --find-links` 从已解析 wheelhouse 安装；
4. 执行 `pip check`；
5. 保存 `pip freeze --all`、wheel SHA-256 清单和解析指纹；
6. 成功后才把数据库状态置为 `READY`，失败则记录受限长度摘要并允许管理员重试。

Linux 正式环境在第 5 步完成后才发布权限：虚拟环境及内部目录、文件统一保持 `root:fcc-script`，目录只读可穿越，可执行文件保留组执行权限，普通文件只向组开放读取。`fcc-script` 不拥有共享环境，也没有组写权限。全局 `wheels` 缓存保持 `root:root 0700`，功能进程不能读取或修改。Launcher 每次启动都会按同一规则修复旧版本遗留权限；遇到异常文件类型或顶层符号链接时停止启动，避免 root 跟随不可信路径。

离线模式只使用 ZIP 的 `wheels/`。环境准备不会修改平台 Python，不会在脚本运行到 `ModuleNotFoundError` 后临时安装。操作系统动态库不是 Python 包问题；需要新增系统包时必须构建新镜像。

当前缓存上限用于阻止单次解析超过配置容量，不主动删除已建环境，避免把未来正在运行的脚本环境删掉。安全的引用计数和清理策略应在阶段 C 有运行引用后实现。

阶段 B 暂时在管理员上传/重试请求中、数据库事务之外同步执行依赖准备。这保证失败状态和数据库提交边界真实可用，但依赖下载很慢时 HTTP 请求可能超过外部反向代理的等待时间。阶段 C 接入持久 Runner 队列时，必须把同一构建器迁到 Runner 消费，并让上传接口在登记后立即返回 `PREPARING`；不能用 Web 进程内临时线程冒充可靠队列。这个过渡边界不影响环境指纹、缓存或失败重试数据模型。

## 7. 管理区网络门

网络门有两种模式：

- `ACCOUNT_ONLY`：只依赖现有管理员权限；
- `TRUSTED_NETWORKS`：管理员权限之外，解析后的客户端 IP 还必须属于登记 CIDR。

用户、客户、功能、配置、审计和系统设置接口统一受网络门保护。判断不写死 RFC1918：公司可能通过公网出口、VPN、IPv6 或反向代理访问，真实边界必须由部署方登记。

`X-Forwarded-For` 只有在直接对端属于可信代理时才生效。设置页显示实际客户端 IP 和 `/32` 或 `/128` 建议值；启用网络门时后端确认当前地址仍在新列表内。可信代理和网络门不能首次同时改动，防止地址解释变化导致自锁。主机侧 `fccctl admin-access reset` 是最后恢复通道，没有公网绕过 API。

## 8. SQLite 与可移植性

ZIP、默认数据源、客户数据源版本、配置密文和所有元数据都保存在 `fcc.db`。`runtime-cache` 可丢弃重建，不是业务数据的唯一副本。迁移仍必须同时复制数据库和 `instance.key`，否则会话摘要绑定和配置密文都无法继续使用。

大 BLOB 查询使用 deferred 列，只在下载、依赖重试或未来执行快照时显式加载，避免列表页面把 ZIP 和数据源内容一起读入内存。

## 9. HTTP 接口

```text
GET  /api/customers/{customer_id}/features
GET  /api/customer-features/{id}/data-source
PUT  /api/customer-features/{id}/data-source
GET  /api/customer-features/{id}/data-source/download
GET  /api/customer-features/{id}/config
PUT  /api/customer-features/{id}/config

GET  /api/admin/feature-definitions
POST /api/admin/features/versions
POST /api/admin/feature-versions/{id}/prepare
GET  /api/admin/feature-versions/{id}/default-data-source/download
POST /api/admin/customer-features/{id}/activate-version
PATCH /api/admin/customer-features/{id}
GET  /api/admin/settings
PUT  /api/admin/settings
```

配置管理和全部 `/api/admin/*` 接口受管理员权限与管理区网络门保护；修改接口另有 CSRF，敏感修改由应用服务要求重新认证。客户数据源替换允许有客户权限的业务操作员执行。

## 10. 前端

- 工作台按左上角当前客户加载功能卡片；管理员可以在每张功能卡片的“配置管理”旁打开上传窗口，在当前页面完成客户选择、文件选择、身份复验和上传；没有功能时从原空状态登记第一个功能，不增加独立操作卡；
- 清楚显示配置、依赖和数据源是否满足运行前提；
- 可以下载/替换客户数据源；
- 功能管理支持上传、查看静态校验警告、依赖失败摘要、重试和明确切换版本；
- 配置管理动态生成字段，密钥永不回显；
- 系统设置维护可信网络、可信代理、上传边界和依赖源；
- “运行”按钮明确标注阶段 C 且禁用，不制造脚本已经可控执行的错觉。

## 11. 后续阶段的强约束

阶段 C 创建运行记录时必须在一个短事务内固定：`customer_feature_id`、`feature_version_id`、`data_source_revision_id` 和配置快照。Runner 只能使用这些快照，不能在任务中途读取“当前”指针。配置密钥解密只发生在受控 Runner 输入准备路径，不得通过日志或 API 返回。
