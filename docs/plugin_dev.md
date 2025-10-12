# 小树壁纸 Next 开发者临时指南

> 本文档针对当前开发分支（2025-10-07）提供的 API。随着架构演进，接口可能发生变化，请保持关注仓库更新。

## 插件目录与命名

- 插件源码位于 `src/plugins/` 目录下。
- 每个插件对应一个 Python 模块（`.py` 文件）或包，模块名即插件标识的一部分。
- 模块需要暴露一个名为 `PLUGIN` 的实例，类型实现了 `app.plugins.Plugin` 协议。
- 推荐以插件 `identifier` 作为文件名，例如 `sample.py` 对应 `identifier="sample"`。

## PluginManifest

每个插件必须定义 `PluginManifest`，并挂载到 `PLUGIN.manifest` 上，用于描述插件的静态信息。

```python
from app.plugins import PluginManifest, PluginKind

manifest = PluginManifest(
    identifier="sample",
    name="示例插件",
    version="0.1.0",
    description="演示如何集成 Little Tree Wallpaper Next 插件 API",
    author="Your Name",
    homepage="https://example.com",
    permissions=("resource_data",),  # 可选，需要访问受保护数据时声明
    dependencies=("core>=1.0.0",),  # 可选，支持简单的版本比较运算符
    kind=PluginKind.FEATURE,  # 可选，可声明为 PluginKind.LIBRARY
)
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `identifier` | 插件唯一标识符（用于存储目录、日志等），建议使用小写字母和下划线 |
| `name` | 插件显示名称 |
| `version` | 插件版本号，采用语义化版本 |
| `description` | 可选，插件简介 |
| `author` | 可选，作者信息 |
| `homepage` | 可选，主页或文档链接 |
| `permissions` | 可选，列出插件启动前需要授予的权限标识符 |
| `dependencies` | 可选，列出依赖的其他插件 identifier，可使用 `core>=1.0.0`、`helper==0.2` 这样的语法描述版本要求 |
| `kind` | 可选，插件类型，默认 `PluginKind.FEATURE`，当插件仅提供 API／库能力时可设为 `PluginKind.LIBRARY` |

访问 `manifest.short_label()` 可获得 `name` + `version` 的组合字符串。

## 插件生命周期

插件需要实现 `activate(self, context: PluginContext) -> None` 方法。在应用启动时，插件管理器会：

1. 创建插件实例上绑定的 `PluginManifest`；
2. 构造 `PluginContext`；
3. 调用插件的 `activate` 方法。

如果加载或激活过程中发生异常，错误会记录到日志并阻止该插件继续运行。

## PluginContext 能力

`PluginContext` 向插件提供了以下能力：

- `page`: 当前 Flet `Page` 实例，可用于构建 UI 控件或注册事件。
- `register_navigation(view)`: 注册一个主导航视图（见下文）。
- `register_route(view)`: 注册一个附加路由，通过 `page.go()` 访问。
- `register_startup_hook(hook)`: 注册应用启动后执行的回调。
- `set_initial_route(route)`: 可选地改变初始路由。
- `logger`: 已绑定插件 identifier 的 `loguru.Logger`，直接 `logger.info("...")` 即可。
- `metadata`: 字典，可用于在插件及核心系统之间传递额外信息；也可通过 `context.add_metadata(key, value)` 辅助写入。
- 权限辅助：`context.has_permission(id)` 检查当前授权；`context.request_permission(id, message=None)` 主动触发系统确认；`context.ensure_permission(id, message=None)` 确保已授权，否则抛出 `PluginPermissionError`。
- 全局数据接口：
    - `register_data_namespace(identifier, *, description="", permission=None)`：注册命名空间，声明数据归属以及访问权限。
    - `publish_data(namespace_id, entry_id, payload)`：写入 / 更新命名空间中的数据条目。
    - `latest_data(namespace_id)` / `get_data(namespace_id, entry_id)` / `list_data(namespace_id)`：读取共享数据快照，需被授予命名空间所要求的权限。
- 存储路径工厂：`plugin_data_path`、`plugin_config_path`、`plugin_cache_path` 以及对应的 `*_dir` 方法用于访问 / 初始化插件专属的数据、配置、缓存目录。传入 `create=True` 时会确保目录存在。
- `add_bing_action(factory)`: 在“资源 → Bing 每日”操作行追加自定义按钮或其他控件。
- `add_spotlight_action(factory)`: 在“资源 → Windows 聚焦”操作行追加控件。
- `register_settings_page(label, builder, *, icon=None, button_label="插件设置", description=None)`: 注册插件的专属设置页面。插件管理面板会在对应插件卡片中显示一个“插件设置”按钮，并在新页面中渲染 `builder` 返回的控件。
- 收藏管理接口（核心插件激活后可用，需在 manifest 中声明并获批对应的 `favorites_*` 权限；使用前可通过 `context.has_favorite_support()` 判断）：
    - `context.favorites`：返回 `FavoriteService` 实例，包裹了全部收藏操作并在内部执行权限校验。历史属性 `context.favorite_manager` 仍可用，但会返回同一服务实例。
    - 读取：`favorites.list_folders()` / `favorites.get_folder(id)` / `favorites.list_items(folder_id="__all__")` / `favorites.get_item(item_id)` / `favorites.find_by_source(source)`（需 `favorites_read`）。
    - 写入：`favorites.create_folder(...)`、`favorites.update_folder(...)`、`favorites.delete_folder(...)`、`favorites.add_or_update_item(...)`、`favorites.update_item(...)`、`favorites.remove_item(...)`、`favorites.register_classifier(...)`、`favorites.classify_item(...)`（需 `favorites_write`）。
    - 导入导出：`favorites.export_folders(target_path, folder_ids=None, include_assets=True)`、`favorites.import_package(path)`、`favorites.localize_items_from_files(mapping)`、`favorites.localization_root()`（需 `favorites_export`）。
    相关数据类型（`FavoriteSource`、`FavoriteItem` 等）可直接从 `app.plugins` 导入。
    相关数据类型（`FavoriteSource`、`FavoriteItem` 等）可直接从 `app.plugins` 导入。
- 系统操作接口（返回 `PluginOperationResult`，详见下文）：
    - `open_route(route: str)`: 请求跳转到指定路由。需声明并获得 `app_route` 权限。
    - `switch_home(navigation_id: str)`: 切换首页侧边栏导航项（例如 `home`、`resource`）。需 `app_home` 权限。
    - `open_settings_tab(tab: int)`: 打开设置页并定位到指定标签（按设置tabs顺序，从0开始）。需 `app_settings` 权限。
    - `set_wallpaper(path: str)`: 将本地图片设置为系统壁纸。需 `wallpaper_control` 权限。
    - `ipc_broadcast(channel: str, payload: dict)`: 通过跨进程广播发布消息。需 `ipc_broadcast` 权限。
    - `ipc_subscribe(channel: str)`: 订阅跨进程广播频道，成功时结果的 `data` 为 `IPCSubscription` 对象，可调用 `.get()` 读取队列消息。
    - `ipc_unsubscribe(subscription_id: str)`: 取消订阅，传入 `ipc_subscribe` 返回的订阅 ID。

### PluginOperationResult

所有系统操作接口都会返回 `PluginOperationResult`：

| 字段 | 含义 |
| --- | --- |
| `success` | 布尔值，表示操作是否立即成功执行。|
| `data` | 可选，成功时返回的附加结果（例如 IPC 订阅句柄）。|
| `error` | 当 `success=False` 时的错误代码，如 `permission_denied`、`permission_pending`、`invalid_argument`、`operation_failed`、`subscription_not_found` 等。|
| `message` | 可选的人类可读描述。|
| `permission` | 当错误与权限相关时指出具体的权限标识符。|

调用 `result.raise_for_error()` 可将失败结果转换为异常；当错误为 `permission_denied` 且带有权限标识时，会抛出 `PluginPermissionError`，便于插件或插件管理器统一处理。

常见错误码说明（权限请求会阻塞直到用户做出选择，因此不会返回 `permission_pending`）：

- `permission_denied`：权限被拒绝或撤销；插件可提示用户授权或直接终止相关功能。
- `invalid_argument`：传入参数无效（如导航 ID 不存在）。
- `operation_failed`：操作执行过程中发生异常，`message` 提供具体原因。
- `subscription_not_found`：取消订阅时未找到对应 ID。

推荐模式：

```python
result = context.open_route("/settings")
if not result.success:
    if result.error == "permission_denied":
        result.raise_for_error()  # 将抛出 PluginPermissionError，可由插件管理器捕获
    else:
        context.logger.error("操作失败: %s", result.message)
