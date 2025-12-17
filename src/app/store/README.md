# 商店模块 (Store Module)

商店模块提供主题、壁纸源和插件的在线获取和管理功能。

## 功能概述

- 从官方或自定义源获取资源列表
- 展示资源详情（名称、版本、作者、描述等）
- 下载和安装资源
- 支持自定义商店源URL

## 模块结构

```
store/
├── __init__.py      # 模块导出
├── models.py        # 数据模型定义
├── service.py       # 资源获取服务
├── ui.py            # 商店页面UI
└── README.md        # 本文档
```

## 核心组件

### 数据模型 (`models.py`)

#### `ResourceMetadata`
资源元数据，包含资源的所有信息。

**字段：**
- `type`: 资源类型（`"plugin"` | `"theme"` | `"wallpaper_source"`）
- `id`: 全局唯一ID（反向域名风格）
- `name`: 显示名称
- `version`: 版本号（SemVer）
- `summary`: 一句话简介
- `description_md`: Markdown格式的详细描述
- `icon_*`: 图标相关字段（四选一）
- `download_*`: 下载相关字段
- `author`: 作者信息
- `tags`: 标签列表

**方法：**
- `get_icon()`: 获取图标URL
- `get_download_source()`: 获取下载源

#### `ResourceAuthor`
资源作者信息。

#### `ResourceAsset`
可下载资产条目。

### 服务层 (`service.py`)

#### `StoreService`
商店服务类，负责与远程API交互。

**方法：**
- `list_resources(resource_type)`: 获取资源列表
- `get_resource_metadata(resource_type, filename)`: 获取单个资源元数据
- `get_all_resources(resource_type)`: 获取所有资源元数据
- `resolve_icon_url(metadata)`: 解析图标URL
- `resolve_download_url(metadata)`: 解析下载URL

**默认源：**
```
https://wallpaper.api.zsxiaoshu.cn
```

### UI层 (`ui.py`)

#### `StoreUI`
商店页面UI管理器。

**功能：**
- 三标签页切换（主题/壁纸源/插件）
- 网格布局展示资源卡片
- 资源详情对话框
- 下载和安装处理

## API格式

### 索引文件
每个资源类型都有一个 `index.json` 文件，包含TOML文件名列表。

**URL格式：**
```
{base_url}/{type}/index.json
```

**类型：**
- `theme`: 主题
- `resources`: 壁纸源
- `plugins`: 插件

**示例响应：**
```json
["example_plugin.toml", "another_plugin.toml"]
```

### 元数据文件
每个资源有一个TOML格式的元数据文件。

**URL格式：**
```
{base_url}/{type}/{filename}
```

**TOML格式参考：**
参见问题描述中的元数据规范。

## 使用示例

### 在代码中使用商店服务

```python
from app.store import StoreService
import asyncio

async def main():
    # 创建服务实例
    service = StoreService()
    
    # 获取所有插件
    plugins = await service.get_all_resources("plugins")
    
    for plugin in plugins:
        print(f"{plugin.name} v{plugin.version}")
        print(f"  作者: {plugin.author.name if plugin.author else 'N/A'}")
        print(f"  简介: {plugin.summary}")
        
        # 获取下载URL
        download_url = service.resolve_download_url(plugin)
        if download_url:
            print(f"  下载: {download_url}")
    
    await service.close()

asyncio.run(main())
```

### 使用自定义源

在设置页面的"资源"标签中：
1. 启用"使用自定义源"开关
2. 输入自定义源URL
3. 重新打开商店页面

或在代码中：
```python
service = StoreService(base_url="https://your-custom-source.com")
```

## 配置

商店相关配置存储在应用设置中：

- `store.use_custom_source`: 是否使用自定义源（布尔值）
- `store.custom_source_url`: 自定义源URL（字符串）

## 安装流程

### 壁纸源
1. 从商店下载 `.ltws` 文件
2. 调用 `WallpaperSourceManager.import_source()` 导入
3. 自动启用并刷新列表

### 主题和插件
1. 从商店下载文件（当前为ZIP格式）
2. 保存到 `CACHE_DIR/store_downloads/`
3. 安装逻辑待完善（TODO）

## 扩展和维护

### 添加新字段
在 `models.py` 中的 `ResourceMetadata` 添加字段，并更新 `service.py` 的解析逻辑。

### 支持新的资源类型
1. 在 `models.py` 的 `ResourceMetadata.type` 添加类型
2. 在 `ui.py` 的 `StoreUI` 添加标签页
3. 实现对应的安装处理器

### 自定义UI
继承或修改 `StoreUI` 类来定制商店页面的外观和行为。

## 故障排查

### 资源加载失败
- 检查网络连接
- 验证商店源URL是否正确
- 查看日志了解详细错误信息

### 安装失败
- 确保有足够的磁盘空间
- 检查文件格式是否正确
- 查看日志了解详细错误信息

## 相关文档

- [壁纸源格式](.github/instructions/壁纸源格式.instructions.md)
- [LTWS库使用说明](.github/instructions/ltws库使用说明.instructions.md)
