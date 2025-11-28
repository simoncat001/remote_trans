#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BCF文件元数据解析器
用于解析SEM（扫描电子显微镜）.bcf文件中的元数据
"""

import argparse
import os
import re
import struct
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

class BCFParser:
    """
    BCF文件解析器，用于从.bcf文件中提取元数据
    """
    
    def __init__(self, file_path: Path):
        """
        初始化BCF解析器
        
        Args:
            file_path: BCF文件路径
        """
        self.file_path = file_path
        self.metadata: Dict[str, Any] = {}
        
    def parse(self) -> Dict[str, Any]:
        """
        解析BCF文件并提取元数据
        
        Returns:
            包含提取的元数据的字典
        """
        print(f"正在解析BCF文件: {self.file_path}")
        print(f"文件大小: {self.file_path.stat().st_size / (1024 * 1024):.2f} MB")
        
        # 尝试多种方法提取元数据
        self._extract_file_info()
        self._search_text_strings()
        self._analyze_binary_structure()
        
        return self.metadata
    
    def _extract_file_info(self):
        """
        提取文件基本信息
        """
        self.metadata['文件信息'] = {
            '文件名': self.file_path.name,
            '文件路径': str(self.file_path),
            '文件大小(MB)': round(self.file_path.stat().st_size / (1024 * 1024), 2),
            '修改时间': self.file_path.stat().st_mtime,
            '创建时间': self.file_path.stat().st_ctime
        }
    
    def _search_text_strings(self):
        """
        搜索文件中的可读文本字符串
        """
        print("\n搜索文件中的可读文本字符串...")
        
        with open(self.file_path, 'rb') as f:
            content = f.read(500000)  # 读取前500KB进行分析
        
        # 方法1: 查找连续的ASCII文本
        ascii_texts = re.findall(b'[\x20-\x7e]{5,}', content)
        
        # 方法2: 查找可能的UTF-8文本
        try:
            utf8_texts = []
            # 尝试不同的编码方式
            for encoding in ['utf-8', 'latin-1', 'cp1252']:
                try:
                    decoded = content.decode(encoding)
                    # 查找可能包含元数据的文本段
                    potential_metadata = re.findall(r'[\w\s\-\.,:;_\(\)/\\]+', decoded)
                    utf8_texts.extend(potential_metadata)
                except:
                    continue
        except:
            utf8_texts = []
        
        # 合并并去重
        all_texts = set()
        for text in ascii_texts:
            try:
                all_texts.add(text.decode('ascii'))
            except:
                pass
        
        all_texts.update(utf8_texts)
        
        # 过滤掉过长或过短的文本
        filtered_texts = [text.strip() for text in all_texts if 5 <= len(text) <= 200]
        
        print(f"找到 {len(filtered_texts)} 个可能的文本段")
        
        # 尝试识别元数据字段
        self._identify_metadata_fields(filtered_texts)
        
        # 保存所有找到的文本（用于调试）
        if len(filtered_texts) > 0:
            self.metadata['识别到的文本段'] = filtered_texts[:50]  # 只保存前50个
    
    def _identify_metadata_fields(self, texts: List[str]):
        """
        尝试从文本中识别元数据字段
        
        Args:
            texts: 可能包含元数据的文本列表
        """
        metadata_fields = {
            '电压': [],
            '电流': [],
            '放大倍数': [],
            '工作距离': [],
            '扫描模式': [],
            '日期': [],
            '时间': [],
            '样品名称': [],
            '操作人员': [],
            '仪器型号': [],
            '其他': []
        }
        
        # 定义元数据字段的模式
        patterns = {
            '电压': [
                r'(\d+(?:\.\d+)?)\s*(kV|KV|V|伏特)',
                r'(加速电压|高压|电压)[:：]?\s*(\d+(?:\.\d+)?)'
            ],
            '电流': [
                r'(\d+(?:\.\d+)?)\s*(nA|NA|μA|uA|mA|MA|A|安|安培)',
                r'(发射电流|电流|束流)[:：]?\s*(\d+(?:\.\d+)?)'
            ],
            '放大倍数': [
                r'(\d+(?:\.\d+)?)\s*[xX×]',
                r'(放大倍数|倍率)[:：]?\s*(\d+(?:\.\d+)?)'
            ],
            '工作距离': [
                r'(\d+(?:\.\d+)?)\s*(mm|MM|m|米)',
                r'(工作距离|WD|wd)[:：]?\s*(\d+(?:\.\d+)?)'
            ],
            '日期': [
                r'(\d{4})[-/]?(\d{1,2})[-/]?(\d{1,2})',
                r'(\d{1,2})[-/]?(\d{1,2})[-/]?(\d{4})'
            ],
            '时间': [
                r'(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?',
                r'(\d{1,2})\.(\d{1,2})(?:\.(\d{1,2}))?'
            ]
        }
        
        # 搜索每个文本段中的元数据模式
        for text in texts:
            found = False
            
            for field, field_patterns in patterns.items():
                for pattern in field_patterns:
                    matches = re.findall(pattern, text)
                    if matches:
                        for match in matches:
                            # 提取数值部分
                            numeric_parts = [m for m in match if m and m.replace('.', '').isdigit()]
                            if numeric_parts:
                                metadata_fields[field].append(numeric_parts[0])
                                found = True
                                break
                if found:
                    break
            
            # 尝试匹配其他可能的元数据
            if not found:
                # 检查是否包含常见的元数据关键词
                keywords = {
                    '扫描模式': ['扫描模式', 'Scan Mode', 'scan mode'],
                    '样品名称': ['样品', 'Sample', 'sample'],
                    '操作人员': ['操作员', 'Operator', 'operator', '用户', 'User', 'user'],
                    '仪器型号': ['型号', 'Model', 'model', '仪器', 'Instrument', 'instrument']
                }
                
                for field, field_keywords in keywords.items():
                    for keyword in field_keywords:
                        if keyword.lower() in text.lower():
                            metadata_fields[field].append(text.strip())
                            found = True
                            break
                    if found:
                        break
            
            if not found:
                metadata_fields['其他'].append(text)
        
        # 整理识别到的元数据
        sem_metadata = {}
        for field, values in metadata_fields.items():
            if values:
                # 去重并排序
                unique_values = sorted(set(values))
                sem_metadata[field] = unique_values[0] if len(unique_values) == 1 else unique_values
        
        if sem_metadata:
            self.metadata['SEM元数据'] = sem_metadata
    
    def _analyze_binary_structure(self):
        """
        分析文件的二进制结构
        """
        print("\n分析文件的二进制结构...")
        
        with open(self.file_path, 'rb') as f:
            header = f.read(512)
        
        # 检查文件头
        file_signature = header[:8]
        print(f"文件签名 (前8字节): {file_signature.hex()} = {repr(file_signature)}")
        
        # 检查是否有已知的文件格式标记
        known_signatures = {
            b'CBF': 'CBF文件格式',
            b'PNG': 'PNG图像',
            b'GIF': 'GIF图像',
            b'JFIF': 'JPEG图像',
            b'RIFF': 'RIFF容器格式',
            b'BM': 'BMP图像',
            b'PDF': 'PDF文档',
            b'ZIP': 'ZIP压缩文件',
            b'PK': 'PKZIP压缩文件',
            b'AAMV': '可能是某种自定义格式'
        }
        
        format_match = None
        for signature, description in known_signatures.items():
            if file_signature.startswith(signature):
                format_match = description
                break
        
        if format_match:
            print(f"识别到的文件格式: {format_match}")
            self.metadata['文件格式'] = format_match
        else:
            print("未识别到已知的文件格式")
        
        # 检查是否包含常见的元数据结构标记
        # 例如XML或JSON的开始标记
        if b'<?xml' in header or b'<root>' in header:
            print("可能包含XML结构")
            self.metadata['可能的结构'] = 'XML'
        elif b'{' in header or b'[' in header:
            print("可能包含JSON结构")
            self.metadata['可能的结构'] = 'JSON'
    
    def save_metadata(self, output_path: Optional[Path] = None):
        """
        保存提取的元数据到JSON文件
        
        Args:
            output_path: 输出文件路径，如果为None则使用默认路径
        """
        if output_path is None:
            # 默认输出路径: 与原文件同目录，添加_metadata后缀
            base_name = self.file_path.stem
            output_path = self.file_path.parent / f"{base_name}_metadata.json"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)
        
        print(f"\n元数据已保存到: {output_path}")

def main():
    """
    命令行工具的主函数
    """
    parser = argparse.ArgumentParser(description='BCF文件元数据解析器')
    parser.add_argument('input', type=Path, help='BCF文件路径')
    parser.add_argument('--output', '-o', type=Path, help='输出JSON文件路径')
    parser.add_argument('--verbose', '-v', action='store_true', help='显示详细信息')
    
    args = parser.parse_args()
    
    # 检查输入文件
    input_path = args.input.expanduser().resolve()
    if not input_path.exists():
        print(f"错误：文件不存在: {input_path}")
        return 1
    
    if input_path.suffix.lower() != '.bcf':
        print(f"警告：输入文件不是.bcf文件: {input_path}")
    
    # 解析文件
    parser = BCFParser(input_path)
    metadata = parser.parse()
    
    # 保存结果
    parser.save_metadata(args.output)
    
    # 显示结果
    print("\n提取的元数据摘要:")
    print("-" * 50)
    
    if '文件信息' in metadata:
        print("文件信息:")
        for key, value in metadata['文件信息'].items():
            print(f"  {key}: {value}")
    
    if 'SEM元数据' in metadata:
        print("\nSEM元数据:")
        for key, value in metadata['SEM元数据'].items():
            if isinstance(value, list):
                print(f"  {key}: {', '.join(map(str, value[:3]))}{'...' if len(value) > 3 else ''}")
            else:
                print(f"  {key}: {value}")
    
    print("\n解析完成！")
    return 0

if __name__ == "__main__":
    sys.exit(main())
