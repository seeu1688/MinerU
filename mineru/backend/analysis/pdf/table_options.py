# Copyright (c) Opendatalab. All rights reserved.
"""Preserve disabled table regions without extracting their contents."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


def _bbox(block: Mapping[str, Any]) -> tuple[float, float, float, float] | None:
    """读取有限且有正面积的区域坐标；非法坐标不参与内容归属判断。"""
    raw = block.get("bbox")
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in raw):
        return None
    x0, y0, x1, y1 = raw
    if not all(math.isfinite(value) for value in raw) or x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1, y1


def _inside(inner: tuple[float, ...], outer: tuple[float, ...]) -> bool:
    """只有完整包含才判定内部内容属于外部区域。"""
    return outer[0] <= inner[0] and outer[1] <= inner[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


def retain_table_regions(pages: Sequence[Sequence[Mapping[str, Any]]]) -> list[list[dict[str, Any]]]:
    """保留表格和题注，在抽取前排除完整位于表格内的正文块。

    部分交叠不能确定内容归属。复制块，避免修改共享布局或其他请求。
    """
    result = []
    body_types = {
        "text",
        "title",
        "doc_title",
        "paragraph_title",
        "aside_text",
        "ref_text",
        "list",
        "index",
        "phonetic",
        "code",
        "algorithm",
        "equation",
        "equation_block",
        "image",
        "image_block",
        "chart",
        "formula_number",
    }
    for page in pages:
        tables = [box for block in page if block.get("type") == "table" if (box := _bbox(block)) is not None]
        retained = []
        for block in page:
            box = _bbox(block)
            if block.get("type") in body_types and box is not None and any(_inside(box, table) for table in tables):
                continue
            retained.append(dict(block))
        result.append(retained)
    return result


def tables_to_images(pages: list[list[dict[str, Any]]]) -> None:
    """在文本归属处理后将表格转为图片，保留页面渲染方向。"""
    for page in pages:
        for block in page:
            if block.get("type") != "table":
                continue
            block["type"] = "image"
            block["content"] = ""
            block["angle"] = 0
            for name in ("html", "lines", "sub_type"):
                block.pop(name, None)


def exclude_table_formulas(
    formulas: list[list[dict[str, Any]]],
    pages: list[list[dict[str, Any]]],
    sizes: list[tuple[int, int]],
) -> list[list[dict[str, Any]]]:
    """在公式识别前排除表格内的公式裁图，保留表格外的公式。"""
    result = []
    for items, page, (width, height) in zip(formulas, pages, sizes, strict=True):
        tables = [box for block in page if block.get("type") == "table" if (box := _bbox(block)) is not None]
        retained = []
        for item in items:
            box = _bbox(item)
            if box is not None:
                normalized = box[0] / width, box[1] / height, box[2] / width, box[3] / height
                if any(_inside(normalized, table) for table in tables):
                    continue
            retained.append(item)
        result.append(retained)
    return result


__all__ = ["exclude_table_formulas", "retain_table_regions", "tables_to_images"]