```

> **提示**：全局数据读取接口（`latest_data` / `get_data` / `list_data`）在没有权限时会返回 `None` 或空列表，而不会抛出 `PermissionDenied` 异常，便于插件在只读场景下按需降级。

示例：

```python
config_file = context.plugin_config_path("settings.json", create=True)
if not config_file.exists():
    config_file.write_text("{}", encoding="utf-8")

context.logger.info("配置文件位置: {}", config_file)
```

### 收藏 API 示例

以下示例演示如何在插件中“收藏”一张壁纸并保证去重（需要在 `PluginManifest.permissions` 中声明 `favorites_read` 与 `favorites_write`）：

```python
from app.plugins import FavoriteSource

def collect_wallpaper(context: PluginContext, metadata: dict) -> None:
    if not context.has_favorite_support():
        context.logger.warning("收藏系统尚未就绪，已忽略收藏请求")
        return

    source = FavoriteSource(
        type="custom",
        identifier=metadata["id"],
        title=metadata.get("title", "未命名壁纸"),
        url=metadata.get("preview"),
        extra={"plugin": context.manifest.identifier},
    )

    service = context.favorites
    item, created = service.add_or_update_item(
        folder_id="default",
        title=source.title,
        description=metadata.get("description", ""),
        tags=["插件示例", metadata.get("category", "壁纸")],
        source=source,
        preview_url=source.url,
        local_path=metadata.get("local_path"),
    )

    verb = "新增" if created else "更新"
    context.logger.info("{}收藏: {} ({})", verb, item.title, item.id)
