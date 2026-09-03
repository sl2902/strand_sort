import pytest
from fastapi.testclient import TestClient
from strand_sort.main import app


@pytest.fixture
def client():
    return TestClient(app)