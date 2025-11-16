# 全局设置（Application Settings）

此文档描述小树壁纸 Next 在 Flet 版本中的全局设置系统（应用级设置）。该系统用于存储与应用本身相关的偏好配置，例如界面主题、语言、下载/存储路径、更新策略等。

## 存储位置与格式

- 存储位置：使用平台规范的配置目录（由 `app.paths.CONFIG_DIR` 提供），文件名为 `config.json`。
- 格式：JSON。项目已有 `src/config.py` 定义了 `DEFAULT_CONFIG`，以及 `save_config_file` 辅助写入函数。

示例路径（Windows）: `%APPDATA%\Little-Tree-Wallpaper\Next\config.json`（具体由 `platformdirs` 决定）。

## 编程接口

新添加的模块：`src/app/settings.py`，提供 `SettingsStore`：

- 初始化：SettingsStore(path: pathlib.Path)
- 方法：
  - `get(key, default=None)` - 以顶层键读取设置（例如 `get('ui')`）
  - `set(key, value)` - 设置顶层键并立即保存到磁盘
  - `save()` - 显式保存当前内存设置到磁盘
  - `reset()` - 重置为 `DEFAULT_CONFIG` 并保存
  - `as_dict()` - 返回当前设置的浅拷贝字典视图

应用在启动时（`Application.__init__`）会实例化 `SettingsStore(CONFIG_DIR / "config.json")`。插件/页面在构建 `PluginContext` 时会在 `metadata` 字段中收到一个设置快照：

- `metadata['app_settings']` - 当前设置字典的快照（只读）
- `metadata['app_settings_path']` - 配置文件的文件系统路径

注意：当前对外暴露的是快照（字典副本），而不是 `SettingsStore` 实例本身；这避免了对存储并发写入的复杂性。如果需要插件写入设置，应通过核心 API 扩展或将写权限限定在受控路径中。

## UI 集成示例

核心设置页（`Pages.build_settings_view`）已添加了一个最小示例：

- 在“界面”选项中显示“界面主题”和“界面语言”的下拉控件
- 点击“保存设置”时，程序会将 `ui.theme` 和 `ui.language` 写入 `CONFIG_DIR/config.json`（使用项目已有 `save_config_file` 方法）

这只是一个示例；更多字段可以按相同方式添加并在保存时写回文件。

## 开机启动与自动执行

`startup` 节点现在包含更丰富的开机控制：

- `startup.auto_start`：布尔值，配合 `StartupManager` 在 Windows 注册表中添加/移除启动项。
- `startup.wallpaper_change`：描述开机后立即执行一次壁纸更换的行为，字段包括：
  - `enabled`：是否启用。
  - `list_ids`：参与的自动更换列表 ID（与自动换壁纸列表共用存储）。
  - `fixed_image`：可选的固定壁纸路径。
  - `order`：`random`、`random_no_repeat` 或 `sequential`。
  - `delay_seconds`：应用启动后的延迟执行秒数。

UI 中的“通用 → 开机与后台”板块允许用户直接操作这些设置，并提供“立即执行一次”按钮用于即时验证配置。

## 开发/测试 注意事项

- 项目使用 `orjson`（在 `src/config.py` 中用于快速 JSON 序列化/反序列化）。在本地运行或测试之前，请确保在项目 Python 环境中安装了 `orjson`。例如：

```powershell
# 激活虚拟环境后
python -m pip install orjson
```

- 也可以修改 `src/config.py` 以在 `orjson` 不可用时退回到内置 `json`（我可以代为实现）。

## 未来改进（可选）

- 将 `SettingsStore` 的实例以受控方式暴露给 `PluginContext`，并设计写权限与事件通知系统。
- 在 UI 上实现字段与设置的双向绑定与即时生效（例如更改主题立刻生效）。
- 添加单元测试覆盖 `SettingsStore` 行为（load/save/reset、损坏文件处理）。

---
文档到此。如需我把写权限以 API 形式暴露、或把设置 UI 扩展为完整配置面板，我可以继续实现。