```

## 权限管理

权限体系的状态说明、完整列表以及运行时授权流程已单独整理至
[`docs/plugin_permissions.md`](./plugin_permissions.md)。
开发插件时，当执行需要授权的操作（如收藏读写、路由跳转）且状态为
“下次询问”时，`PluginContext.ensure_permission()` 会触发系统对话框，阻塞等待用户选择。
若只需判断是否已授权，可调用 `context.has_permission("permission_id")`。

## 全局数据共享（Global Data Store）

`PluginContext` 暴露的全局数据接口允许插件之间通过受控的命名空间共享结构化信息。每个命名空间由“拥有者”插件注册，并可声明访问所需的权限（例如 `resource_data`）。写入数据时需要提供条目 ID，系统会维护修订号与时间戳，读取接口返回字典快照：

```python
context.register_data_namespace(
    "sample.notes",
    description="示例插件公开的笔记内容",
    permission=None,
)

context.publish_data(
    "sample.notes",
    entry_id="latest",
    payload={"message": "Hello from sample plugin"},
)

snapshot = context.latest_data("sample.notes")
if snapshot:
    payload = snapshot["payload"]
    context.logger.info("最新笔记: {}", payload.get("message"))
```

核心资源页会在加载 Bing / Spotlight 数据时写入 `resource.bing` 与 `resource.spotlight` 命名空间，并在事件 payload 中附带 `namespace` 与 `data_id` 字段，便于插件以 ID 回查最新快照。

## 收藏系统与数据格式

Little Tree Wallpaper Next 内置了一个收藏系统，用于存放用户在 Bing、Windows 聚焦以及其他来源中挑选出来的壁纸条目。收藏数据以 JSON 形式持久化在本地：

- 存储路径：`{DATA_DIR}/favorites/favorites.json`（`DATA_DIR` 为通过 `platformdirs.user_data_dir` 计算出的应用数据目录）。
- 文件版本号目前为 `1`，后续若有破坏性更新会通过 `version` 字段区分。
- 结构顶层包含 `folders`、`items`、`folder_order` 三个键：

```jsonc
{
    "version": 1,
    "folders": {
        "default": {
            "id": "default",
            "name": "默认收藏夹",
            "description": "系统自动创建的默认收藏夹",
            "order": 0,
            "created_at": 1730793600.0,
            "updated_at": 1730793600.0,
            "metadata": {}
        }
    },
    "items": {
        "c9b1f0...": {
            "id": "c9b1f0...",
            "folder_id": "default",
            "title": "Bing 每日壁纸",
            "description": "2025-10-03：桂林漓江",
            "tags": ["Bing", "每日壁纸"],
            "source": {
                "type": "bing",
                "identifier": "20251003",
                "title": "Bing 每日壁纸",
                "url": "https://www.bing.com/...",
                "preview_url": "https://www.bing.com/...",
                "local_path": null,
                "extra": {"copyright": "© ..."}
            },
            "preview_url": "https://www.bing.com/...",
            "local_path": null,
            "created_at": 1730793600.0,
            "updated_at": 1730793600.0,
            "ai": {
                "status": "idle",
                "suggested_tags": [],
                "suggested_folder_id": null,
                "metadata": {},
                "updated_at": null
            },
            "extra": {"bing": {"startdate": "20251003"}}
        }
    },
    "folder_order": ["default"]
}
```

字段说明：

- `FavoriteFolder`
    - `id`: 收藏夹 ID，默认收藏夹恒为 `default`。
    - `name` / `description`: 用户可编辑的名称与描述。
    - `order`: 用于在 UI Tabs 中排序的整数，系统会根据 `folder_order` 自动维护。
    - `metadata`: 预留对象，可在未来扩展颜色、图标等属性。
- `FavoriteItem`
    - `folder_id`: 归属的收藏夹 ID。
    - `title` / `description`: 展示文本，允许用户编辑。
    - `tags`: 标签字符串数组，UI 支持多标签检索。
    - `source`: `FavoriteSource` 对象，描述收藏来源：
        - `type`: 来源类型（`bing` / `windows_spotlight` / `system_wallpaper` / `custom` 等）。
        - `identifier`: 来源唯一键，用于去重。
        - `url`: 原始资源地址，可用于重新下载或打开详情页。
        - `preview_url`: 预览图片地址，优先用于 UI 展示。
        - `local_path`: 若资源已下载，会记录本地路径。
        - `extra`: 保留原始 API 数据或额外上下文。
    - `ai`: 预留给 AI 自动分类的字段，包含：
        - `status`: `idle` / `pending` / `running` / `completed` / `failed`。
        - `suggested_tags`: 模型产出的推荐标签。
        - `suggested_folder_id`: 模型建议归档到的收藏夹。
        - `metadata`: 自定义模型信息，如置信度、版本号等。
    - `extra`: 其他与业务相关的扩展字段。

核心代码通过 `app.favorites.FavoriteManager` 管理该文件，提供以下关键 API：

- `list_folders()` / `create_folder()` / `rename_folder()` / `delete_folder()` / `reorder_folders()`
- `add_or_update_item()` / `update_item()` / `remove_item()` / `find_by_source()` / `list_items()`
- `set_classifier(classifier)` / `maybe_classify_item(item_id)`：用于挂接未来的 AI 自动分类逻辑。`classifier` 可返回 `FavoriteAIResult(tags, folder_id, metadata)`，系统会把结果写入 `ai` 字段并保留人工修改。

> **注意**：收藏文件属于用户私有数据，插件若要访问请提前征得用户授权，并遵守隐私合规要求。核心 UI 在创建、编辑收藏后会自动刷新 Tabs，并调用 `maybe_classify_item()` 触发异步分析，开发者在实现 AI 模块时只需注册一个分类回调即可。

## 注册导航视图

导航视图用于在主界面侧边栏加入入口：

```python
from app.plugins import AppNavigationView
import flet as ft

