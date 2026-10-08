"""公式开关的请求边界、模型调度和原始区域保留。"""

import asyncio
from copy import deepcopy
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError
from mineru_vl_utils import MinerUClient

from mineru.backend.analyze import _validate_parsing_options
from mineru.backend.analysis.pdf.formula_options import formulas_to_images, retain_formula_regions
from mineru.backend.analysis.pdf.table_options import retain_table_regions
from mineru.errors import InvalidRequestError
from mineru.parser import api_server
from mineru.parser.api_client import MinerUApiParser
from mineru.parser.api_server import CreateJobRequest
from mineru.parser.mineru_parser import MinerUParser


@pytest.mark.parametrize("formula", [True, False])
@pytest.mark.parametrize("table", [True, False])
@pytest.mark.parametrize("image", [True, False])
def test_three_options_survive_remote_payload(formula: bool, table: bool, image: bool) -> None:
    parser = MinerUApiParser(formula_enable=formula, table_enable=table, image_analysis=image)
    payload = parser._build_payload({"type": "file_id", "file_id": "sample"}, "")
    request = CreateJobRequest.model_validate(payload)
    assert (request.formula_enable, request.table_enable, request.image_analysis) == (formula, table, image)


def test_formula_default_and_null_contract() -> None:
    payload = MinerUApiParser()._build_payload({"type": "file_id", "file_id": "sample"}, "")
    assert "formula_enable" not in payload
    assert CreateJobRequest.model_validate(payload).formula_enable is True
    with pytest.raises(ValidationError):
        CreateJobRequest.model_validate({**payload, "formula_enable": None})


@pytest.mark.parametrize("value", ["false", "true", 0, 1, [], {}, None])
def test_formula_rejects_coercion(value: object) -> None:
    with pytest.raises(ValueError, match="formula_enable"):
        MinerUParser(formula_enable=value)
    if value is not None:  # Remote SDK None means omit the field.
        with pytest.raises(ValueError, match="formula_enable"):
            MinerUApiParser(formula_enable=value)
    with pytest.raises(ValidationError):
        CreateJobRequest.model_validate(
            {"files": [{"source": {"type": "file_id", "file_id": "sample"}}], "formula_enable": value}
        )


@pytest.mark.parametrize("suffix,effort", [("xlsx", "xhigh"), ("docx", "medium"), ("pdf", "flash")])
def test_unsupported_routes_reject_formula_disable(suffix: str, effort: str) -> None:
    with pytest.raises(InvalidRequestError, match="formula_enable=False"):
        _validate_parsing_options(True, True, effort, suffix, False)


@pytest.mark.parametrize("name,tier", [("sample.xlsx", "advanced"), ("sample.pdf", "flash")])
def test_http_rejects_unsupported_formula_before_job(tmp_path: Path, name: str, tier: str) -> None:
    app = api_server.create_app(upload_dir=str(tmp_path), tier="flash")
    with TestClient(app) as client:
        response = client.post(
            "/v1/parse/jobs",
            json={
                "files": [{"source": {"type": "inline", "name": name, "data": "JVBERi0xLjcK"}}],
                "tier": tier,
                "formula_enable": False,
            },
        )
    assert response.status_code == 400
    assert response.json()["error"]["param"] == "formula_enable"
    assert response.json()["error"]["code"] == "parsing_option_unsupported"
    assert not app.state.job_store._jobs


def test_formula_container_preserves_outer_crop_and_adjacent_sentence() -> None:
    pages = [
        [
            {"type": "equation_block", "bbox": [0.1, 0.2, 0.9, 0.5]},
            {"type": "equation", "bbox": [0.2, 0.25, 0.8, 0.3]},
            {"type": "text", "bbox": [0.2, 0.35, 0.8, 0.4], "content": "duplicate"},
            {"type": "image", "bbox": [0.2, 0.35, 0.3, 0.4], "content": "must not be interpreted"},
            {"type": "text", "bbox": [0.8, 0.45, 0.95, 0.6], "content": "Keep x=1 in this sentence"},
        ]
    ]
    original = deepcopy(pages)
    result = retain_formula_regions(pages)
    formulas_to_images(result)
    assert pages == original
    assert len(result[0]) == 2
    assert result[0][0] == {"type": "image", "bbox": [0.1, 0.2, 0.9, 0.5], "content": "", "angle": 0}
    assert result[0][1] == original[0][-1]


