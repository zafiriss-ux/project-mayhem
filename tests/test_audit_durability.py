"""INV-22 (AGENTS §8.13, T-PRA-21, plan #21): the coach audit record is durable and written
before the route's effect; if it cannot be written the request fails closed."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from titan.api.auth import AuthStore, hash_password
from titan.api.main import CSRF_HEADER_NAME, CoachAuditStore, create_app
from titan.core.database import DatabaseManager

_ROUTES = [
    ("get", "/athletes/a1/dashboard", None, "athlete_dashboard"),
    ("post", "/coach/overrides?athlete_id=a1", {"reason": "legs heavy"}, "coach_override"),
]


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setenv("TITAN_JWT_PRIVATE_KEY", key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
    ).decode())
    monkeypatch.setenv("TITAN_JWT_PUBLIC_KEY", key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode())
    counted: list[str] = []
    monkeypatch.setattr(
        "titan.observability.metrics.get_metrics",
        lambda: SimpleNamespace(counter=lambda name, *a, **k: counted.append(name)),
    )

    db = DatabaseManager(db_dir=tmp_path)
    db.assign_athlete_to_coach("coach-1", "a1")
    auth_store = AuthStore()
    auth_store.upsert_user(
        user_id="coach-1", username="coach", password_hash=hash_password("coach-pass"),
        role="COACH", athlete_id=None,
    )
    audit_store = CoachAuditStore()
    client = TestClient(
        create_app(auth_store=auth_store, audit_store=audit_store, db=db), base_url="https://testserver"
    )
    assert client.post("/auth/login", json={"username": "coach", "password": "coach-pass"}).status_code == 200
    csrf = {CSRF_HEADER_NAME: client.get("/api/csrf-token").json()["csrf_token"]}
    yield SimpleNamespace(client=client, db=db, audit_store=audit_store, counted=counted, csrf=csrf)
    db.close()


def _call(env, method: str, url: str, body):  # noqa: ANN001, ANN202
    kwargs = {"headers": env.csrf}
    if body is not None:
        kwargs["json"] = body
    return getattr(env.client, method)(url, **kwargs)


@pytest.mark.integration
@pytest.mark.parametrize(("method", "url", "body", "resource"), _ROUTES)
def test_audit_row_is_durable_when_the_action_succeeds(setup, method, url, body, resource) -> None:
    assert _call(setup, method, url, body).status_code == 200
    [row] = setup.db.get_coach_audit_log(coach_id="coach-1")
    assert (row["athlete_id"], row["resource"]) == ("a1", resource)


@pytest.mark.integration
@pytest.mark.parametrize(("method", "url", "body", "resource"), _ROUTES)
def test_audit_write_failure_fails_closed_before_the_action(
    setup, monkeypatch: pytest.MonkeyPatch, method, url, body, resource
) -> None:
    def _broken(**_kw) -> None:
        raise RuntimeError("database is locked")

    monkeypatch.setattr(setup.db, "log_coach_action", _broken)

    response = _call(setup, method, url, body)

    assert response.status_code == 503  # the handler never ran: no "override_submitted" body
    assert "not performed" in response.json()["detail"]
    assert setup.counted == ["audit_write_failure"]
    assert setup.audit_store.rows == []
    assert setup.db.get_coach_audit_log() == []


@pytest.mark.integration
def test_unassigned_coach_is_denied_and_not_audited(setup) -> None:
    response = setup.client.post("/coach/overrides?athlete_id=a2", json={"reason": "r"}, headers=setup.csrf)
    assert response.status_code == 403
    assert setup.db.get_coach_audit_log() == []