context.add_navigation_view(
    AppNavigationView(
        id="sample",
        label="示例",
        icon=ft.Icons.EMOJI_OBJECTS_OUTLINED,
        selected_icon=ft.Icons.EMOJI_OBJECTS,
        content=ft.Container(
            content=ft.Column([
                ft.Text("Hello from sample plugin!"),
            ]),
            expand=True,
        ),
    )
)
```

> **注意**：至少有一个插件需要注册导航视图，否则应用无法正常启动。

## 注册附加路由

使用 `AppRouteView` 可以向 `page.views` 栈中额外注入视图，例如设置页面：

```python
from app.plugins import AppRouteView

context.add_route_view(
    AppRouteView(
        route="/sample/help",
        builder=lambda: ft.View("/sample/help", controls=[ft.Text("帮助页面")]),
    )
)
```

随后可通过 `page.go("/sample/help")` 访问。

## 启动钩子

插件可以在应用 UI 构建完成后执行初始化逻辑：

```python
def on_ready():
    context.logger.info("示例插件已经准备就绪")

context.add_startup_hook(on_ready)
```

钩子执行失败不会终止应用，但会记录错误日志。

## 日志与调试

`context.logger` 已绑定当前插件的 identifier，可直接用于调试：

```python
context.logger.debug("当前缓存目录: {}", context.plugin_cache_dir())
```

建议在需要时开启 `run.bat`（或 `uv run flet run`）查看实时日志。

## 扩展资源页操作按钮

`context.add_bing_action` 与 `context.add_spotlight_action` 均接收一个 *无参* 工厂函数，返回任意 Flet 控件。控件会被重新构建，因此请在工厂内创建新实例，而不要重用已有控件。

```python
def make_download_all_button():
    return ft.OutlinedButton(
        "批量下载",
        icon=ft.Icons.DOWNLOAD_FOR_OFFLINE,
        on_click=lambda _: context.logger.info("批量下载触发"),
    )