@pytest.mark.parametrize("effort", ["medium", "high", "xhigh"])
@pytest.mark.parametrize("parse_mode", ["txt", "ocr"])
def test_formula_disable_skips_mfr_and_does_not_mask_inline_text(
    monkeypatch: pytest.MonkeyPatch,
    effort: str,
    parse_mode: str,
) -> None:
    from mineru.backend.analysis.pdf import window

    image = Image.new("RGB", (100, 100))
    context = SimpleNamespace(mfr_model=Mock(), ocr_model=Mock())
    context.mfr_model.batch_predict.side_effect = AssertionError("Formula model must not run")
    monkeypatch.setattr(window, "_validate_text_formula_window_inputs", lambda *args: None)
    monkeypatch.setattr(window, "_apply_medium_table_recognition", lambda *args: None)
    monkeypatch.setattr(window, "_apply_medium_formula_number_ocr", Mock(side_effect=AssertionError("Formula OCR")))
    captured = {}

    def ocr(*args: object) -> list:
        captured["masks"] = args[3]
        return [[]]

    monkeypatch.setattr(window, "_ocr_det", ocr)
    monkeypatch.setattr(window, "_apply_ocr_rec_results", lambda *args: None)
    monkeypatch.setattr(window, "_fill_window_block_content_and_lines", lambda *args, **kwargs: args[2])
    try:
        window._process_text_and_formulas(
            [{"img_pil": image}],
            [SimpleNamespace()],
            [[{"type": "text", "bbox": [0, 0, 1, 1]}]],
            parse_mode,
            effort,
            context,
            [[{"label": "inline_formula", "bbox": [10, 10, 20, 20]}]],
            np_images=[np.zeros((100, 100, 3), dtype=np.uint8)],
            formula_enable=False,
        )
        assert captured["masks"] == [[]]
        context.mfr_model.batch_predict.assert_not_called()
    finally:
        image.close()


@pytest.mark.parametrize("use_async", [False, True])
@pytest.mark.parametrize("table", [False, True])
@pytest.mark.parametrize("image_analysis", [False, True])
def test_installed_vlm_skips_formula_crop_without_disabling_other_types(
    monkeypatch: pytest.MonkeyPatch,
    use_async: bool,
    table: bool,
    image_analysis: bool,
) -> None:
    client = MinerUClient(
        backend="http-client", server_url="http://127.0.0.1:1", model_name="test", skip_model_name_checking=True, use_tqdm=False
    )
    calls = []

    def predict(images: list, prompts: list[str], *args: object) -> list:
        calls.extend(prompts)
        return [SimpleNamespace(text="outside", scored=None) for _ in images]

    async def aio_predict(images: list, prompts: list[str], *args: object, **kwargs: object) -> list:
        return predict(images, prompts, *args)

    monkeypatch.setattr(client, "_batch_predict", predict)
    monkeypatch.setattr(client, "_aio_batch_predict", aio_predict)
    pages = [
        [
            {"type": "equation_block", "bbox": [0.1, 0.1, 0.9, 0.3]},
            {"type": "equation", "bbox": [0.2, 0.15, 0.8, 0.25]},
            {"type": "table", "bbox": [0.1, 0.35, 0.9, 0.6]},
            {"type": "image", "bbox": [0.1, 0.65, 0.4, 0.8]},
            {"type": "text", "bbox": [0.1, 0.85, 0.9, 0.95]},
        ]
    ]
    pages = retain_formula_regions(pages)
    if not table:
        pages = retain_table_regions(pages)
    img = Image.new("RGB", (200, 200))
    try:
        kwargs = {
            "images": [img],
            "blocks_list": pages,
            "image_analysis": image_analysis,
            "not_extract_list": ["equation", "equation_block"] + ([] if table else ["table"]),
        }
        result = (
            asyncio.run(client.aio_batch_extract_with_layout(**kwargs))
            if use_async
            else client.batch_extract_with_layout(**kwargs)
        )
        assert not any("Formula Recognition" in prompt for prompt in calls)
        assert len(calls) == 1 + int(table) + int(image_analysis)
        assert result[0][0].type == "equation"
        assert result[0][0].bbox == [0.1, 0.1, 0.9, 0.3]
        assert not result[0][0].content
    finally:
        img.close()
        asyncio.run(client.aclose())


