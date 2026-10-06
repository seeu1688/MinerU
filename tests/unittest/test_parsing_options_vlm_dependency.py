"""Exercise the installed VLM library; substitute only model predictions.

These tests prove extraction scheduling and layout preservation, not model accuracy.
"""

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image
from mineru_vl_utils import MinerUClient

from mineru.backend.analysis.pdf.table_options import retain_table_regions


@pytest.mark.parametrize("use_async", [False, True])
@pytest.mark.parametrize("image_analysis", [False, True])
def test_disabled_table_skips_model_crop_and_preserves_bbox(
    monkeypatch: pytest.MonkeyPatch, use_async: bool, image_analysis: bool
) -> None:
    client = MinerUClient(
        backend="http-client",
        server_url="http://127.0.0.1:1",
        model_name="contract-test",
        skip_model_name_checking=True,
        use_tqdm=False,
    )
    calls = []

    def predict(images: list[Any], prompts: list[str], *args: Any) -> list[SimpleNamespace]:
        calls.extend(prompts)
        return [SimpleNamespace(text="outside", scored=None) for _ in images]

    async def aio_predict(images: list[Any], prompts: list[str], *args: Any, **kwargs: Any) -> list[SimpleNamespace]:
        return predict(images, prompts, *args)

    monkeypatch.setattr(client, "_batch_predict", predict)
    monkeypatch.setattr(client, "_aio_batch_predict", aio_predict)
    blocks = [
        [
            {"type": "table", "bbox": [0.1, 0.1, 0.8, 0.8], "angle": 90},
            {"type": "image", "bbox": [0.2, 0.2, 0.6, 0.6]},
            {"type": "text", "bbox": [0.1, 0.85, 0.9, 0.95]},
        ]
    ]
    image = Image.new("RGB", (200, 200))
    try:
        kwargs = {
            "images": [image],
            "blocks_list": retain_table_regions(blocks),
            "not_extract_list": ["table"],
            "image_analysis": image_analysis,
        }
        if use_async:
            result = asyncio.run(client.aio_batch_extract_with_layout(**kwargs))
        else:
            result = client.batch_extract_with_layout(**kwargs)
        assert len(calls) == 1  # Only the external text reached the model.
        assert [block.type for block in result[0]] == ["table", "text"]
        assert result[0][0].bbox == [0.1, 0.1, 0.8, 0.8]
        assert result[0][0].content in (None, "")
        assert result[0][1].content == "outside"
        assert client.helper.image_analysis is False
    finally:
        image.close()
        asyncio.run(client.aclose())
