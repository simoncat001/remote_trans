#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试脚本：解析.bcf文件的元数据
"""

import sys
import os
import struct
from pathlib import Path

def parse_bcf_metadata(file_path):
    """解析.bcf文件的元数据"""
    path = Path(file_path)
    
    if not path.exists():
        print(f"错误：文件不存在: {file_path}")
        return None
    
    print(f"正在解析文件: {file_path}")
    print(f"文件大小: {path.stat().st_size} 字节")
    
    try:
        # 方法1: 检查文件的二进制内容
        print("\n1. 检查文件的二进制内容...")
        with open(path, 'rb') as f:
            # 读取文件头
            header = f.read(1024)
            
            print("\n文件头的十六进制表示 (前128字节):")
            for i in range(0, min(128, len(header)), 16):
                chunk = header[i:i+16]
                hex_str = ' '.join(f'{b:02x}' for b in chunk)
                ascii_str = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in chunk)
                print(f'{i:04x}: {hex_str:<48} | {ascii_str}')
            
            # 查找文本字符串
            print("\n2. 搜索文件中的可读文本字符串...")
            f.seek(0)
            content = f.read(100000)  # 只读取前100KB进行分析
            
            # 尝试找到UTF-8编码的文本段
            import re
            # 查找连续的ASCII文本（长度至少为5）
            ascii_texts = re.findall(b'[\x20-\x7e]{5,}', content)
            
            print(f"找到 {len(ascii_texts)} 个ASCII文本段")
            print("\n前20个文本段:")
            for i, text in enumerate(ascii_texts[:20]):
                try:
                    decoded = text.decode('ascii')
                    print(f"  {i+1}: {decoded}")
                except:
                    pass
            
            # 方法2: 尝试将整个文件作为二进制数据进行分析
            print("\n3. 分析文件的二进制结构...")
            
            # 检查文件是否有特定的文件头标记
            magic_numbers = {
                b'CBF': 'CBF文件格式',
                b'PNG': 'PNG图像',
                b'GIF': 'GIF图像',
                b'JFIF': 'JPEG图像',
                b'RIFF': 'RIFF容器格式',
                b'BM': 'BMP图像',
                b'PDF': 'PDF文档',
                b'ZIP': 'ZIP压缩文件',
                b'PK': 'PKZIP压缩文件'
            }
            
            print("\n文件头识别:")
            for magic, description in magic_numbers.items():
                if header.startswith(magic):
                    print(f"  找到匹配: {description}")
            
            # 检查是否包含XML或JSON结构
            if b'<?xml' in content or b'<root>' in content:
                print("  可能包含XML结构")
            if b'{' in content and b'}' in content:
                print("  可能包含JSON结构")
            
            return {"analysis_complete": True}
            
    except Exception as e:
        print(f"\n解析过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    # 如果提供了命令行参数，则使用该参数作为文件路径
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    else:
        # 默认使用用户提到的文件（使用绝对路径）
        file_path = os.path.abspath("data/SEM/1.bcf")
    
    # 解析文件
    metadata = parse_bcf_metadata(file_path)
    
    if metadata:
        print("\n解析成功!")
    else:
        print("\n解析失败!")
