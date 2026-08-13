from starlette.requests import Request

from skyvern.forge.request_logging import _sanitize_body, _sanitize_response_body


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/login", "headers": []})


def test_json_request_and_response_tokens_are_redacted() -> None:
    body = b'{"password":"secret","nested":{"access_token":"jwt"}}'

    assert "secret" not in _sanitize_body(_request(), body, "application/json")
    assert "jwt" not in _sanitize_response_body(_request(), body.decode(), "application/json")


def test_presigned_url_is_redacted_from_response_logs() -> None:
    body = '{"presigned_url":"https://minio.test/object?X-Amz-Signature=synthetic"}'

    sanitized = _sanitize_response_body(_request(), body, "application/json")

    assert "X-Amz-Signature" not in sanitized
    assert "https://minio.test/object" not in sanitized
