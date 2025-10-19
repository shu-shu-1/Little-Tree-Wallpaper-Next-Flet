# 小树壁纸 Next 插件权限说明

> 更新日期：2025-10-19

本文件汇总插件权限体系的设计目标、可用权限清单，以及运行时授权流程，供插件开发者与维护人员参考。

## 权限状态与策略

应用在持久化层面支持三种决策：

- **允许（granted）**：永久授予能力，后续调用不会再弹出提示。
- **拒绝（denied）**：直接拒绝能力，相关 API 会返回 `permission_denied` 或抛出 `PluginPermissionError`。
- **下次询问（prompt）**：在下一次实际调用时弹出权限对话框，由用户临时决定。

当状态为 “下次询问” 时，调用线程会阻塞直到用户处理提示。用户选择“稍后决定”不会改变存储状态，后续再次调用仍会弹窗。

## 已知权限列表

| 标识符 | 说明 |
| --- | --- |
| `filesystem` | 允许插件访问应用数据目录之外的本地文件。 |
| `network` | 允许插件发起自定义网络请求。 |
| `clipboard` | 允许插件读取或写入系统剪贴板。 |
| `wallpaper` | 允许插件设置或删除系统壁纸。 |
| `resource_data` | 允许插件接收资源页提供的壁纸元数据。 |
| `python_import` | 允许插件在运行时加载额外的 Python 模块或依赖。 |
| `app_route` | 允许插件请求跳转到任意已注册的应用路由。 |
| `app_home` | 允许插件切换首页导航。 |
| `app_settings` | 允许插件打开设置页并定位标签。 |
| `wallpaper_control` | 允许插件触发内置壁纸操作（Bing / Windows 聚焦）。 |
| `ipc_broadcast` | 允许插件通过内置 IPC 服务订阅、发送跨进程广播消息。 |
| `favorites_read` | 允许插件读取收藏夹及收藏条目。 |
| `favorites_write` | 允许插件创建、修改或删除收藏夹与条目。 |
| `favorites_export` | 允许插件导入 / 导出收藏数据、访问本地化资源。 |
| `theme_read` | 允许插件读取已安装的主题列表与元数据。 |
| `theme_apply` | 允许插件切换当前主题或更新主题背景设置。 |

> 插件导入时还可能根据源码中的 `import` 语句生成动态的 `python_import:*` 子权限，以便用户审核依赖。

## 运行时授权流程

- **系统操作（如 `context.open_route`）** 始终通过应用层 `_ensure_permission`，未授权时自动弹出对话框。
- **收藏 API、全局数据等延迟校验能力** 现在会在权限为 `prompt` 时触发同样的对话框：
  - `PluginContext.ensure_permission()` 会在遇到 `prompt` 状态时调用宿主并阻塞等待用户选择。
  - `FavoriteService` 等包装类复用了上述逻辑，因此在“下次询问”状态下再次访问会正常弹窗。
- **事件总线与全局数据读取** 会在缺少授权时静默跳过，以免在高频事件下反复弹窗。插件可通过 `context.request_permission()` 主动引导授权。

## 插件侧最佳实践

- 在执行需要授权的操作前，使用 `context.has_permission("xxx")` 快速检查是否已授予。
- 若需要在运行时提示用户，调用 `context.request_permission("xxx", message="...说明...")`。`message` 会显示在系统弹窗内，帮助用户理解申请原因。
- 捕获 `PluginPermissionError`，向用户展示友好提示或引导到“插件管理 → 管理权限”。

## 管理端提示

- 插件管理页面的“管理权限”对话框仍可批量调整上述状态。
- 当后台监测到某个权限被拒绝，会在状态栏弹出含插件名与权限名的提醒，方便定位问题。

更多插件开发信息，请配合阅读 `docs/plugin_dev.md`。