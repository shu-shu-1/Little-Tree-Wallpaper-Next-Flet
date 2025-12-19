#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单的商店模块测试脚本
"""

import sys
from pathlib import Path

# 添加src到路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_models():
    """测试数据模型"""
    print("测试数据模型...")
    from app.store.models import ResourceMetadata, ResourceAuthor, ResourceAsset
    
    # 创建测试资源
    author = ResourceAuthor(
        name="测试作者",
        email="test@example.com",
        url="https://example.com",
    )
    
    asset = ResourceAsset(
        name="测试资产",
        path="src/test.zip",
    )
    
    resource = ResourceMetadata(
        type="plugin",
        id="com.example.test",
        name="测试插件",
        version="1.0.0",
        summary="这是一个测试插件",
        description_md="## 测试\n\n这是测试内容",
        author=author,
        assets=[asset],
    )
    
    print(f"  ✓ 资源类型: {resource.type}")
    print(f"  ✓ 资源ID: {resource.id}")
    print(f"  ✓ 资源名称: {resource.name}")
    print(f"  ✓ 作者: {resource.author.name}")
    print(f"  ✓ 下载源: {resource.get_download_source()}")
    print("模型测试通过！\n")

def test_service_init():
    """测试服务初始化"""
    print("测试服务初始化...")
    from app.store.service import StoreService
    
    # 创建服务实例
    service = StoreService()
    print(f"  ✓ 默认URL: {service.base_url}")
    
    # 使用自定义URL
    custom_service = StoreService(base_url="https://custom.example.com")
    print(f"  ✓ 自定义URL: {custom_service.base_url}")
    
    print("服务初始化测试通过！\n")

def test_toml_parsing():
    """测试TOML解析"""
    print("测试TOML解析...")
    from app.store.service import StoreService
    import rtoml
    
    # 创建测试TOML内容
    test_toml = """
type = "plugin"
id = "com.example.test"
name = "测试插件"
version = "1.0.0"
summary = "测试摘要"
description_md = "测试描述"

[author]
name = "测试作者"
email = "test@example.com"

[[assets]]
name = "主资产"
path = "src/plugin.zip"
"""
    
    # 解析TOML
    data = rtoml.loads(test_toml)
    print(f"  ✓ 解析成功: {data.get('name')}")
    
    # 使用服务解析
    service = StoreService()
    metadata = service._parse_resource_metadata(data)
    print(f"  ✓ 转换为对象: {metadata.name}")
    print(f"  ✓ 作者: {metadata.author.name if metadata.author else 'N/A'}")
    print(f"  ✓ 资产数量: {len(metadata.assets)}")
    
    print("TOML解析测试通过！\n")

def main():
    """主测试函数"""
    print("=" * 60)
    print("商店模块测试")
    print("=" * 60 + "\n")
    
    try:
        test_models()
        test_service_init()
        test_toml_parsing()
        
        print("=" * 60)
        print("所有测试通过！✓")
        print("=" * 60)
        return 0
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
