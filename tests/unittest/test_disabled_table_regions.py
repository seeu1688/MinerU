"""Disabled tables preserve source regions and do not consume adjacent content."""

from copy import deepcopy

from mineru.backend.analysis.pdf.table_options import exclude_table_formulas, retain_table_regions, tables_to_images


def test_table_ownership_keeps_captions_and_partial_overlap() -> None:
    table = {"type": "table", "bbox": [0.1, 0.1, 0.8, 0.8]}
    inner = {"type": "image", "bbox": [0.2, 0.2, 0.3, 0.3]}
    inner_text = {"type": "text", "bbox": [0.2, 0.3, 0.5, 0.4]}
    caption = {"type": "table_caption", "bbox": [0.1, 0.1, 0.8, 0.15], "content": "Caption"}
    adjacent = {"type": "text", "bbox": [0.75, 0.7, 0.95, 0.9], "content": "Adjacent paragraph"}
    pages = [[table, inner, inner_text, caption, adjacent]]
    original = deepcopy(pages)
    filtered = retain_table_regions(pages)
    assert filtered == [[table, caption, adjacent]]
    tables_to_images(filtered)
    assert pages == original
    assert filtered[0][0]["type"] == "image"
    assert filtered[0][1:] == [caption, adjacent]


def test_table_image_uses_page_orientation_and_discards_structure() -> None:
    for angle in (0, 90, 180, 270):
        pages = [[{"type": "table", "bbox": [0, 0, 1, 1], "angle": angle, "content": "<table/>", "lines": []}]]
        tables_to_images(pages)
        assert pages == [[{"type": "image", "bbox": [0, 0, 1, 1], "angle": 0, "content": ""}]]


def test_table_formula_filter_handles_pixel_coordinates_and_keeps_external_display_math() -> None:
    inner = {"label": "inline_formula", "bbox": [20, 20, 30, 30]}
    external = {"label": "display_formula", "bbox": [90, 90, 100, 100]}
    pages = [[{"type": "table", "bbox": [0.1, 0.1, 0.8, 0.8]}]]
    assert exclude_table_formulas([[inner, external]], pages, [(100, 100)]) == [[external]]


def test_invalid_table_box_does_not_claim_other_blocks() -> None:
    for bbox in ([0, 0, float("nan"), 1], [0, 0, 0, 0], [True, 0, 1, 1], None):
        pages = [[{"type": "table", "bbox": bbox}, {"type": "text", "bbox": [0.1, 0.1, 0.2, 0.2]}]]
        assert retain_table_regions(pages) == pages
