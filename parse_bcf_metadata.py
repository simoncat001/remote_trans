#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BCF文件元数据解析器
用于解析SEM（扫描电子显微镜）.bcf文件中的元数据
"""

import argparse
import json
import mmap
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import lxml.etree as LET  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    LET = None


class BCFParser:
    """BCF文件解析器，用于从.bcf文件中提取元数据。"""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.metadata: Dict[str, Any] = {}

    def parse(self) -> Dict[str, Any]:
        """解析BCF文件，返回包含完整元数据的字典。"""

        print(f"正在解析BCF文件: {self.file_path}")
        file_info = self._build_file_info()
        xml_bytes = self._extract_xml_bytes()
        xml_text = self._decode_xml(xml_bytes)
        xml_text = self._sanitize_xml(xml_text)

        print("已定位到嵌入的XML元数据，正在转换为字典...")
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            if LET is None:
                raise
            print(f"⚠️ 标准XML解析失败 ({exc})，改用lxml恢复模式")
            parser = LET.XMLParser(recover=True)
            root = LET.fromstring(xml_text.encode("utf-8"), parser=parser)
        xml_dict = self._element_to_dict(root)

        self.metadata = {
            "文件信息": file_info,
            "元数据": {root.tag: xml_dict},
        }
        return self.metadata

    def _build_file_info(self) -> Dict[str, Any]:
        stat = self.file_path.stat()
        return {
            "文件名": self.file_path.name,
            "文件路径": str(self.file_path.resolve()),
            "文件大小(MB)": round(stat.st_size / (1024 * 1024), 2),
            "修改时间": stat.st_mtime,
            "创建时间": stat.st_ctime,
        }

    def _extract_xml_bytes(self) -> bytes:
        file_size = self.file_path.stat().st_size
        if file_size == 0:
            raise ValueError("文件为空，无法解析")

        with self.file_path.open("rb") as fh:
            with mmap.mmap(fh.fileno(), length=0, access=mmap.ACCESS_READ) as mm:
                start = mm.find(b"<?xml")
                if start == -1:
                    raise ValueError("未在BCF文件中找到XML头部")

                search_slice = mm[start : min(start + 4096, file_size)]
                root_tag_match = re.search(br"<([A-Za-z0-9:_-]+)[^>]*>", search_slice)
                if not root_tag_match:
                    raise ValueError("无法识别XML根元素")

                root_tag = root_tag_match.group(1)
                end_tag = b"</" + root_tag + b">"

                search_pos = start
                while True:
                    end = mm.find(end_tag, search_pos)
                    if end == -1:
                        raise ValueError("未找到XML根元素的结束标记")
                    end += len(end_tag)
                    # 直接返回第一个匹配到的根节点闭合段
                    if mm[start:end].count(end_tag) == 1:
                        break
                    search_pos = end

                length_mb = (end - start) / (1024 * 1024)
                print(
                    f"发现XML片段，起始于字节{start}，结束于字节{end}，长度约{length_mb:.2f} MB"
                )
                return bytes(mm[start:end])

    def _decode_xml(self, xml_bytes: bytes) -> str:
        encoding_match = re.search(br"encoding=\"([^\"]+)\"", xml_bytes[:100])
        encoding = encoding_match.group(1).decode("ascii") if encoding_match else "utf-8"
        print(f"使用编码 {encoding} 解码XML元数据")
        return xml_bytes.decode(encoding, errors="replace")

    @staticmethod
    def _sanitize_xml(xml_text: str) -> str:
        """移除XML 1.0不支持的控制字符，避免解析失败。"""

        invalid_xml_chars = re.compile(
            """[
                \x00-\x08
                \x0B-\x0C
                \x0E-\x1F
                \x7F-\x84
                \x86-\x9F
            ]""",
            re.VERBOSE,
        )
        cleaned = invalid_xml_chars.sub("", xml_text)
        if cleaned != xml_text:
            print("⚠️ 检测到非法控制字符，已自动清理后再解析")
        return cleaned

    def _element_to_dict(self, element: ET.Element) -> Any:
        children = list(element)
        node: Dict[str, Any] = {}

        if element.attrib:
            node.update({f"@{k}": v for k, v in element.attrib.items()})

        text = (element.text or "").strip()

        if children:
            for child in children:
                child_value = self._element_to_dict(child)
                if child.tag in node:
                    if not isinstance(node[child.tag], list):
                        node[child.tag] = [node[child.tag]]
                    node[child.tag].append(child_value)
                else:
                    node[child.tag] = child_value
            if text:
                node["#text"] = text
            return node

        if node:
            if text:
                node["#text"] = text
            return node

        return text

    def save_metadata(self, output_path: Optional[Path] = None):
        if output_path is None:
            output_path = self.file_path.with_name(f"{self.file_path.stem}_metadata.json")

        with output_path.open("w", encoding="utf-8") as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)

        print(f"\n元数据已保存到: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="BCF文件元数据解析器")
    parser.add_argument("input", type=Path, help="BCF文件路径")
    parser.add_argument("--output", "-o", type=Path, help="输出JSON文件路径")

    args = parser.parse_args()

    input_path = args.input.expanduser().resolve()
    if not input_path.exists():
        print(f"错误：文件不存在: {input_path}")
        return 1

    if input_path.suffix.lower() != ".bcf":
        print(f"警告：输入文件不是.bcf文件: {input_path}")

    parser = BCFParser(input_path)
    parser.parse()
    parser.save_metadata(args.output)

    print("\n解析完成！")
    return 0


if __name__ == "__main__":
    sys.exit(main())
