# Copyright (c) Opendatalab. All rights reserved.
"""关闭公式专用识别时保留独立公式区域。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .table_options import _bbox, _inside

FORMULA_TYPES = frozenset({"equation", "equation_block"})


def retain_formula_regions(pages: Sequence[Sequence[Mapping[str, Any]]]) -> list[list[dict[str, Any]]]:
    """保留最外层公式框，避免容器内的文本或子公式重复抽取。

    equation_block 改为 equation，防止 VLM 后处理删除空公式容器。
    只过滤完整包含的内容块；部分相交的正文必须保留。
    """
    result = []
    for page in pages:
        regions = [
            (index, box)
            for index, block in enumerate(page)
            if block.get("type") in FORMULA_TYPES
            if (box := _bbox(block)) is not None
        ]
        retained = []
        for index, block in enumerate(page):
            box = _bbox(block)
            if box is not None and block.get("type") in FORMULA_TYPES | {
                "text",
                "formula_number",
                "image",
                "image_block",
                "chart",
                "title",
                "doc_title",
                "paragraph_title",
                "aside_text",
                "ref_text",
                "list",
                "index",
                "code",
                "algorithm",
            }:
                if any(index != other and _inside(box, outer) and (box != outer or index > other) for other, outer in regions):
                    continue
            copy = dict(block)
            if copy.get("type") in FORMULA_TYPES:
                copy["type"] = "equation"
                copy["content"] = ""
            retained.append(copy)
        result.append(retained)
    return result


def formulas_to_images(pages: list[list[dict[str, Any]]]) -> None:
    """公式回填完成后改为图片；不再送入图片分析模型。"""
    for page in pages:
        for block in page:
            if block.get("type") not in FORMULA_TYPES:
                continue
            block["type"] = "image"
            block["content"] = ""
            block["angle"] = 0
            for name in ("latex", "lines", "sub_type"):
                block.pop(name, None)


__all__ = ["FORMULA_TYPES", "retain_formula_regions", "formulas_to_images"]
