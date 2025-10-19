# 主题系统（Theme System）

本文档介绍 Flet 版本“小树壁纸 Next”的主题系统与主题文件格式。主题用于统一应用配色、背景图片以及特定组件的样式。

## 存放位置

- 默认主题文件目录：`%APPDATA%/Little-Tree-Wallpaper/Next/themes/`（Windows，具体由 `app.paths.CONFIG_DIR` 决定）。
- 通过配置项 `ui.theme_profile` 选取主题：
  - `"default"`（默认值）使用内置主题。
  - 也可以填写自定义主题文件名（相对 `themes/` 目录）或绝对路径，例如 `"aurora.json"`。

> 若目录不存在，应用会在启动时自动创建。

## 主题文件结构

主题文件为 JSON 对象，推荐包含以下几个段落：

```json
{
  "schema_version": 1,
  "name": "示例主题",
  "palette": {
    "mode": "seed",
    "seed_color": "#4f46e5",
    "preferred_mode": "dark",
    "use_material3": true
  },
  "background": {
    "image": "https://images.unsplash.com/photo-1469474968028-56623f02e42e",
    "opacity": 0.35,
    "fit": "cover",
    "alignment": "center",
    "repeat": "no_repeat"
  },
  "components": {
    "page": {
      "bgcolor": "#0f172a"
    },
    "app_bar": {
      "bgcolor": "#0f172a",
      "color": "#f8fafc"
    },
    "navigation_rail": {
      "bgcolor": "#111827",
      "indicator_color": "#34d399"
    },
    "navigation_container": {
      "bgcolor": "#111827"
    }
  }
}
```

### 配色（palette）

主题支持两种颜色配置模式：

- `seed`：通过 `seed_color` 指定单一主题色，Flet 会基于该颜色生成完整的色板。
- `custom`：直接提供 `color_scheme` 字段，用以填充 `ft.ColorScheme` 的属性，例如 `primary`、`on_primary`、`surface` 等。可以同时指定 `brightness`（`light`/`dark`）。

附加字段：

- `preferred_mode`（可选）：`light` / `dark` / `system`。当应用设置为“跟随系统”时，主题可用此字段建议一个首选模式。
- `use_material3`（布尔值，可选）：控制 `ft.Theme.use_material3`。

所有颜色值均可使用：

- 十六进制（`#RRGGBB` 或 `#AARRGGBB`）。
- `rgb(...)` / `rgba(...)`。
- Flet 颜色常量名称（如 `"surface_container_highest"`），大小写不敏感，连字符会自动转换为下划线。

### 背景（background）

- `image`：图片路径或 URL。相对路径会依次在主题文件所在目录、`themes/` 目录以及配置目录中查找。
- `opacity`：0.0 ~ 1.0 的浮点值。
- `fit`：`cover`、`contain`、`fill`、`fit_width`、`fit_height`、`scale_down`、`none`。
- `alignment`：`center`、`top_left`、`top`、`top_right`、`left`、`right`、`bottom_left`、`bottom`、`bottom_right`。
- `repeat`：`no_repeat`、`repeat`、`repeat_x`、`repeat_y`。

背景层位于主界面最底层，与应用内容叠加。

### 组件样式（components）

`components` 是一个以组件标识为键的对象，值为需要写入控件的属性字典。支持的组件标识当前包括：

- `page`：对应 `ft.Page`，可设置 `bgcolor`、`padding` 等直接属性。
- `app_bar`：首页 `ft.AppBar`。
- `navigation_rail`：侧边导航栏 `ft.NavigationRail`。
- `navigation_panel`：包裹导航栏与分割线的容器，可统一设置背景色、内边距等。
- `navigation_divider`：导航栏与内容区之间的分割线（`ft.VerticalDivider`）。
- `navigation_container`：用于承载当前页面内容的 `ft.Container`。
- `home_view`：首页 `ft.View`。

> 属性会直接通过 `setattr` 写入控件，因此请使用 Flet 控件支持的字段名称。带 `color` 的字段会自动尝试解析为 Flet 颜色常量或十六进制颜色。

针对 `home_view`，当主题定义了背景图片时，还可以使用以下扩展键：

- `overlay_color`：叠加在背景图片上的遮罩颜色（默认读取 `bgcolor`）。
- `overlay_opacity`：遮罩透明度，范围 0.0~1.0，默认为 1.0。
- `force_bgcolor`：若设为 `true`，即使存在背景图片也会直接将 `bgcolor` 应用于视图自身（禁用遮罩逻辑）。

## 启用自定义主题

1. 将主题 JSON 文件放入配置目录的 `themes/` 子目录。
2. 修改 `config.json` 中的 `ui.theme_profile` 字段，例如：
   ```json
   {
     "ui": {
       "theme": "system",
       "theme_profile": "aurora.json"
     }
   }
   ```
3. 重新启动应用或在运行时触发重载，即可看到主题生效。

若主题解析失败，程序会记录警告日志并回退到默认主题。

## 设置界面集成

应用的全局设置新增了“主题”标签页，可在运行时完成主题切换：

- 列表自动展示默认主题与配置目录 `themes/` 下的全部 `*.json` 主题文件。
- 点击“刷新”按钮可重新读取主题目录；“打开主题目录”会在系统文件管理器中定位该目录。
- “应用主题”会立即将所选主题写入 `ui.theme_profile`，并触发应用重新加载以套用背景与颜色样式。

> 主题文件更改后无需重启，重新点击“应用主题”即可在界面中生效。

## 示例主题

仓库附带一个示例主题文件：`docs/themes/aurora_green.json`。可复制到配置目录后，通过 `ui.theme_profile` 引用 `"aurora_green.json"` 即可预览效果。欢迎在此基础上调整颜色、背景和组件样式。

## 插件访问主题接口

插件可通过新的 `PluginContext` API 管理主题（需声明权限）：

- `context.list_themes()` → 返回主题列表与元数据。需要 `theme_read` 权限。
- `context.set_theme_profile(profile_id)` → 应用指定主题。需要 `theme_apply` 权限。

主题条目包含字段：

- `id`：主题标识（`default` 或相对于 `themes/` 的路径）。
- `name`：展示名称。
- `path`：实际文件路径（内置主题为空）。
- `builtin`：是否为内置主题。
- `source`：`builtin` / `file` / `custom`。
- `summary`：主题描述（可选）。
- `is_active`：是否为当前正在使用的主题。

插件在调用 `set_theme_profile` 后，宿主会重建 UI 以应用新主题；请在调用前提示用户该操作会导致界面刷新。