context.add_bing_action(make_download_all_button)
```

控件将被插入到现有的操作按钮组之后，可用于提供插件特有的批量处理、收藏或分享功能。

## 事件系统（Event Bus）

为了支持插件之间以及核心与插件之间的轻量数据广播与协作，应用内置了一个简单的同步事件总线（`PluginEventBus`）。事件系统采用声明式事件定义 + 订阅回放的模式，并带有权限控制以保护敏感资源数据。

要点概览：
- 每种事件都由一个 `event_type` 字符串标识，并可附带 `description` 与可选 `permission`（需要插件被授权才能接收）。
- 插件（或核心）通过 `register_event(owner, event_type, description, permission)` 注册事件定义。
- 插件订阅事件通过 `subscribe(plugin_id, event_type, handler, replay_last=True)`，订阅者会收到后续事件并可选择重放最新一条已保存的事件（用于状态同步）。
- 发送事件通过 `emit(event_type, payload, source=plugin_id)`，载荷为一个字典（JSON 兼容）。事件会被同步分发到满足权限要求的监听器。
- 核心以 `namespace` + `data_id` 将事件与全局数据条目关联；例如 `resource.bing.updated` 会包含 `namespace="resource.bing"` 与最新条目的 `data_id`，便于订阅方使用 `context.latest_data` 快速获取同一份内容。

核心类型说明（摘要）：
- `EventDefinition(event_type, description="", permission=None)`：事件元数据。
- `PluginEvent(type, payload: dict, source: str)`：投递给监听器的运行时事件对象。

权限与安全：
- 若事件定义带有 `permission`（例如 `resource_data`），事件总线在分发前会询问一个权限解析器（由主应用注入）以判断某个监听插件是否被授予该权限。未被授权的插件不会收到事件。
- 插件应当仅在明确需要时请求权限，核心也会把重要事件声明在 `CORE_EVENT_DEFINITIONS` 中。
- 新增权限 `python_import` 用于约束插件在运行时加载额外的 Python 模块；如需自带第三方依赖或动态 `importlib`，请在 manifest 中声明并提示用户授予。

重放行为（replay_last）：
- 事件总线会保留每个事件类型的最近一次事件（last event）。当新的订阅者订阅并且 `replay_last=True` 时，如果该事件存在且订阅者有权限，会立即收到该事件，便于做初始化／状态同步。

示例：注册、订阅与发送

```python
from app.plugins import EventDefinition

