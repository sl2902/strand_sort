from mangum import Mangum

from strand_sort.main import app

# API Gateway invokes this directly — Mangum translates the event into an
# ASGI request against the existing FastAPI app unchanged. Requires
# storage_backend=s3 and db_engine=dynamodb (see config.py) since Lambda has
# no persistent local disk shared across invocations.
handler = Mangum(app)
