"""
Integration tests for the FastAPI REST endpoints.
Uses httpx AsyncClient with a test database.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["version"] == "1.0.0"


class TestScenesEndpoint:
    @pytest.mark.asyncio
    async def test_list_scenes_empty(self, client):
        resp = await client.get("/api/v1/scenes/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_get_nonexistent_scene(self, client):
        import uuid
        resp = await client.get(f"/api/v1/scenes/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_invalid_extension(self, client, tmp_path):
        fake = tmp_path / "imagery.csv"
        fake.write_text("not a raster")
        files = {"file": ("imagery.csv", fake.open("rb"), "text/csv")}
        data  = {"name": "test", "acquisition_year": "2020"}
        resp  = await client.post("/api/v1/scenes/upload", files=files, data=data)
        assert resp.status_code == 422


class TestAnalysesEndpoint:
    @pytest.mark.asyncio
    async def test_list_analyses_empty(self, client):
        resp = await client.get("/api/v1/analyses/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_get_nonexistent_analysis(self, client):
        import uuid
        resp = await client.get(f"/api/v1/analyses/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_analysis_invalid_scenes(self, client):
        import uuid
        payload = {
            "name": "Test Analysis",
            "scene_t1_id": str(uuid.uuid4()),
            "scene_t2_id": str(uuid.uuid4()),
        }
        resp = await client.post("/api/v1/analyses/", json=payload)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_analysis_same_scene_rejected(self, client):
        import uuid
        same_id = str(uuid.uuid4())
        payload = {
            "name": "Bad Analysis",
            "scene_t1_id": same_id,
            "scene_t2_id": same_id,
        }
        resp = await client.post("/api/v1/analyses/", json=payload)
        assert resp.status_code == 422


class TestOpenAPISchema:
    @pytest.mark.asyncio
    async def test_openapi_schema_reachable(self, client):
        resp = await client.get("/api/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert schema["info"]["title"] == "Dallas Land Use Change Detection API"

    @pytest.mark.asyncio
    async def test_docs_reachable(self, client):
        resp = await client.get("/api/docs")
        assert resp.status_code == 200
