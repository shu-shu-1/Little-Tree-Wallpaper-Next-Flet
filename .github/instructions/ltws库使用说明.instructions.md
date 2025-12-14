---
applyTo: '**'
---

# LTWS 解析器使用文档

本指南聚焦如何使用 `ltws-parser` 的类、方法、参数、返回值和报错处理，帮助在代码与 CLI 中解析、验证、打包 LTWS v3.0 壁纸源。

已适配协议关键点（v3.0 新版）：
- `source.toml` 支持用 `categories` / `config` 指向任意相对路径（不再强制根目录 `categories.toml` / `config.toml`）
- `identifier` 规则按协议放宽：仅小写字母/数字/点/下划线，且至少包含一个点（反向域名风格）
- 变量函数参数支持协议示例的冒号分隔：`{{random_int:1:10}}`（同时兼容旧的逗号分隔）
- JSON Pointer 路径支持 `*` 与 `**` 通配（`json_pointer_get`）

## 安装

```bash
pip install ltws-parser
# 或源码安装
git clone https://github.com/shu-shu-1/ltws-parser.git
cd ltws-parser && pip install -e .
```

## 核心类与方法

### LTWSParser
- 用途：解析目录或 `.ltws`（未压缩 TAR）为 `WallpaperSource`。
- 初始化：`LTWSParser(strict=True)`（strict=True 时解析/验证出错直接抛异常）。
- 方法：
    - `parse(path: str) -> WallpaperSource`
    - `get_errors() -> List[str]`
    - `get_warnings() -> List[str]`
- 常见异常：`FileNotFoundError`, `InvalidSourceError`, `ParseError`, `ValidationError`, `WallpaperSourceError`。

示例：
```python
from ltws import LTWSParser
parser = LTWSParser(strict=True)
source = parser.parse("my_source.ltws")  # 或目录
```

### LTWSValidator
- 用途：在已解析的 `WallpaperSource` 上做深度校验（字段格式、图标、映射等）。
- 方法：
    - `validate_source(source: WallpaperSource) -> bool`
    - `get_validation_report() -> { errors: List[str], warnings: List[str], passed: bool }`
    - `get_errors() / get_warnings()`
- 校验要点（库内置）：
    - 元数据：scheme/identifier/name/version 规范
    - 分类：ID 唯一、图标格式
    - API：名称长度、分类引用存在、logo 与 `category_icons` 图标格式
    - 请求：URL 必须 http(s)，method 仅 GET/POST，超时建议区间
    - 映射：单图/多图互斥，多图需 `item_mapping` 且含 `image`

示例：
```python
from ltws import LTWSValidator
validator = LTWSValidator()
ok = validator.validate_source(source)
print(validator.get_validation_report())
```

### LTWSPackager
- 用途：将目录打包为 `.ltws`（并生成 manifest）；提供解包辅助。
- 初始化：`LTWSPackager(strict=True)`（strict 时发现违规立即抛错）。
- 方法：
    - `pack(source_dir: str, output_file: str, overwrite: bool=False) -> str`
    - `unpack(...)` 若需要可参考 CLI `ltws unpack`（如未暴露可自行用 `tarfile`）。
- 额外检查：缺少必需文件、`apis` 空、存在本地资源文件（png/jpg/svg/ico/ttf 等）、图标引用本地路径、体积超限的 TOML 提示警告。

### VariableEngine
- 用途：模板变量替换（时间、随机、屏幕、URL 编码、自定义函数）。
- 方法：
    - `replace(template: str, context: Dict[str, Any]=None) -> str`
    - `register_variable(name, value)` / `register_function(name, func)`
    - `create_context(**kwargs)`（提供屏幕等默认值）
- 内置函数：`timestamp_ms`, `timestamp_s`, `date_iso`, `date_cn`, `year/month/day/hour/minute/second`, `random_string`, `random_int`, `random_hex`, `url_encode`, `uuid`。

参数分隔符说明：
- 推荐（协议示例）：冒号分隔，例如 `{{random_string:8}}`、`{{random_int:1:10}}`
- 兼容：逗号分隔，例如 `{{random_int:1,10}}`

