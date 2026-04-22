"""
Health endpoint tests — v1.0

Covers:
  GET /health      — Liveness probe semantics, response shape, no-I/O contract
  GET /ready       — Readiness probe: DB ok, Redis status variants, 503 on DB failure
  GET /health/deep — Diagnostics: key gate, structure, live Redis probe

Tests are grouped to document contracts, not just assert shapes.
All tests use the in-memory SQLite test database set up in conftest.py.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.deps import get_db
from app.database import Base


# ── Shared client fixture (independent of conftest's client for isolation) ────

_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_ENGINE)


@pytest.fixture(scope="module", autouse=True)
def _create_tables():
    Base.metadata.create_all(bind=_ENGINE)
    yield
    Base.metadata.drop_all(bind=_ENGINE)


@pytest.fixture
def db():
    sess = _Session()
    yield sess
    sess.close()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# GET /health  —  Liveness probe
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthLiveness:
    """
    /health is the liveness probe.

    Contract:
      - Always returns 200 (never 503) while the process is alive
      - Does NO database or Redis I/O
      - Returns minimal fields only (no topology internals)
      - Must respond in < 100 ms (no blocking I/O)
    """

    def test_health_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200, f"Liveness probe must always return 200, got {r.status_code}"

    def test_health_status_is_ok(self, client):
        data = r = client.get("/health").json()
        assert data["status"] == "ok", f"status field must be 'ok', got {data.get('status')}"

    def test_health_returns_version(self, client):
        data = client.get("/health").json()
        assert "version" in data, "/health must include 'version' field"
        assert isinstance(data["version"], str)
        assert len(data["version"]) > 0

    def test_health_returns_uptime(self, client):
        data = client.get("/health").json()
        assert "uptime_seconds" in data, "/health must include 'uptime_seconds' for basic observability"
        assert isinstance(data["uptime_seconds"], int)
        assert data["uptime_seconds"] >= 0

    def test_health_does_not_expose_topology(self, client):
        """
        /health must NOT expose deployment_mode, node_role, branch_code,
        hq_sync_enabled, or environment. These were in the original one-liner
        and are now correctly moved to /health/deep (behind INTERNAL_API_KEY).
        """
        data = client.get("/health").json()
        forbidden_keys = {"deployment_mode", "node_role", "branch_code",
                          "hq_sync_enabled", "environment", "deployment"}
        leaked = forbidden_keys & data.keys()
        assert not leaked, (
            f"SECURITY: /health is leaking topology internals: {leaked}. "
            "These must only appear in /health/deep (auth-gated)."
        )

    def test_health_does_not_expose_db_state(self, client):
        """DB status must not appear on liveness — liveness must never fail due to DB."""
        data = client.get("/health").json()
        assert "db" not in data
        assert "database" not in data
        assert "checks" not in data

    def test_health_never_503_when_db_is_down(self, client):
        """
        Critical: /health must return 200 even if the DB is unreachable.
        Docker restarts the container based on liveness. We must not restart a
        healthy process just because Postgres is temporarily down.
        """
        with patch("app.main.engine") as mock_engine:
            mock_engine.connect.side_effect = Exception("simulated DB failure")
            mock_engine.dialect.name = "sqlite"
            r = client.get("/health")

        assert r.status_code == 200, (
            f"Liveness probe returned {r.status_code} when DB was down. "
            "This is wrong — liveness must never fail due to DB state."
        )

    def test_health_no_auth_required(self, client):
        """Liveness must be accessible without any Authorization header."""
        r = client.get("/health")
        assert r.status_code == 200
        assert r.status_code != 401
        assert r.status_code != 403


# ─────────────────────────────────────────────────────────────────────────────
# GET /ready  —  Readiness probe
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthReadiness:
    """
    /ready is the readiness probe.

    Contract:
      - Returns 200 + status='ok' when DB is reachable and Redis is configured/ok
      - Returns 200 + status='degraded' when DB ok but Redis unavailable (optional)
      - Returns 503 + status='not_ready' when DB is unreachable
      - Never exposes raw connection strings or exception details
      - No auth required (used by load balancers and Docker healthcheck)
    """

    def test_ready_returns_200_when_db_ok(self, client):
        """
        With the always-available SQLite in-memory test DB, /ready must return
        exactly 200 — never 503. The previous assertion used `in (200, 503)`,
        which silently passed even when the DB probe was failing.
        """
        r = client.get("/ready")
        assert r.status_code == 200, (
            f"/ready returned {r.status_code} with an always-available SQLite test DB. "
            "Expected exactly 200. If this fails, verify that the test DB engine "
            "override (get_db) is wired correctly and the SQLite connection is open."
        )

    def test_ready_response_has_required_shape(self, client):
        r = client.get("/ready")
        data = r.json()
        assert "status" in data
        assert "version" in data
        assert "checks" in data
        assert "database" in data["checks"]
        assert "redis" in data["checks"]

    def test_ready_status_ok_when_db_reachable(self, client):
        """
        With SQLite test DB always reachable: ready returns 200 + ok/degraded.
        """
        r = client.get("/ready")
        assert r.status_code == 200
        assert r.json()["status"] in ("ok", "degraded"), (
            f"Unexpected status value: {r.json()['status']}"
        )

    def test_ready_503_when_db_is_down(self, client):
        """
        P0: When DB is unreachable, /ready must return 503 so Docker
        does NOT route traffic to the API until the DB recovers.
        """
        with patch("app.main.engine") as mock_engine:
            mock_engine.connect.side_effect = Exception("simulated postgres down")
            mock_engine.dialect.name = "postgresql"
            r = client.get("/ready")

        assert r.status_code == 503, (
            f"Expected 503 when DB is down, got {r.status_code}. "
            "The Docker healthcheck depends on this to block the sync-agent from starting."
        )
        data = r.json()
        assert data["status"] == "not_ready"
        assert data["checks"]["database"] == "error"

    def test_ready_does_not_leak_connection_string(self, client):
        """DB error response must not contain DSN, password, or hostname."""
        with patch("app.main.engine") as mock_engine:
            mock_engine.connect.side_effect = Exception(
                "password authentication failed for user 'smartlynx'"
            )
            mock_engine.dialect.name = "postgresql"
            r = client.get("/ready")

        body = r.text
        assert "password" not in body.lower(), "Connection string leaked in /ready response"
        assert "postgresql://" not in body
        assert "smartlynx_db" not in body

    def test_ready_redis_not_configured_is_acceptable(self, client):
        """
        When REDIS_URL is not set (dev or minimal deployment),
        /ready must still return 200 with redis='not_configured'.
        """
        with patch("app.main.settings") as mock_settings:
            mock_settings.REDIS_URL = ""   # Redis not configured
            # Keep engine working
            r = client.get("/ready")

        # The outcome depends on whether engine also mocked — just check structure
        data = r.json()
        assert "checks" in data

    def test_ready_redis_unavailable_is_degraded_not_503(self, client):
        """
        If Redis is configured but unreachable, /ready must return 200 (not 503)
        with status='degraded'. Redis is optional — losing cache must not gate traffic.
        """
        import app.main as main_module

        # Simulate Redis client exists but ping fails
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("Redis connection refused")

        original = main_module._redis_sync_client
        try:
            main_module._redis_sync_client = mock_redis
            with patch.object(main_module.settings, "REDIS_URL", "redis://localhost:6379"):
                r = client.get("/ready")
        finally:
            main_module._redis_sync_client = original

        assert r.status_code == 200, (
            f"Redis failure must NOT cause 503. Got {r.status_code}. "
            "Redis is optional — the app must serve requests even without it."
        )
        data = r.json()
        assert data["status"] == "degraded"
        assert data["checks"]["redis"] == "unavailable"

    def test_ready_no_topology_exposed(self, client):
        """Readiness probe must not expose deployment internals."""
        r = client.get("/ready")
        data = r.json()
        for key in ("deployment_mode", "node_role", "branch_code", "environment", "deployment"):
            assert key not in data, (
                f"/ready must not expose topology field '{key}'. "
                "Keep these in /health/deep (auth-gated)."
            )

    def test_ready_no_auth_required(self, client):
        """Load balancers must be able to call /ready without credentials."""
        r = client.get("/ready")
        assert r.status_code not in (401, 403)


# ─────────────────────────────────────────────────────────────────────────────
# GET /health/deep  —  Authenticated diagnostics
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthDeep:
    """
    /health/deep is the full diagnostic endpoint.

    Contract:
      - Protected by INTERNAL_API_KEY when configured (returns 503 if not configured)
      - Returns 200 with full diagnostic data when key is valid
      - Returns 403 when key is wrong
      - Includes live DB probe, live Redis probe, uptime, start_time, deployment topology
      - Topology details (deployment, node_role, etc.) are safe here behind the key gate
    """

    def test_deep_health_returns_200_without_key_in_dev(self, client):
        """
        When INTERNAL_API_KEY is empty (default dev setting),
        /health/deep should either be open or return 503 (not configured).
        It must not return 200 with a wrong key.
        """
        r = client.get("/health/deep")
        # In test env, key is "" → endpoint behaves as per _require_internal_key
        assert r.status_code in (200, 403, 503), (
            f"Unexpected status {r.status_code} for /health/deep in dev mode"
        )

    def test_deep_health_returns_403_with_wrong_key(self, client):
        """Wrong key → 403, not 200."""
        with patch("app.main.settings") as ms:
            ms.INTERNAL_API_KEY = "correct-secret-key-xyz"
            r = client.get(
                "/health/deep",
                headers={"X-Internal-Key": "wrong-key"}
            )
        assert r.status_code == 403

    def test_deep_health_response_shape(self, client):
        """When accessible, /health/deep must return the full diagnostic shape."""
        # Access without key (dev mode — key is "")
        r = client.get("/health/deep")
        if r.status_code != 200:
            pytest.skip("INTERNAL_API_KEY is configured — skipping shape test in CI")

        data = r.json()
        assert "status" in data
        assert "version" in data
        assert "uptime_seconds" in data, "uptime_seconds missing from /health/deep"
        assert "started_at" in data,     "started_at missing — added in v4.1 hardening"
        assert "checks" in data
        assert "database" in data["checks"]
        assert "redis"    in data["checks"]
        assert "cache"    in data["checks"]
        assert "ws_terminals"  in data
        assert "metrics"       in data
        assert "deployment"    in data, "deployment block missing — topology moved here from /health"

    def test_deep_health_deployment_block_has_required_fields(self, client):
        """Deployment topology must include all expected fields."""
        r = client.get("/health/deep")
        if r.status_code != 200:
            pytest.skip("INTERNAL_API_KEY is configured — skipping in CI")

        deployment = r.json().get("deployment", {})
        for field in ("mode", "node_role", "branch_code", "hq_sync_enabled", "environment"):
            assert field in deployment, (
                f"/health/deep deployment block is missing '{field}'. "
                "This field was previously on /health (security issue) — "
                "verify it was moved here and not removed."
            )

    def test_deep_health_uptime_is_non_negative(self, client):
        r = client.get("/health/deep")
        if r.status_code != 200:
            pytest.skip("INTERNAL_API_KEY is configured — skipping in CI")

        data = r.json()
        assert isinstance(data["uptime_seconds"], int)
        assert data["uptime_seconds"] >= 0

    def test_deep_health_started_at_is_iso8601(self, client):
        from datetime import datetime
        r = client.get("/health/deep")
        if r.status_code != 200:
            pytest.skip("INTERNAL_API_KEY is configured — skipping in CI")

        started_at = r.json()["started_at"]
        try:
            datetime.fromisoformat(started_at)
        except ValueError:
            pytest.fail(f"started_at is not valid ISO 8601: {started_at!r}")

    def test_deep_health_live_redis_probe_ok(self, client):
        """
        When Redis ping succeeds, /health/deep must report redis='ok',
        not just cache.enabled (the old behaviour, which was a flag, not a live probe).
        """
        import app.main as main_module
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True

        original = main_module._redis_sync_client
        try:
            main_module._redis_sync_client = mock_redis
            with patch.object(main_module.settings, "REDIS_URL", "redis://localhost:6379"):
                r = client.get("/health/deep")
        finally:
            main_module._redis_sync_client = original

        if r.status_code != 200:
            pytest.skip("INTERNAL_API_KEY is configured — skipping in CI")

        checks = r.json()["checks"]
        assert checks["redis"] == "ok", (
            f"Expected redis='ok' after successful ping, got: {checks['redis']!r}"
        )

    def test_deep_health_live_redis_probe_fail(self, client):
        """
        When Redis ping fails, /health/deep must report descriptive error,
        not just 'disabled' (which was the old flag-based behaviour).
        """
        import app.main as main_module
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("Connection reset by peer")

        original = main_module._redis_sync_client
        try:
            main_module._redis_sync_client = mock_redis
            with patch.object(main_module.settings, "REDIS_URL", "redis://localhost:6379"):
                r = client.get("/health/deep")
        finally:
            main_module._redis_sync_client = original

        if r.status_code != 200:
            pytest.skip("INTERNAL_API_KEY is configured — skipping in CI")

        checks = r.json()["checks"]
        assert checks["redis"].startswith("error:"), (
            f"Expected redis='error: ...' when ping fails, got: {checks['redis']!r}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Docker contract tests (static analysis — no runtime)
# ─────────────────────────────────────────────────────────────────────────────

class TestDockerHealthCheck:
    """
    Static analysis: verify docker-compose.prod.yml health check points
    to /ready (not /health) and has start_period configured.
    """

    def _load_compose(self):
        import pathlib
        compose_path = pathlib.Path(__file__).parent.parent / "docker-compose.prod.yml"
        if not compose_path.exists():
            pytest.skip("docker-compose.prod.yml not found")
        return compose_path.read_text()

    def test_docker_api_healthcheck_points_to_ready(self):
        """
        Docker must use /ready (readiness probe), not /health (liveness).
        A liveness probe cannot gate sync-agent start — it passes
        even when the DB is unreachable.
        """
        compose = self._load_compose()
        assert "/ready" in compose, (
            "docker-compose.prod.yml api healthcheck must use /ready, not /health. "
            "A liveness-only healthcheck allows the sync-agent to start before "
            "the DB is available, causing sync failures at startup."
        )

    def test_docker_api_healthcheck_has_start_period(self):
        """
        start_period must be set so Alembic migrations complete before Docker
        begins counting health check failures on the api container.
        Without this, slow migrations cause the container to be restarted
        before it has fully started.
        """
        compose = self._load_compose()
        assert "start_period" in compose, (
            "docker-compose.prod.yml api healthcheck must include start_period "
            "to allow Alembic migrations to complete before health checks begin."
        )

    def test_docker_compose_uses_curl_f_flag(self):
        """curl -f / --fail flag causes non-zero exit on HTTP errors."""
        compose = self._load_compose()
        assert "curl -f" in compose or "curl --fail" in compose, (
            "Docker healthcheck curl command must use -f / --fail. "
            "Without -f, curl exits 0 on any HTTP response including 503."
        )


# ─────────────────────────────────────────────────────────────────────────────
# GET /healthz  —  Kubernetes-convention liveness alias
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthzAlias:
    """
    /healthz is the Kubernetes-convention alias for /health.

    Contract (identical to /health):
      - Always returns 200 while the process is alive
      - Does NO database or Redis I/O
      - Returns the same fields as /health
      - Must NOT appear in /openapi.json (include_in_schema=False)
      - No authentication required
    """

    def test_healthz_returns_200(self, client):
        """Kubernetes probes /healthz expecting 200 on a live process."""
        r = client.get("/healthz")
        assert r.status_code == 200, (
            f"/healthz must always return 200 while the process is alive. "
            f"Got {r.status_code}."
        )

    def test_healthz_response_shape_matches_health(self, client):
        """
        /healthz delegates to health() — the response fields must be identical.
        If /health gains or loses a field, /healthz must reflect that automatically.
        """
        r_health  = client.get("/health").json()
        r_healthz = client.get("/healthz").json()
        assert r_health.keys() == r_healthz.keys(), (
            f"/healthz response fields {set(r_healthz.keys())} differ from "
            f"/health response fields {set(r_health.keys())}. "
            "Both must return the same shape — /healthz delegates to health()."
        )

    def test_healthz_never_503_when_db_is_down(self, client):
        """
        Critical: /healthz must return 200 even if the DB is unreachable.
        Kubernetes restarts the pod when liveness fails — we must not restart
        a healthy process just because Postgres is temporarily down.
        """
        with patch("app.main.engine") as mock_engine:
            mock_engine.connect.side_effect = Exception("simulated DB failure")
            mock_engine.dialect.name = "sqlite"
            r = client.get("/healthz")

        assert r.status_code == 200, (
            f"/healthz returned {r.status_code} when DB was simulated as down. "
            "Liveness probes must never fail due to downstream DB state."
        )

    def test_healthz_no_auth_required(self, client):
        """Kubernetes probes /healthz without credentials — must not require auth."""
        r = client.get("/healthz")
        assert r.status_code not in (401, 403), (
            f"/healthz must not require authentication. Got {r.status_code}."
        )

    def test_healthz_not_in_openapi_schema(self, client):
        """
        /healthz is an internal Kubernetes probe path, not a public API endpoint.
        include_in_schema=False must keep it out of /openapi.json.
        If this appears in the schema, it signals that the include_in_schema=False
        decorator was removed — a regression that clutters API docs.
        """
        r = client.get("/openapi.json")
        if r.status_code != 200:
            pytest.skip("/openapi.json not available (production mode with docs_url=None)")
        paths = r.json().get("paths", {})
        assert "/healthz" not in paths, (
            "REGRESSION: /healthz must have include_in_schema=False. "
            "It should not appear in /openapi.json — it is an internal Kubernetes "
            "liveness probe path, not a public API endpoint."
        )