# 在插件激活时（通常由 core 或者插件本身注册）
context.register_event(
    event_type="resource.bing.updated",
    description="Bing 每日壁纸已刷新",
    permission="resource_data",
)

def on_bing_update(event):
    # event.payload 是一个字典，包含由触发方定义的字段
    print("收到 Bing 更新：", event.payload)
    data_id = event.payload.get("data_id")
    if data_id:
        latest = context.get_data("resource.bing", data_id)
        print("关联的全局数据条目:", latest)

# 订阅（replay_last=True 会立即收到最近一条事件以同步状态）
unsubscribe = context.subscribe_event("resource.bing.updated", on_bing_update, replay_last=True)

# 发送事件（例如在资源刷新逻辑中）
context.emit_event("resource.bing.updated", payload={"date": "2025-10-03", "url": "..."})

# 若不再需要监听，调用退订函数
unsubscribe()
```

注意事项与最佳实践：
- 事件载荷应保持精简且可序列化（避免直接传入大对象或未序列化的自定义类）。
- 若事件涉及敏感数据（例如本地文件路径或用户信息），请在事件定义中声明 `permission` 并在插件中谨慎订阅/请求授权。
- 事件处理器应尽量保持短小、同步安全；事件总线为同步分发，阻塞的处理器会阻塞后续分发。

核心事件清单（示例）
- `resource.bing.updated`：Bing 每日壁纸数据刷新（permission="resource_data"）
- `resource.bing.action`：用户在 Bing 卡片上执行操作（permission="resource_data"）
- `resource.spotlight.updated`：Windows 聚焦资源列表更新（permission="resource_data"）
- `resource.spotlight.action`：Windows 聚焦动作（permission="resource_data"）
- `resource.download.completed`：内置资源下载完成（permission="resource_data"），payload 附带 `source`、`action`、`file_path` 以及对应资源的 `namespace`、`data_id`

以上核心事件由应用在启动时注册（参见 `CORE_EVENT_DEFINITIONS`），插件可以直接订阅或在需时重新注册／扩展新的事件类型。

## 跨进程广播（IPC）

应用内置一个轻量级 IPC 服务，允许获得 `ipc_broadcast` 权限的插件与外部进程通过“频道”共享 JSON 兼容的消息。核心特性：

- 插件使用 `context.ipc_broadcast(channel, payload)` 发送消息；
- 使用 `context.ipc_subscribe(channel)` 订阅频道，成功时 `result.data` 为 `IPCSubscription` 对象：
    - `subscription.subscription_id`：取消订阅时需要的 ID；
    - `subscription.channel`：频道名；
    - `subscription.get(timeout=None)`：从线程安全队列中读取下一条消息，返回 `dict` 或 `None`（超时或关闭）。
- 通过 `context.ipc_unsubscribe(subscription_or_id)` 释放订阅，既可以传入 `IPCSubscription` 对象，也可以传入其 `subscription_id`；在插件停用 / 应用重载时会自动清理残留订阅。
- 内部消息结构：

```json
{
    "channel": "sample",
    "payload": {"text": "hello"},
    "origin": "sample-plugin",
    "timestamp": 1735929600.123
}
```

### 外部进程接入

- **Windows**：使用命名管道 `\\.\pipe\little-tree-wallpaper-ipc`；
- **macOS / Linux**：使用 Unix Domain Socket，路径位于运行时目录（可通过 `context.ipc_broadcast("system.describe", {})` 或外部 `describe` 命令获取）。

示例（外部 Python 进程）：

```python
from multiprocessing.connection import Client