示例：
```python
from ltws import VariableEngine
engine = VariableEngine()
print(engine.replace("{{date_iso}}-{{random_string:6}}"))
```

### 数据模型概要
- `WallpaperSource`: metadata/config/categories/apis, `source_path`, `loaded_at`；帮助方法 `get_api_by_name`、`get_category_by_id`。
- `WallpaperAPI`: `name/description/logo/categories/category_icons/parameters/request/response/mapping/validation/error_handling/cache`；`category_icons` 为 {category_id: icon}。
- `Category`: `id/name/category/subcategory/subsubcategory/icon/description`。
- `Parameter`: `key/type/label/default/choices/hidden/...`；`type` 取 `choice|text|boolean`。
- `RequestConfig`: `url/method/timeout_seconds/interval_seconds/max_concurrent/skip_ssl_verify/user_agent/headers/body`。
- `FieldMapping`: 单图字段（image/title/description...）或多图 `items + item_mapping`（必须含 image），二者互斥。

## CLI 速查（安装后有 `ltws`）

```bash
ltws validate path            # 验证目录或 .ltws；支持 --no-strict, -v
ltws pack src_dir out.ltws    # 打包；支持 --overwrite
ltws inspect file.ltws        # 查看清单
ltws unpack file.ltws out_dir # 解包
# 额外脚本：python scripts/ltws-cli.py / ltws-gui.py 亦可使用
```

## 最小示例（与协议路径字段一致）

仓库内置了一个最小 v3 示例：`examples/v3_min_source/`，其 `source.toml` 使用：
- `categories = "categories/custom_categories.toml"`
- `apis = ["apis/*.toml"]`

你可以直接验证与打包：

```bash
ltws validate examples/v3_min_source
ltws pack examples/v3_min_source examples/v3_min_source.ltws --overwrite
ltws validate examples/v3_min_source.ltws
```

## 代码范例

### 解析 + 验证 + 报告
```python
from ltws import LTWSParser, LTWSValidator

parser = LTWSParser(strict=False)
source = parser.parse("examples/source.ltws")

validator = LTWSValidator()
if not validator.validate_source(source):
        print("errors", validator.get_errors())
        print("warnings", validator.get_warnings())
```

### 打包 + 检查
```python
from ltws import LTWSPackager

packager = LTWSPackager(strict=True)
packager.pack("./my_source", "./my_source.ltws", overwrite=True)
```

## 错误与异常

常用异常类（来自 `ltws.exceptions`）：
- `WallpaperSourceError`: 基类
- `FileNotFoundError`: 必需文件缺失
- `InvalidSourceError`: 协议/结构不符合（含 scheme/version 等）
- `ParseError`: TOML/文件解析失败
- `ValidationError`: 校验未通过
- `PackagingError`: 打包过程失败

排查建议：
- 解析阶段用 `parser.get_errors()/get_warnings()` 查看汇总。
- 校验阶段用 `validator.get_validation_report()`。
- 打包失败通常与缺文件、含本地资源或重复/非法图标引用有关。

## FAQ（针对库使用）
- **如何在 API 上为不同分类指定图标？** 在 API 文件写 `category_icons = { cat_id = "data:image/..." }`，解析后 `WallpaperAPI.category_icons` 可见，验证器会检查分类存在与图标格式。
- **静态响应是否必须 request？** `response.format` 为 `static_list/static_dict` 时可省略 `request`，验证器会自动放行并给空映射。
- **如何自定义变量函数？** `engine.register_function("md5", lambda s: ...)` 后即可在模板用 `{{md5:xxx}}`。

## 映射路径补充（通配 JSON Pointer）

当 `response.format = "json"` 时，映射路径通常使用 JSON Pointer，例如：
- `/data/items/0/url`
- `/data/items/*/url`（`*` 匹配一层）
- `/**/url`（`**` 匹配任意深度）

注意：`ltws-parser` 的 `json_pointer_get` 在含通配符时返回“列表”，不含通配符时返回“单值”。

## 支持与许可证

MIT 许可证。更多示例与问题反馈请见 GitHub 仓库与 Issues。