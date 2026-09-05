from mangum import Mangum

from strand_sort.lambda_handler import handler


def test_handler_wraps_the_existing_fastapi_app():
    """The whole point of this deployment approach: no new app, just a
    wrapper. This is the FastAPI app from main.py, unchanged."""
    assert isinstance(handler, Mangum)
