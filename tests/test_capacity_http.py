import asyncio

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
