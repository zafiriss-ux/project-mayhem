"""AT-03: only the allow-listed routes answer without a login.

ADR-0048 keeps the API behind JWT. FastAPI serves /docs, /redoc and /openapi.json
by default; they gave anyone the API map without a login. Every other route must
answer 401 when the request carries no credentials.
"""

from __future__ import annotations

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from titan.api.auth import AuthStore
from titan.api.main import CSRF_HEADER_NAME, create_app

# Routes that answer without a JWT on purpose. /metrics is a mount with its own
# token (M0-14) and is not an APIRoute.
PUBLIC_ROUTES = {
    "/health",
    "/readyz",
    "/api/csrf-token",
    "/auth/login",
    "/auth/refresh",
    "/auth/logout",
}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setenv(
        "TITAN_JWT_PRIVATE_KEY",
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ).decode(),
    )
    monkeypatch.setenv(
        "TITAN_JWT_PUBLIC_KEY",
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode(),
    )
    return TestClient(create_app(auth_store=AuthStore()), base_url="https://testserver")


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"])
def test_the_api_docs_are_not_served(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 404


def test_no_route_besides_the_api_and_metrics(client: TestClient) -> None:
    # Plain Starlette routes (the docs pages are such routes) skip the API's auth
    # dependencies, so none may exist; /metrics guards itself (M0-14).
    others = {r.path for r in client.app.routes if not isinstance(r, APIRoute)}
    assert others <= {"/metrics"}, others


def test_every_route_outside_the_allow_list_needs_a_login(client: TestClient) -> None:
    routes = [r for r in client.app.routes if isinstance(r, APIRoute)]
    paths = {r.path for r in routes}
    assert PUBLIC_ROUTES <= paths, "an allow-listed route is gone; update the list"

    csrf = client.get("/api/csrf-token").json()["csrf_token"]
    checked = 0
    for route in routes:
        if route.path in PUBLIC_ROUTES:
            continue
        url = route.path.replace("{athlete_id}", "a-0000abcd")
        for method in route.methods - {"HEAD", "OPTIONS"}:
            response = client.request(method, url, headers={CSRF_HEADER_NAME: csrf}, json={})
            assert response.status_code == 401, (method, route.path, response.status_code)
            checked += 1
    assert checked >= 3
