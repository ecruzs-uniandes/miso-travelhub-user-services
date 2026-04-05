import pytest


@pytest.mark.asyncio
async def test_health_check_returns_200(async_client):
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "user-services"
    assert data["version"] == "1.0.0"
