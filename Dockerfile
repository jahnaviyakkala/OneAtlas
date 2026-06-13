# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set the working directory in the container
WORKDIR /app

# Copy the project specification
COPY pyproject.toml ./

# Copy the application code
COPY src/ ./src/

# Install dependencies using uv
RUN uv sync --no-dev

# Hugging Face Spaces route to port 7860 by default
ENV PORT=7860
EXPOSE 7860

# Run the OneAtlas AppSpec Engine API
CMD ["uv", "run", "uvicorn", "compiler.main:app", "--host", "0.0.0.0", "--port", "7860"]
