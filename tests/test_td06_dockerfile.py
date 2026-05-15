"""TD-06: Dockerfile + docker-compose existence and content checks."""

from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_dockerfile_exists():
    assert (ROOT / "Dockerfile").exists()


def test_dockerignore_excludes_env():
    content = (ROOT / ".dockerignore").read_text()
    assert ".env" in content


def test_dockerignore_excludes_tests():
    content = (ROOT / ".dockerignore").read_text()
    assert "tests/" in content


def test_docker_compose_exists():
    assert (ROOT / "docker-compose.yml").exists()


def test_docker_setup_docs_exists():
    assert (ROOT / "docs" / "DOCKER_SETUP.md").exists()
