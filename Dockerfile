FROM public.ecr.aws/lambda/python:3.12

# Install uv for fast, lockfile-accurate dependency resolution
RUN pip install --no-cache-dir uv

# Copy dependency manifests first so Docker can cache this layer
COPY pyproject.toml uv.lock ./

# Export the locked, production-only dependency set and install it
# directly into the Lambda task root (where the runtime looks for imports)
RUN uv export --frozen --no-dev --no-editable --no-emit-project -o requirements.txt \
    && pip install --no-cache-dir -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

# Copy application source
COPY src/strand_sort ${LAMBDA_TASK_ROOT}/strand_sort

# Lambda entry point: <module>.<handler variable>
CMD ["strand_sort.lambda_handler.handler"]