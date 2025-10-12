
<table width="100%">
  <tr>
    <td align="left" width="120">
      <img src="src\assets\images\icon.ico" alt="OpenCut Logo" width="100" />
    </td>
    <td align="right">
      <h1>Little Tree Wallpaper Next  <br><span style="font-size: 0.7em; font-weight: normal;">小树壁纸Next</span></h1>
      <h3 style="margin-top: -10px;">A wallpaper app for desktop <br><span style="font-size: 0.7em; font-weight: normal;">一个桌面壁纸应用</span></h3>
    </td>
  </tr>
</table>


> [!NOTE]
> 
> This project is still under development. 
> 
> This is the Next version of the Little Tree Wallpaper, developed based on Flet. 
> 
> [Main repository of Little Tree Wallpaper](https://github.com/shu-shu-1/Little-Tree-Wallpaper)
> 
> ————————
> 
> 该项目仍在开发中。
> 
> 这是小树壁纸的Next版本，基于Flet开发。
> 
> [小树壁纸主仓库](https://github.com/shu-shu-1/Little-Tree-Wallpaper)


![Visitor Count](http://estruyf-github.azurewebsites.net/api/VisitorHit?user=shu-shu-1&repo=Little-Tree-Wallpaper-Next-Flet&countColor=%237B1E7B)

## Overview / 概述 ℹ️

Little Tree Wallpaper is a versatile app designed to quickly change and download wallpapers from a variety of sources, including Bing, 360, and Wallhaven. ✨ In addition, it supports multiple interfaces that allow users to bookshop and automatically rotate their favorite wallpapers.Little Tree Wallpaper will conduct local intelligent classification of users' wallpapers.

Stay tuned for more exciting features coming soon! 🎉

If you like this project, please give it a star! ⭐️

————————

小树壁纸是一款多功能应用程序，旨在快速更换和下载来自多种来源的壁纸，包括 Bing、360 和 Wallhaven。✨ 另外，它支持多种接口，允许用户收藏并自动轮换他们喜欢的壁纸，小树壁纸会为用户壁纸进行本地智能分类。

敬请期待更多激动人心的功能即将上线，我们将不断更新优化，为您带来更好的使用体验！🎉

如果您喜欢这个项目，不妨点个 ⭐️ 吧！

## 指南

## Test watermark / 测试版水印 🏷️

A small, unobtrusive badge appears at the bottom-right when the app runs in non-stable mode. You can tweak or disable it:

- File: `src/app/constants.py`
- Toggle: change `MODE = "TEST"` to `"STABLE"` to hide the badge globally.

当应用处于非稳定模式时，右下角会显示一个不打扰的“测试版”角标；如需关闭或自定义：

- 位置：`src/app/constants.py`
- 开关：把 `MODE = "TEST"` 改为 `"STABLE"` 即可全局隐藏角标。

## Plugin system quick start / 插件系统速览 🔌

The entry point has been modularized. At runtime the app loads plugins from `src/plugins/`. Each plugin can register navigation destinations and additional routes through a simple context API.

- Core plugin: `src/plugins/core.py` – provides the built-in pages.
- Sample plugin: `src/plugins/sample.py` – demonstrates the latest API features.
- Plugin contracts: `src/app/plugins/base.py`.
- Discovery: `src/app/plugins/manager.py` automatically imports Python modules placed under `src/plugins/` that expose a `PLUGIN` instance.
- Developer notes: see `docs/plugin_dev.md` for the temporary plugin authoring guide.

要扩展应用，只需在 `src/plugins/` 中新建模块，并实现 `PLUGIN = YourPlugin()`，并为插件定义 `PluginManifest`：

```python
import flet as ft

from app.plugins import AppNavigationView, Plugin, PluginContext, PluginManifest


class ExamplePlugin(Plugin):
  manifest = PluginManifest(
    identifier="example",
    name="示例插件",
    version="0.1.0",
  )

  def activate(self, context: PluginContext) -> None:
    context.add_navigation_view(
      AppNavigationView(
        id="example",
        label="示例",
        icon=ft.Icons.EMOJI_OBJECTS_OUTLINED,
        selected_icon=ft.Icons.EMOJI_OBJECTS,
        content=ft.Text("Hello from plugin!"),
      )
    )


PLUGIN = ExamplePlugin()
```

Plugins can keep state, use the shared `ft.Page` instance from `context.page`, schedule startup hooks via `context.add_startup_hook`, and persist files under the per-plugin storage helpers provided by `PluginContext`. 插件可以访问 `context.page` 获取 Flet 页面实例，通过 `context.add_startup_hook` 注册启动钩子，并使用上下文提供的路径助手读写专属数据。

Need plugin-specific actions? Use `context.add_bing_action` / `context.add_spotlight_action` to append buttons below the built-in wallpaper cards, and `context.register_settings_page` to expose a dedicated settings view accessed via the plugin card's **插件设置** button. 更多扩展 API 详见 `docs/plugin_dev.md`。


## Run the app / 运行指南 ▶️

### uv

Run as a desktop app / 作为桌面应用运行: 

```
uv run flet run
```

Run as a web app / 作为web应用运行:

```
uv run flet run --web
```

### Poetry

Install dependencies from `pyproject.toml` / 从 `pyproject.toml` 安装依赖:

```
poetry install
```

Run as a desktop app / 作为桌面应用运行:

```
poetry run flet run
```

Run as a web app / 作为web应用运行:

```
poetry run flet run --web
```

For more details on running the app, refer to the [Flet Getting Started Guide](https://flet.dev/docs/getting-started/).

有关运行该应用程序的更多详细信息，请参阅 [Flet入门指南](https://flet.dev/docs/getting-started/)。

## Build the app / 构建指南 📦

### macOS

```
flet build macos -v
```

For more details on building macOS package, refer to the [Flet macOS Packaging Guide](https://flet.dev/docs/publish/macos/).

有关构建macOS包的更多详细信息，请参阅 [Flet macOS打包指南](https://flet.dev/docs/publish/macos/)。

### Linux

```
flet build linux -v
```

For more details on building Linux package, refer to the [Flet Linux Packaging Guide](https://flet.dev/docs/publish/linux/).

有关构建Linux包的更多详细信息，请参阅 [Flet Linux打包指南](https://flet.dev/docs/publish/linux/)。

### Windows

```
flet build windows -v
```

For more details on building Windows package, refer to the [Flet Windows Packaging Guide](https://flet.dev/docs/publish/windows/).

有关构建Windows包的更多详细信息，请参阅 [Flet Windows打包指南](https://flet.dev/docs/publish/windows/)。

## Release Notes / 版本发行说明 📋

This project follows the versioning conventions of [Semantic Versioning 2.0.0](https://semver.org/). 📦

本项目采用[语义化版本 2.0.0](https://semver.org/lang/zh-CN/)的版本命名规则。📦

## Special Thanks / 特别感谢 ❤️

@[炫饭的芙芙](https://space.bilibili.com/1669914811)


## Star History / Star 趋势 🌟


<a href="https://www.star-history.com/#shu-shu-1/Little-Tree-Wallpaper-Next-Flet&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=shu-shu-1/Little-Tree-Wallpaper-Next-Flet&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=shu-shu-1/Little-Tree-Wallpaper-Next-Flet&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=shu-shu-1/Little-Tree-Wallpaper-Next-Flet&type=Date" />
 </picture>
</a>


---

Feel free to explore, contribute, 和 help improve the project! 

🚀 欢迎随时探索、贡献和帮助改进此项目！

## Plugin settings tab index (0-based) / 插件设置页索引说明 🧭

When developing plugins, you may want to programmatically open the app Settings page and switch to the "Plugins" tab. Flet's Tabs selection is numeric and 0-based, so using a hard-coded number in plugins is fragile and hard to maintain.

To avoid magic numbers the application exposes a small constant in `src/app/constants.py`:

- `SETTINGS_TAB_PLUGINS` — index of the "Plugins" tab inside the Settings view (0-based).

Example (inside a plugin):

```python
from app.constants import SETTINGS_TAB_PLUGINS

# ... inside your plugin's activate or UI builder:
context.open_settings_tab(SETTINGS_TAB_PLUGINS)
```


插件如果需要跳转到应用的“设置 → 插件”页，请优先使用 `src/app/constants.py` 中提供的 `SETTINGS_TAB_PLUGINS` 常量，避免在代码中直接写入索引数字（0-based）。示例：

```python
from app.constants import SETTINGS_TAB_PLUGINS

context.open_settings_tab(SETTINGS_TAB_PLUGINS)
```

Using the named constant improves readability and makes future reshuffles of the Settings tabs safer, since only the constant needs to be updated.


## Application settings / 全局设置（开发者说明）

This repository includes a small application-level settings system used to persist program preferences (UI theme, language, storage paths, update policy, etc.). The implementation stores settings as JSON in the platform-appropriate config directory (see `app.paths.CONFIG_DIR`).

- Settings defaults are defined in `src/config.py` as `DEFAULT_CONFIG`.
- A convenience helper `SettingsStore` is provided at `src/app/settings.py` with `get/set/save/reset/as_dict` APIs.
- During startup the app instantiates a `SettingsStore(CONFIG_DIR / "config.json")` and exposes a read-only snapshot and path to plugins via `PluginContext` metadata under `metadata['app_settings']` and `metadata['app_settings_path']`.

Developer note: the project prefers `orjson` for fast JSON operations (imported in `src/config.py`). Before running the app or tests locally, ensure `orjson` is available in your environment:

```powershell
# activate your venv, then
python -m pip install orjson
```

If you prefer not to install `orjson`, I can add a small fallback so `src/config.py` uses the built-in `json` when `orjson` is missing.
