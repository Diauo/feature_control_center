# 第三方组件说明

本目录保存需要随交付包明确保留的第三方许可证文本。依赖的精确版本同时固定在 `backend/pyproject.toml` 和 `frontend/package-lock.json`。

| 组件 | 版本 | 用途 | 许可证 / 上游 |
| --- | --- | --- | --- |
| 7-Zip Extra (`7zz`) | 26.03 | 正式 Linux 镜像中的 RAR 解码 | [`7zip-license.txt`](./7zip-license.txt)、[7-Zip](https://www.7-zip.org/) |
| rarfile | 4.5 | RAR3/RAR5 元数据解析与安全读取适配 | ISC，[rarfile](https://github.com/markokr/rarfile) |
| openpyxl | 3.1.5 | 生成执行汇总与结果明细 XLSX | MIT，[openpyxl](https://openpyxl.readthedocs.io/) |
| Morphicons | 1.7.1 | 密码可见性与侧栏状态动态图标 | MIT，[Morphicons](https://github.com/guillermolg00/morphicons) |
| Motion for Vue | 2.4.2 | 登录视觉区和界面动效 | MIT，[motion-v](https://github.com/motiondivision/motion-vue) |
| Vue Sonner | 2.0.9 | 右上角操作通知 | MIT，[vue-sonner](https://github.com/xiaoluoboding/vue-sonner) |

7-Zip 的 RAR 代码存在许可证中特别说明的限制。本项目只分发官方预编译命令行二进制，不修改其解码代码；完整文本以本目录副本为准。
