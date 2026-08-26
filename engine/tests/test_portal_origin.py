"""Host-safe checks for the portal's strict same-origin boundary."""

from starlette.requests import Request

from app.portal.router import _same_origin


def _request(host: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "https",
            "path": "/p/case/token",
            "headers": [(b"host", host.encode())],
            "query_string": b"",
            "server": (host, 443),
            "client": ("127.0.0.1", 1),
        }
    )


def test_same_origin_requires_an_exact_http_origin() -> None:
    request = _request("intake.example.com")
    assert _same_origin(request, "https://intake.example.com")
    assert not _same_origin(request, "https://evil.example/intake.example.com")
    assert not _same_origin(request, "https://evilhttps://intake.example.com")
    assert not _same_origin(request, "javascript://intake.example.com")
