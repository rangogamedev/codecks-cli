#!/usr/bin/env bash
# Build the codecks-cli Docker image via Compose.
# Run once, or again after changing pyproject.toml dependencies.
# Optional: PYTHON_VERSION=3.14 ./docker/build.sh
set -e
cd "$(dirname "$0")/.."

build_args=""
if [ -n "$PYTHON_VERSION" ]; then
  build_args="--build-arg PYTHON_VERSION=$PYTHON_VERSION"
fi

docker compose build $build_args
echo "Build complete. Run ./docker/test.sh to verify."