address = r"\\.\pipe\little-tree-wallpaper-ipc"  # Windows；Unix 系统改为 socket 文件路径
with Client(address, family="AF_PIPE") as conn:
        conn.send({"action": "subscribe", "channel": "sample"})
        print(conn.recv())  # 订阅确认
        conn.send({"action": "publish", "channel": "sample", "payload": {"text": "外部消息"}})
        event = conn.recv()
        print("收到广播:", event)
```

外部客户端可发送以下动作：

| 动作 | 说明 |
| --- | --- |
| `subscribe` | 订阅频道，服务端会回发 `{"ack": "subscribe", "channel": ...}` |
| `unsubscribe` | 取消订阅 |
| `publish` | 发布广播，与内部插件一样会投递给所有订阅者 |
| `describe` | 获取当前频道、地址等诊断信息 |

> 建议配合权限系统使用：未获授权的插件调用 IPC 接口会得到 `permission_denied` 或 `permission_pending` 结果，并不会影响其他功能。

## 导入流程与权限提示

通过“导入插件 (.py)”选择文件后，应用会预先加载其 manifest，并弹出权限确认对话框：
- 列出插件声明的权限，用户可逐项决定是否授予；
- 若插件 manifest 缺失或无法解析，会给出警告并仍允许导入；
- 用户确认后会立即保存权限设置并重新加载插件；若选择“稍后再说”，插件将以默认权限（全部未授权）加载。

权限状态现为三态（已授权 `granted` / 已拒绝 `denied` / 待确认 `prompt`）。当状态为 `prompt` 时，首次调用相关接口会触发运行时弹窗，插件收到的 `PluginOperationResult` `error` 字段为 `permission_pending`，用户确认后可再次尝试操作。

如果插件依赖其他插件或库型插件（`kind=PluginKind.LIBRARY`），请在 manifest 的 `dependencies` 中注明版本要求；当依赖未满足时，插件管理面板会显示“依赖缺失”状态，并阻止被依赖项被删除。

## 插件设置页面

插件可以通过 `register_settings_page` 在插件管理面板中启用“插件设置”按钮。点击后会跳转到一个带统一 AppBar 的新页面，展示插件自定义的配置控件：

```python
context.register_settings_page(
    label="高级选项",
    icon=ft.Icons.TUNE,
    button_label="插件设置",
    description="在这里集中管理高级功能开关",
    builder=lambda: ft.Container(
        padding=20,
        content=ft.Column(
            spacing=12,
            controls=[
                ft.Switch(label="启用增强模式", value=True),
                ft.Text("保存后需要重新启动插件。", size=12, color=ft.Colors.GREY),
            ],
        ),
    ),
)
```

按钮标题默认为“插件设置”，可通过 `button_label` 自定义。`description` 会显示在设置页面顶部，适合放置说明或提示。

## 示例插件

仓库提供了 `src/plugins/sample.py` 作为参考实现，覆盖了：

- Manifest 定义与全局 `PLUGIN` 实例；
- 导航视图、路由注册；
- 使用插件专属的数据 / 配置目录；
- 启动钩子与日志输出；
- 使用 `PluginContext.metadata` 传递信息；
- 订阅 `resource.download.completed` 事件，记录最近一次下载并展示事件日志；
- 展示权限状态，并提供 `open_route` / `switch_home` / `open_settings_tab` / `set_wallpaper` 等操作的快捷测试按钮；
- `add_bing_action` / `add_spotlight_action` 扩展资源页操作按钮；
- `register_settings_page` 提供插件专属的设置页面。

示例插件声明了 `resource_data`、`app_route`、`app_home`、`app_settings` 与 `wallpaper_control` 等权限，方便在实际应用中直接体验运行时授权对话框和操作结果。可根据需要复制并裁剪成自己的模板。

---

若在开发过程中遇到接口问题或希望扩展 API，请在仓库 Issue 中说明具体诉求，我们会优先迭代正式文档。
