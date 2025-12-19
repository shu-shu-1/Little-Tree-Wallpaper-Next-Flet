"""Plugin manager implementation."""

from __future__ import annotations

import ast
import importlib
import importlib.util
import shutil
import sys
import tempfile
import zipfile
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from loguru import logger

from .base import Plugin, PluginContext, PluginManifest
from .config import PluginConfigStore
from .permissions import (
    KNOWN_PERMISSIONS,
    PermissionState,
    PluginPermission,
    ensure_permission_states,
)
from .runtime import PluginRuntimeInfo, PluginStatus


@dataclass(slots=True)
class LoadedPlugin:
    identifier: str
    plugin: Plugin
    manifest: PluginManifest
    module: ModuleType | None = None
    module_name: str | None = None
    source_path: Path | None = None
    builtin: bool = False


@dataclass(slots=True)
class PluginImportResult:
    destination: Path
    identifier: str | None
    manifest: PluginManifest | None
    requested_permissions: tuple[str, ...] = tuple()
    module_name: str | None = None
    error: str | None = None


class PluginManager:
    """Responsible for discovering and activating plugins."""

    _IMPORT_WHITELIST: set[str] = {"flet", "datetime", "time", "json"}
    _IMPORT_WHITELIST_PREFIXES: tuple[str, ...] = ("app.plugins",)

    def __init__(
        self,
        search_paths: Iterable[Path],
        config_store: PluginConfigStore,
        package_prefix: str = "plugins",
        builtin_identifiers: Iterable[str] | None = None,
    ):
        self._search_paths: list[Path] = [Path(p) for p in search_paths]
        self._package_prefix = package_prefix
        self._config = config_store
        self._builtin_ids: set[str] = set(builtin_identifiers or [])
        self._loaded: list[LoadedPlugin] = []
        self._runtime: dict[str, PluginRuntimeInfo] = {}

    @staticmethod
    def _states_to_bool(states: dict[str, PermissionState]) -> dict[str, bool]:
        return {key: state == PermissionState.GRANTED for key, state in states.items()}

    @property
    def loaded_plugins(self) -> list[LoadedPlugin]:
        return list(self._loaded)

    @property
    def runtime_info(self) -> list[PluginRuntimeInfo]:
        return list(self._runtime.values())

    def reset(self) -> None:
        self._loaded.clear()
        self._runtime.clear()

    def is_builtin(self, identifier: str) -> bool:
        return identifier in self._builtin_ids

    def register(
        self, plugin: Plugin, manifest: PluginManifest, module: ModuleType | None = None,
    ) -> None:
        self._loaded.append(LoadedPlugin(plugin=plugin, manifest=manifest, module=module))

    def discover(self) -> None:
        self._loaded.clear()
        self._runtime.clear()
        found_identifiers: set[str] = set()

        for path in self._search_paths:
            if not path.exists():
                continue
            for entry in sorted(path.iterdir()):
                if entry.name.startswith("_"):
                    continue
                if entry.is_file() and entry.suffix != ".py":
                    continue

                module_name = entry.stem if entry.is_file() else entry.name
                import_name = f"{self._package_prefix}.{module_name}"

                try:
                    module = importlib.import_module(import_name)
                except Exception as exc:  # pragma: no cover - import errors logged for diagnosis
                    identifier = module_name
                    logger.error(f"插件模块导入失败 {import_name}: {exc}")
                    config_entry = self._config.register_plugin(
                        identifier,
                        default_enabled=False,
                        source={"type": "module", "module": module_name, "path": str(entry)},
                        permissions={},
                    )
                    permissions_state = config_entry.permissions
                    self._runtime[identifier] = PluginRuntimeInfo(
                        identifier=identifier,
                        manifest=None,
                        enabled=config_entry.enabled,
                        status=PluginStatus.FAILED,
                        error=str(exc),
                        source_path=entry,
                        builtin=False,
                        permissions_granted=self._states_to_bool(permissions_state),
                        permission_states=permissions_state,
                        module_name=module_name,
                    )
                    found_identifiers.add(identifier)
                    continue

                plugin = getattr(module, "PLUGIN", None)
                if plugin is None:
                    logger.warning(
                        f"插件模块 {import_name} 未提供 PLUGIN 实例，已跳过",
                    )
                    identifier = module_name
                    config_entry = self._config.register_plugin(
                        identifier,
                        default_enabled=False,
                        source={"type": "module", "module": module_name, "path": str(entry)},
                        permissions={},
                    )
                    permissions_state = config_entry.permissions
                    module_file = getattr(module, "__file__", None) or entry
                    self._runtime[identifier] = PluginRuntimeInfo(
                        identifier=identifier,
                        manifest=None,
                        enabled=config_entry.enabled,
                        status=PluginStatus.FAILED,
                        error="缺少 PLUGIN 实例",
                        source_path=Path(module_file),
                        builtin=False,
                        permissions_granted=config_entry.permissions,
                        module_name=module_name,
                    )
                    found_identifiers.add(identifier)
                    continue

                manifest = getattr(plugin, "manifest", None)
                if not isinstance(manifest, PluginManifest):
                    logger.error(
                        f"插件 {import_name} 缺少 manifest 或类型错误，已跳过",
                    )
                    identifier = module_name
                    config_entry = self._config.register_plugin(
                        identifier,
                        default_enabled=False,
                        source={"type": "module", "module": module_name, "path": str(entry)},
                        permissions={},
                    )
                    module_file = getattr(module, "__file__", None) or entry
                    self._runtime[identifier] = PluginRuntimeInfo(
                        identifier=identifier,
                        manifest=None,
                        enabled=config_entry.enabled,
                        status=PluginStatus.FAILED,
                        error="manifest 缺失或类型错误",
                        source_path=Path(module_file),
                        builtin=False,
                        permissions_granted=self._states_to_bool(permissions_state),
                        permission_states=permissions_state,
                        module_name=module_name,
                    )
                    found_identifiers.add(identifier)
                    continue

                identifier = manifest.identifier
                if identifier in found_identifiers:
                    logger.error(f"检测到重复的插件标识符 {identifier}，已跳过 {import_name}")
                    continue

                module_path = Path(getattr(module, "__file__", entry)) if getattr(module, "__file__", None) else entry
                is_builtin = identifier in self._builtin_ids
                try:
                    dependency_specs = manifest.dependency_specs()
                except ValueError as exc:
                    logger.error(
                        "插件 {identifier} 依赖声明错误: {error}",
                        identifier=manifest.identifier,
                        error=str(exc),
                    )
                    dependency_specs = tuple()

                current_states = ensure_permission_states(
                    manifest.permissions,
                    self._config.get_permissions(identifier),
                )
                config_entry = self._config.register_plugin(
                    identifier,
                    default_enabled=True if is_builtin else True,
                    source={
                        "type": "builtin" if is_builtin else "module",
                        "module": module_name,
                        "path": str(module_path),
                    },
                    permissions={k: v.value for k, v in current_states.items()},
                )
                enabled = config_entry.enabled
                permission_states = ensure_permission_states(
                    manifest.permissions, config_entry.permissions,
                )

                runtime_status = PluginStatus.DISABLED
                pending_permissions: list[str] = []
                if enabled:
                    pending_permissions = [
                        perm
                        for perm, state in permission_states.items()
                        if state is not PermissionState.GRANTED
                    ]
                    runtime_status = PluginStatus.LOADED
                self._runtime[identifier] = PluginRuntimeInfo(
                    identifier=identifier,
                    manifest=manifest,
                    enabled=enabled,
                    status=runtime_status,
                    error=None,
                    source_path=module_path,
                    builtin=is_builtin,
                    permissions_required=manifest.permissions,
                    permissions_granted=self._states_to_bool(permission_states),
                    permission_states=permission_states,
                    permissions_pending=tuple(pending_permissions),
                    module_name=module_name,
                    plugin_type=manifest.kind,
                    dependencies=dependency_specs,
                )

                if enabled and self._runtime[identifier].status == PluginStatus.LOADED:
                    self._loaded.append(
                        LoadedPlugin(
                            identifier=identifier,
                            plugin=plugin,
                            manifest=manifest,
                            module=module,
                            module_name=module_name,
                            source_path=module_path,
                            builtin=is_builtin,
                        ),
                    )

                found_identifiers.add(identifier)

        # Any plugins present in config but not found on disk should be marked accordingly
        for identifier, entry in self._config.all_plugins().items():
            if identifier in found_identifiers:
                continue
            source = entry.source
            source_path = Path(source.get("path")) if source.get("path") else None
            builtin = source.get("type") == "builtin"
            permissions_state = entry.permissions
            self._runtime[identifier] = PluginRuntimeInfo(
                identifier=identifier,
                manifest=None,
                enabled=entry.enabled,
                status=PluginStatus.FAILED,
                error="插件文件未找到",
                source_path=source_path,
                builtin=builtin,
                permissions_required=tuple(),
                permissions_granted=self._states_to_bool(permissions_state),
                permission_states=permissions_state,
                module_name=source.get("module"),
            )

        self._evaluate_dependencies()

    def _evaluate_dependencies(self) -> None:
        manifest_versions: dict[str, str] = {}
        for identifier, runtime in self._runtime.items():
            if runtime.manifest:
                manifest_versions[identifier] = runtime.manifest.version

        for identifier, runtime in self._runtime.items():
            issues: dict[str, str] = {}
            for spec in runtime.dependencies:
                dep_runtime = self._runtime.get(spec.identifier)
                if dep_runtime is None or dep_runtime.manifest is None:
                    issues[spec.identifier] = "依赖插件未安装"
                    continue
                if not dep_runtime.enabled or dep_runtime.status not in {
                    PluginStatus.LOADED,
                    PluginStatus.ACTIVE,
                }:
                    issues[spec.identifier] = f"依赖插件 {spec.identifier} 未启用或无法加载"
                    continue
                dep_version = manifest_versions.get(spec.identifier)
                if not spec.is_satisfied_by(dep_version):
                    required = spec.describe()
                    current = dep_version or "?"
                    issues[spec.identifier] = f"需要 {required}，当前 {current}"
            runtime.dependency_issues = issues
            if issues and runtime.status == PluginStatus.LOADED:
                runtime.status = PluginStatus.MISSING_DEPENDENCY
                runtime.error = "; ".join(issues.values())
                logger.warning(
                    "插件 {identifier} 依赖未满足: {issues}",
                    identifier=identifier,
                    issues=runtime.error,
                )

        self._loaded = [
            loaded
            for loaded in self._loaded
            if self._runtime.get(loaded.identifier) and self._runtime[loaded.identifier].status == PluginStatus.LOADED
        ]

    def _compute_activation_order(self) -> list[LoadedPlugin]:
        if not self._loaded:
            return []
        available = {loaded.identifier: loaded for loaded in self._loaded}
        in_degree: dict[str, int] = dict.fromkeys(available, 0)
        dependents: dict[str, set[str]] = {identifier: set() for identifier in available}

        for identifier, loaded in available.items():
            runtime = self._runtime.get(identifier)
            if not runtime:
                continue
            deps = [spec.identifier for spec in runtime.dependencies if spec.identifier in available]
            in_degree[identifier] = len(deps)
            for dep in deps:
                dependents.setdefault(dep, set()).add(identifier)

        queue = deque([identifier for identifier, degree in in_degree.items() if degree == 0])
        ordered: list[str] = []
        while queue:
            current = queue.popleft()
            ordered.append(current)
            for dependent in dependents.get(current, set()):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(ordered) != len(available):
            logger.warning("检测到插件依赖循环，使用默认加载顺序")
            return list(self._loaded)
        return [available[identifier] for identifier in ordered]

    def activate_all(
        self,
        context_factory: Callable[[Plugin, PluginManifest], PluginContext],
    ) -> None:
        activation_order = self._compute_activation_order()

        for loaded in activation_order:
            runtime = self._runtime.get(loaded.identifier)
            try:
                context = context_factory(loaded.plugin, loaded.manifest)
            except Exception as exc:
                name = loaded.manifest.identifier if loaded.manifest else (loaded.module_name or loaded.identifier)
                logger.error(
                    f"构建插件上下文失败 {name}: {exc}",
                )
                if runtime:
                    runtime.status = PluginStatus.ERROR
                    runtime.error = str(exc)
                continue

            try:
                loaded.plugin.activate(context)
                logger.info(
                    f"插件 {loaded.manifest.identifier if loaded.manifest else loaded.identifier} ({loaded.manifest.short_label() if loaded.manifest else ''}) 已激活",
                )
                if runtime:
                    runtime.status = PluginStatus.ACTIVE
                    runtime.error = None
            except Exception as exc:
                logger.error(
                    f"插件 {loaded.manifest.identifier if loaded.manifest else loaded.identifier} 激活失败: {exc}",
                )
                if runtime:
                    runtime.status = PluginStatus.ERROR
                    runtime.error = str(exc)

    # ------------------------------------------------------------------
    # management helpers
    # ------------------------------------------------------------------
    def set_enabled(self, identifier: str, enabled: bool) -> None:
        self._config.set_enabled(identifier, enabled)

    def update_permission(
        self, identifier: str, permission: str, allowed: bool | PermissionState | None,
    ) -> None:
        if isinstance(allowed, PermissionState):
            state = allowed
        elif allowed is None:
            state = PermissionState.PROMPT
        else:
            state = PermissionState.GRANTED if allowed else PermissionState.DENIED
        self._config.set_permission_state(identifier, permission, state)

    def delete_plugin(self, identifier: str) -> None:
        runtime = self._runtime.get(identifier)
        if runtime is None:
            logger.warning(f"尝试删除未知插件 {identifier}")
            self._config.remove_plugin(identifier)
            return
        if runtime.builtin:
            raise ValueError("内置插件无法删除")
        dependents = [
            info.identifier
            for info in self._runtime.values()
            if info.manifest and any(spec.identifier == identifier for spec in info.dependencies)
        ]
        if dependents:
            raise ValueError(
                f"以下插件依赖于 {identifier}，请先卸载依赖项：{', '.join(sorted(dependents))}",
            )
        path = runtime.source_path
        if path and path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            if path.is_file():
                pycache_dir = path.with_name("__pycache__")
                if pycache_dir.exists() and pycache_dir.is_dir():
                    module_name = path.stem
                    for cached in list(pycache_dir.iterdir()):
                        if cached.stem.startswith(module_name):
                            try:
                                cached.unlink()
                            except OSError:
                                pass
                # 如果源路径是文件，额外尝试删除其所在目录（用户插件目录）
                parent_dir = path.parent
                for root in self._search_paths:
                    try:
                        parent_dir.relative_to(root)
                    except ValueError:
                        continue
                    if parent_dir.exists():
                        shutil.rmtree(parent_dir, ignore_errors=True)
                    break
        self._config.remove_plugin(identifier)
        self._runtime.pop(identifier, None)
        self._loaded = [plugin for plugin in self._loaded if plugin.identifier != identifier]
        module_name = runtime.module_name
        if module_name:
            self_module = f"{self._package_prefix}.{module_name}"
            sys.modules.pop(self_module, None)
        importlib.invalidate_caches()

    def import_plugin(self, source_path: Path) -> PluginImportResult:
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(source)

        target_root = self._search_paths[0]
        target_root.mkdir(parents=True, exist_ok=True)

        # 归一化目标目录名
        sanitized = "".join(
            ch if ch.isalnum() or ch == "_" else "_" for ch in source.stem
        ).strip("_") or "plugin"
        candidate = sanitized
        counter = 1
        while (target_root / candidate).exists():
            candidate = f"{sanitized}_{counter}"
            counter += 1

        destination_dir = target_root / candidate
        destination_dir.mkdir(parents=True, exist_ok=False)

        temp_dir: Path | None = None
        module_name = destination_dir.name

        def _cleanup() -> None:
            try:
                if temp_dir and temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
            finally:
                importlib.invalidate_caches()

        try:
            payload_root: Path
            main_file: Path | None = None

            if source.is_file() and source.suffix.lower() == ".zip":
                temp_dir_obj = tempfile.TemporaryDirectory()
                temp_dir = Path(temp_dir_obj.name)
                with zipfile.ZipFile(source, "r") as zf:
                    zf.extractall(temp_dir)

                entries = [p for p in temp_dir.iterdir() if not p.name.startswith("__MACOSX")]
                if len(entries) == 1 and entries[0].is_dir():
                    payload_root = entries[0]
                else:
                    payload_root = temp_dir

                shutil.copytree(payload_root, destination_dir, dirs_exist_ok=True)
            elif source.is_file():
                # 普通 .py 文件：包装为包目录
                shutil.copy2(source, destination_dir / source.name)
            else:
                raise ValueError("仅支持导入 .py 或 .zip 插件包")

            # 确保存在入口 __init__.py
            candidates = list(destination_dir.glob("*.py")) + list(destination_dir.rglob("__init__.py"))
            if not candidates:
                raise ValueError("未找到插件 Python 文件，请确认压缩包内容")
            # 优先 __init__.py 作为入口
            main_file = next((p for p in candidates if p.name == "__init__.py"), None)
            if main_file is None:
                main_file = next((p for p in candidates if p.stem.lower() in {"plugin", "main"}), candidates[0])
                # 写一个 __init__.py 将入口暴露为包
                init_path = destination_dir / "__init__.py"
                init_path.write_text(
                    f"from .{main_file.stem} import *\n",
                    encoding="utf-8",
                )
            elif not main_file.samefile(destination_dir / "__init__.py"):
                # 确保包入口存在
                init_path = destination_dir / "__init__.py"
                if not init_path.exists():
                    init_path.write_text(
                        f"from .{main_file.stem} import *\n",
                        encoding="utf-8",
                    )

            importlib.invalidate_caches()

            manifest: PluginManifest | None = None
            identifier: str | None = None
            requested_permissions: set[str] = set()
            error: str | None = None

            import_permissions = self._derive_import_permissions(
                self._collect_import_modules(destination_dir / "__init__.py"),
            )
            requested_permissions.update(import_permissions)

            import_name = f"{self._package_prefix}.{module_name}"
            module = importlib.import_module(import_name)
            plugin = getattr(module, "PLUGIN", None)
            plugin_manifest = getattr(plugin, "manifest", None)
            if isinstance(plugin_manifest, PluginManifest):
                manifest = plugin_manifest
                identifier = manifest.identifier
                requested_permissions.update(manifest.permissions or tuple())

                if identifier in self._runtime:
                    raise ValueError(f"插件标识符 {identifier} 已存在，请先删除后再导入。")

                module_file = getattr(module, "__file__", None) or (destination_dir / "__init__.py")
                module_path = Path(module_file)
                is_builtin = self.is_builtin(identifier)

                try:
                    dependency_specs = manifest.dependency_specs()
                except ValueError as dep_exc:
                    logger.error(
                        "插件 {identifier} 依赖声明错误: {error}",
                        identifier=manifest.identifier,
                        error=str(dep_exc),
                    )
                    dependency_specs = tuple()

                permission_states = ensure_permission_states(
                    manifest.permissions,
                    self._config.get_permissions(identifier),
                )

                # 对于用户安装的插件，记录整个目录作为源路径，便于卸载时删除干净
                source_path = module_path if is_builtin else destination_dir

                config_entry = self._config.register_plugin(
                    identifier,
                    default_enabled=True if is_builtin else False,
                    source={
                        "type": "builtin" if is_builtin else "module",
                        "module": module_name,
                        "path": str(source_path),
                    },
                    permissions={k: v.value for k, v in permission_states.items()},
                )

                if not is_builtin and config_entry.enabled:
                    self._config.set_enabled(identifier, False)
                    config_entry.enabled = False

                permission_states = ensure_permission_states(
                    manifest.permissions,
                    self._config.get_permissions(identifier),
                )

                pending_permissions = [
                    perm
                    for perm, state in permission_states.items()
                    if state is not PermissionState.GRANTED
                ]

                self._runtime[identifier] = PluginRuntimeInfo(
                    identifier=identifier,
                    manifest=manifest,
                    enabled=config_entry.enabled,
                    status=PluginStatus.DISABLED if not config_entry.enabled else PluginStatus.LOADED,
                    error=None,
                    source_path=source_path,
                    builtin=is_builtin,
                    permissions_required=manifest.permissions,
                    permissions_granted=self._states_to_bool(permission_states),
                    permission_states=permission_states,
                    permissions_pending=tuple(pending_permissions),
                    module_name=module_name,
                    plugin_type=manifest.kind,
                    dependencies=dependency_specs,
                )

                # Newly imported plugins shouldn't be considered loaded yet
                if identifier in {plugin.identifier for plugin in self._loaded}:
                    self._loaded = [
                        loaded
                        for loaded in self._loaded
                        if loaded.identifier != identifier
                    ]

                self._evaluate_dependencies()
            else:
                error = "插件未提供 manifest 或 PLUGIN"

        except Exception:
            # 清理已创建的目录
            shutil.rmtree(destination_dir, ignore_errors=True)
            _cleanup()
            raise

        _cleanup()

        return PluginImportResult(
            destination=destination_dir,
            identifier=locals().get("identifier"),
            manifest=locals().get("manifest"),
            requested_permissions=tuple(sorted(locals().get("requested_permissions", set()))),
            module_name=module_name,
            error=locals().get("error"),
        )

    def get_runtime(self, identifier: str) -> PluginRuntimeInfo | None:
        return self._runtime.get(identifier)

    def has_pending_changes(self) -> bool:
        """当存在需要重新加载的配置更改时，返回True。

        我们将持久化配置（启用/权限状态）与内存中的运行时信息进行比较，以确定是否确实需要重新加载。
        """
        try:
            for identifier, runtime in self._runtime.items():
                try:
                    cfg_enabled = self._config.is_enabled(identifier)
                except Exception:
                    cfg_enabled = True
                # 根据runtime.status考虑当前*已应用*的启用状态
                #（ACTIVE/LOADED => 已应用启用，DISABLED => 已应用禁用）。
                applied_enabled = getattr(runtime, "status", None) is not None and runtime.status != PluginStatus.DISABLED
                if bool(applied_enabled) != bool(cfg_enabled):
                    return True
                try:
                    cfg_perms = self._config.get_permissions(identifier)
                except Exception:
                    cfg_perms = {}
                # 标准化键和值：若任何权限状态不同，则需要重新加载
                for perm, state in runtime.permission_states.items():
                    cfg_state = cfg_perms.get(perm)
                    if cfg_state is None:
                        if state is not None and state.value != "prompt":
                            return True
                    elif getattr(cfg_state, "value", cfg_state) != getattr(state, "value", state):
                        return True
            return False
        except Exception:
            # Defensive: if inspection fails, assume no pending changes to avoid false positives
            return False

    @staticmethod
    def _collect_import_modules(file_path: Path) -> set[str]:
        try:
            source = file_path.read_text(encoding="utf-8")
        except OSError:
            return set()
        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError:
            return set()

        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name:
                        modules.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    continue
                if node.module:
                    modules.add(node.module)
        return modules

    def _derive_import_permissions(self, modules: Iterable[str]) -> set[str]:
        permissions: set[str] = set()
        for module in modules:
            normalized = module.strip()
            if not normalized:
                continue
            if self._is_import_allowed(normalized):
                continue
            root = normalized.split(".")[0]
            if self._is_import_allowed(root):
                continue
            permission_id = f"python_import:{root}"
            if permission_id not in KNOWN_PERMISSIONS:
                KNOWN_PERMISSIONS[permission_id] = PluginPermission(
                    identifier=permission_id,
                    name=f"使用库 {root}",
                    description=f"允许插件导入额外的 Python 库 {root}。",
                )
            permissions.add(permission_id)
        return permissions

    @classmethod
    def _is_import_allowed(cls, module: str) -> bool:
        if not module:
            return True
        candidate = module.strip()
        if not candidate:
            return True
        if candidate in cls._IMPORT_WHITELIST:
            return True
        for prefix in cls._IMPORT_WHITELIST_PREFIXES:
            if candidate == prefix or candidate.startswith(prefix + "."):
                return True
        root = candidate.split(".")[0]
        if root in cls._IMPORT_WHITELIST:
            return True
        try:
            spec = importlib.util.find_spec(root)
        except (ImportError, ValueError):  # pragma: no cover - defensive
            spec = None
        if spec is None:
            return False
        origin = getattr(spec, "origin", None)
        if origin in {None, "built-in", "frozen"}:
            return True
        origin_str = str(origin).lower()
        if "site-packages" in origin_str or "dist-packages" in origin_str:
            return False
        return True