@pytest.mark.parametrize("effort", ["high", "xhigh"])
@pytest.mark.parametrize("parse_mode", ["txt", "ocr"])
@pytest.mark.parametrize("formula", [False, True])
@pytest.mark.parametrize("table", [False, True])
@pytest.mark.parametrize("image", [False, True])
def test_vlm_options_keep_three_switches_independent(
    effort: str, parse_mode: str, formula: bool, table: bool, image: bool
) -> None:
    from mineru.backend.analysis.pdf import window

    state = SimpleNamespace(images_pil_list=[], high_vlm_blocks=[])
    options = window._inference_options(state, effort, parse_mode, image, table, formula)
    excluded = set(options.get("not_extract_list", []))
    assert ("equation" in excluded) is (not formula)
    assert ("equation_block" in excluded) is (not formula)
    assert ("table" in excluded) is (not table)
    assert ("text" in excluded) is (parse_mode == "txt")
    assert options["image_analysis"] is (image and effort == "xhigh")


@pytest.mark.parametrize("effort", ["medium", "high", "xhigh"])
@pytest.mark.parametrize("parse_mode", ["txt", "ocr"])
@pytest.mark.parametrize("formula", [False, True])
@pytest.mark.parametrize("table", [False, True])
def test_window_result_preserves_formula_crop_and_sentence(
    monkeypatch: pytest.MonkeyPatch, effort: str, parse_mode: str, formula: bool, table: bool
) -> None:
    from mineru.backend.analysis.pdf import window

    image = Image.new("RGB", (100, 100))
    state = SimpleNamespace(
        images_list=[{"img_pil": image}],
        window_pages=[],
        images_pil_list=[image],
        np_images=[],
        images_layout_res=[],
        vl_style_layout_blocks=[[]],
        page_text_geometries=None,
        page_vector_geometries=None,
        page_snapshots=None,
        accepted_native_tables=[],
        window=SimpleNamespace(start=0),
    )
    blocks = [
        [
            {"type": "equation", "bbox": [0.1, 0.1, 0.9, 0.3], "content": "x^2", "latex": "x^2"},
            {"type": "table", "bbox": [0.1, 0.4, 0.9, 0.6], "content": "<table>value</table>"},
            {"type": "text", "bbox": [0.1, 0.8, 0.9, 0.9], "content": "Keep x=1 in this sentence"},
        ]
    ]
    monkeypatch.setattr(window, "_convert_vlm_results_to_model_list", lambda value: value)
    monkeypatch.setattr(window, "_restore_native_high_table_blocks", lambda value, *args: value)
    for name in (
        "_normalize_xhigh_vlm_blocks",
        "_apply_layout_title_split",
        "_apply_seal_ocr",
        "_supplement_missing_image_block_containers",
    ):
        monkeypatch.setattr(window, name, lambda *args: None)

    def fill(*args: object, **kwargs: object) -> list:
        assert kwargs.get("formula_enable", True) is formula
        return args[2]

    monkeypatch.setattr(window, "_process_text_and_formulas", fill)
    attached = Mock()
    monkeypatch.setattr(window, "_attach_visual_block_images", attached)
    try:
        result = window._finish_pdf_window(
            state,
            blocks,
            effort=effort,
            parse_mode=parse_mode,
            hybrid_model=SimpleNamespace(),
            formula_enable=formula,
            table_enable=table,
        )
        assert result[0][0]["bbox"] == [0.1, 0.1, 0.9, 0.3]
        assert result[0][0]["type"] == ("equation" if formula else "image")
        assert result[0][0]["content"] == ("x^2" if formula else "")
        assert ("latex" in result[0][0]) is formula
        assert result[0][1]["type"] == ("table" if table else "image")
        assert result[0][2]["content"] == "Keep x=1 in this sentence"
        assert attached.call_args.args[0] is result
    finally:
        image.close()


