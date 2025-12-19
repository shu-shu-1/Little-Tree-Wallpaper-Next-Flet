# 商店功能实现说明

## 实现概览

商店功能通过新建的 `app/store` 模块实现，提供主题、壁纸源和插件的在线获取和管理。

## 架构设计

```
┌─────────────────────────────────────────────┐
│           用户界面 (UI Layer)                │
│  - 商店页面 (StoreUI)                        │
│  - 设置页面（商店源配置）                     │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│         服务层 (Service Layer)               │
│  - StoreService: 资源获取                    │
│  - 异步HTTP请求                              │
│  - JSON/TOML解析                             │
└─────────────────┬───────────────────────────┘
                  │
┌─────────────────▼───────────────────────────┐
│         数据模型 (Data Models)               │
│  - ResourceMetadata                          │
│  - ResourceAuthor                            │
│  - ResourceAsset                             │
└──────────────────────────────────────────────┘
```

## 文件修改清单

### 新增文件

1. **`src/app/store/__init__.py`**
   - 模块导出
   - 公开API定义

2. **`src/app/store/models.py`**
   - 数据模型定义
   - 字段验证逻辑

3. **`src/app/store/service.py`**
   - 资源获取服务
   - API通信逻辑
   - 数据解析

4. **`src/app/store/ui.py`**
   - 商店页面UI
   - 资源展示
   - 交互处理

5. **`src/app/store/README.md`**
   - 模块开发文档

6. **`docs/store.md`**
   - 用户使用指南

7. **`test_store.py`**
   - 单元测试脚本

### 修改文件

1. **`src/app/core/pages.py`**
   - 添加商店相关导入
   - 新增 `_build_store()` 方法
   - 新增 `_build_store_source_settings_section()` 方法
   - 新增安装处理方法：
     - `_handle_install_theme()`
     - `_handle_install_plugin()`
     - `_handle_install_wallpaper_source()`
     - `_download_and_install_theme()`
     - `_download_and_install_plugin()`
     - `_download_and_install_wallpaper_source()`
   - 初始化 `self.store` 和 `self._store_ui`

2. **`src/plugins/core.py`**
   - 添加商店导航项 `AppNavigationView`

## 关键实现细节

### 1. 数据流

```
官方/自定义源
    ↓
index.json (文件列表)
    ↓
*.toml (资源元数据)
    ↓
ResourceMetadata 对象
    ↓
UI 展示
    ↓
用户点击安装
    ↓
下载文件
    ↓
导入/安装
```

### 2. 异步处理

所有网络请求都使用 `aiohttp` 异步执行：
- `StoreService` 的所有 API 方法都是 `async`
- `StoreUI.load_resources()` 使用 `asyncio.create_task()`
- 下载和安装使用 `page.run_task()`

### 3. 错误处理

- 服务层：抛出 `StoreServiceError` 异常
- UI层：捕获异常并通过 `SnackBar` 提示用户
- 日志：使用 `loguru` 记录详细错误

### 4. 配置管理

商店源配置存储在 `SettingsStore` 中：
```python
{
    "store.use_custom_source": bool,
    "store.custom_source_url": str
}
```

### 5. 图标处理

支持四种图标格式（优先级递减）：
1. `icon_data_uri`: Data URI（推荐）
2. `icon_path`: 仓库相对路径
3. `icon_url`: 外部URL
4. `icon_base64` + `icon_mime`: Base64编码

### 6. 下载和安装

**壁纸源：**
1. 下载 `.ltws` 文件到临时目录
2. 调用 `WallpaperSourceManager.import_source()`
3. 自动启用并刷新列表

**主题和插件：**
1. 下载文件到 `CACHE_DIR/store_downloads/`
2. 当前仅提示下载完成
3. 安装逻辑待后续实现

## 集成点

### 导航系统

商店页面通过 `AppNavigationView` 注册到核心插件：
```python
AppNavigationView(
    id="store",
    label="商店",
    icon=ft.Icons.STORE_OUTLINED,
    selected_icon=ft.Icons.STORE,
    content=pages.store,
)
```

### 设置页面

在"资源"标签添加商店源配置区域：
- 自定义源开关
- URL输入框
- 重置按钮

### 壁纸源管理器

使用现有的 `WallpaperSourceManager` 导入壁纸源：
```python
record = self._wallpaper_source_manager.import_source(temp_file)
```

## 扩展性

### 添加新资源类型

1. 在 `models.py` 扩展 `ResourceMetadata.type`
2. 在 `ui.py` 添加标签页
3. 实现安装处理器

### 自定义UI

继承 `StoreUI` 类并重写方法：
- `_build_resource_card()`: 自定义卡片样式
- `_show_resource_detail()`: 自定义详情对话框

### 添加过滤器

在 `StoreUI` 中添加：
- 搜索框
- 标签筛选
- 排序选项

## 依赖关系

```
app/store/
├── models.py (无依赖)
├── service.py (依赖: aiohttp, rtoml, loguru, models)
├── ui.py (依赖: flet, service, models, settings)
└── __init__.py

app/core/pages.py
└── 依赖: app/store, app/wallpaper_sources

src/plugins/core.py
└── 依赖: app/core/pages
```

## 性能考虑

1. **并发加载**：使用 `asyncio.as_completed()` 并发获取多个资源元数据
2. **图片懒加载**：仅在需要时加载图标
3. **缓存**：考虑后续添加本地缓存减少网络请求

## 安全考虑

1. **URL验证**：应验证自定义源URL格式
2. **文件验证**：下载后验证文件类型和大小
3. **SHA256校验**：支持资产SHA256校验（已在模型中）

## 测试策略

1. **单元测试**：测试数据模型和服务方法
2. **集成测试**：测试UI与服务交互
3. **端到端测试**：测试完整的安装流程

## 已知限制

1. 主题和插件安装需要重启应用（待实现热加载）
2. 不支持资源更新通知
3. 不支持搜索和筛选
4. 没有资源评分和评论功能

## 未来改进

- [ ] 实现主题应用逻辑
- [ ] 实现插件热加载
- [ ] 添加搜索和筛选
- [ ] 资源本地缓存
- [ ] 更新检查和通知
- [ ] 下载进度显示
- [ ] 多语言支持
- [ ] 资源评分和反馈

## 相关文档

- [商店使用指南](store.md)
- [模块README](../src/app/store/README.md)
- [插件开发文档](plugin_dev.md)
- [主题开发文档](themes.md)
