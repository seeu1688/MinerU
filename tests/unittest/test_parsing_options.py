"""Request-level parsing options: strict inputs and lossless false values."""

import pytest
from pydantic import ValidationError
from fastapi.testclient import TestClient
from pathlib import Path
from unittest.mock import AsyncMock

from mineru.parser import api_server
from mineru.parser.api_client import MinerUApiParser
from mineru.parser.api_server import CreateJobRequest


def test_default_options_preserve_client_payload() -> None:
    parser = MinerUApiParser(api_url="http://localhost:8000")
    payload = parser._build_payload({"type": "file_id", "file_id": "example"}, "")
    assert "table_enable" not in payload
    assert "image_analysis" not in payload


@pytest.mark.parametrize("table_enable", [True, False])
@pytest.mark.parametrize("image_analysis", [True, False])
def test_explicit_options_are_sent(table_enable: bool, image_analysis: bool) -> None:
    parser = MinerUApiParser(api_url="http://localhost:8000", table_enable=table_enable, image_analysis=image_analysis)
    payload = parser._build_payload({"type": "file_id", "file_id": "example"}, "")
    request = CreateJobRequest.model_validate(payload)
    assert payload["table_enable"] is table_enable
    assert payload["image_analysis"] is image_analysis
    assert request.table_enable is table_enable
    assert request.image_analysis is image_analysis


@pytest.mark.parametrize("field", ["table_enable", "image_analysis"])
@pytest.mark.parametrize("value", ["false", "true", 0, 1, [], {}])
def test_options_reject_non_booleans(field: str, value: object) -> None:
    with pytest.raises(ValueError, match=field):
        MinerUApiParser(**{field: value})
    with pytest.raises(ValidationError):
        CreateJobRequest.model_validate({"files": [{"source": {"type": "file_id", "file_id": "example"}}], field: value})


def test_request_defaults_and_null() -> None:
    payload = {"files": [{"source": {"type": "file_id", "file_id": "example"}}]}
    request = CreateJobRequest.model_validate(payload)
    assert request.table_enable is True
    assert request.image_analysis is None
    assert CreateJobRequest.model_validate({**payload, "image_analysis": None}).image_analysis is None
    with pytest.raises(ValidationError):
        CreateJobRequest.model_validate({**payload, "table_enable": None})


@pytest.mark.parametrize("field", ["table_enable", "image_analysis"])
@pytest.mark.parametrize("value", ["false", 0, 1])
def test_http_rejects_coercion_without_creating_job(tmp_path: Path, field: str, value: object) -> None:
    app = api_server.create_app(upload_dir=str(tmp_path), tier="flash")
    with TestClient(app) as client:
        response = client.post(
            "/v1/parse/jobs",
            json={"files": [{"source": {"type": "inline", "name": "demo.pdf", "data": "JVBERi0xLjcK"}}], field: value},
        )
    assert response.status_code == 400
    assert response.json()["error"]["param"] == field
    assert app.state.job_store._jobs == {}


def test_server_disabled_image_analysis_cannot_be_enabled_by_request(tmp_path: Path) -> None:
    app = api_server.create_app(upload_dir=str(tmp_path), tier="flash", image_analysis=False)
    with TestClient(app) as client:
        response = client.post(
            "/v1/parse/jobs",
            json={
                "files": [{"source": {"type": "inline", "name": "demo.pdf", "data": "JVBERi0xLjcK"}}],
                "image_analysis": True,
                "tier": "flash",
            },
        )
    assert response.status_code == 400
    assert response.json()["error"]["param"] == "image_analysis"
    assert app.state.job_store._jobs == {}


def test_job_options_are_independent_of_application_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_server, "_preflight_tier_dependencies", lambda *args: None)
    run_job = AsyncMock()
    monkeypatch.setattr(api_server, "_run_job", run_job)
    app = api_server.create_app(upload_dir=str(tmp_path), tier="standard", preload_models=False)
    with TestClient(app) as client:
        for enabled in (False, True):
            response = client.post(
                "/v1/parse/jobs",
                json={
                    "files": [{"source": {"type": "inline", "name": "demo.pdf", "data": "JVBERi0xLjcK"}}],
                    "tier": "advanced",
                    "image_analysis": enabled,
                    "table_enable": enabled,
                },
            )
            assert response.status_code == 202
        assert app.state.image_analysis is True
    assert run_job.await_count == 2
    assert [call.kwargs["image_analysis"] for call in run_job.await_args_list] == [False, True]
    assert [call.args[1].table_enable for call in run_job.await_args_list] == [False, True]


def test_flash_table_disable_is_rejected_before_queue(tmp_path: Path) -> None:
    app = api_server.create_app(upload_dir=str(tmp_path), tier="flash")
    with TestClient(app) as client:
        response = client.post(
            "/v1/parse/jobs",
            json={
                "files": [{"source": {"type": "inline", "name": "demo.pdf", "data": "JVBERi0xLjcK"}}],
                "tier": "flash",
                "table_enable": False,
            },
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "parsing_option_unsupported"
    assert app.state.job_store._jobs == {}