@pytest.mark.parametrize("use_async", [False, True])
@pytest.mark.parametrize("effort", ["high", "xhigh"])
@pytest.mark.parametrize("parse_mode", ["txt", "ocr"])
@pytest.mark.parametrize("formula", [False, True])
@pytest.mark.parametrize("table", [False, True])
@pytest.mark.parametrize("image", [False, True])
def test_window_dispatch_propagates_formula_option(
    monkeypatch: pytest.MonkeyPatch,
    use_async: bool,
    effort: str,
    parse_mode: str,
    formula: bool,
    table: bool,
    image: bool,
) -> None:
    from mineru.backend.analysis.pdf import window

    blocks = [[{"type": "equation_block", "bbox": [0.1, 0.1, 0.9, 0.3]}]]
    state = SimpleNamespace(images_pil_list=[], high_vlm_blocks=blocks, vl_style_layout_blocks=blocks, close=Mock())
    calls = []

    def prepare(*args: object, **kwargs: object) -> SimpleNamespace:
        assert kwargs.get("formula_enable", True) is formula
        return state

    def finish(*args: object, **kwargs: object) -> list:
        assert kwargs.get("formula_enable", True) is formula
        return args[1]

    def extract(**kwargs: object) -> list:
        calls.append(kwargs)
        return kwargs.get("blocks_list", blocks)

    async def aio_extract(**kwargs: object) -> list:
        return extract(**kwargs)

    async def run_sync(fn: object, *args: object, **kwargs: object) -> object:
        return fn(*args, **kwargs)

    async def run_prepare(fn: object, session: object) -> None:
        fn()

    predictor = SimpleNamespace(
        batch_layout_detect=Mock(return_value=deepcopy(blocks)),
        batch_extract_with_layout=extract,
        batch_two_step_extract=extract,
        aio_batch_layout_detect=Mock(),
        aio_batch_extract_with_layout=aio_extract,
        aio_batch_two_step_extract=aio_extract,
    )

    async def layout(*args: object) -> list:
        return deepcopy(blocks)

    predictor.aio_batch_layout_detect = layout
    monkeypatch.setattr(window, "local_model_stage", lambda *args: nullcontext())
    monkeypatch.setattr(window, "_prepare_pdf_window", prepare)
    monkeypatch.setattr(window, "_prepare_locked_window", prepare)
    monkeypatch.setattr(window, "_finish_pdf_window", finish)
    monkeypatch.setattr(window, "_finish_locked_window", finish)
    monkeypatch.setattr(window, "get_document_render_session", lambda *args: None)
    monkeypatch.setattr(window, "_run_window_prepare", run_prepare)
    monkeypatch.setattr(window, "run_sync", run_sync)
    context = SimpleNamespace(device="cpu")
    kwargs = {
        "effort": effort,
        "parse_mode": parse_mode,
        "image_analysis": image,
        "hybrid_model": context,
        "vlm_predictor": predictor,
        "table_enable": table,
        "formula_enable": formula,
    }
    document = SimpleNamespace(page_count=1)
    if use_async:
        asyncio.run(window.aio_process_pdf_windows(b"", document, **kwargs))
    else:
        window._process_pdf_window(b"", document, SimpleNamespace(start=0, end=1), page_count=1, **kwargs)
    assert len(calls) == 1
    assert ("equation" in calls[0].get("not_extract_list", [])) is (not formula)
    assert calls[0]["image_analysis"] is (image and effort == "xhigh")
    if effort == "xhigh" and not formula:
        assert calls[0]["blocks_list"][0][0]["type"] == "equation"
        assert calls[0]["blocks_list"][0][0]["content"] == ""
    state.close.assert_called_once()
