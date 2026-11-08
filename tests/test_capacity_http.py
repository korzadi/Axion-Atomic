import asyncio
import json

from sqlalchemy.exc import TimeoutError as SQLAlchemyPoolTimeout

from api.capacity import CapacityExceeded
from api.main import database_pool_exhausted, inference_capacity_exceeded


def test_inference_capacity_is_reported_as_retryable_503():
    response = asyncio.run(inference_capacity_exceeded(None, CapacityExceeded(7)))
    assert response.status_code == 503
    assert response.headers["retry-after"] == "7"


def test_database_pool_exhaustion_is_reported_as_retryable_503():
    response = asyncio.run(database_pool_exhausted(None, SQLAlchemyPoolTimeout("pool exhausted")))
    assert response.status_code == 503
    assert response.headers["retry-after"] == "3"


def test_inference_capacity_response_does_not_expose_internal_exception_text():
    response = asyncio.run(inference_capacity_exceeded(None, CapacityExceeded(5)))

    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    assert "El servicio de inferencia está ocupado" in json.loads(response.body)["detail"]
    assert "CapacityExceeded" not in response.body.decode("utf-8")


def test_database_pool_response_does_not_expose_driver_or_pool_details():
    response = asyncio.run(
        database_pool_exhausted(None, SQLAlchemyPoolTimeout("internal pool connection details"))
    )

    assert response.status_code == 503
    assert response.headers["retry-after"] == "3"
    assert "La base de datos está ocupada" in json.loads(response.body)["detail"]
    body = response.body.decode("utf-8")
    assert "internal pool connection details" not in body
    assert "TimeoutError" not in body
