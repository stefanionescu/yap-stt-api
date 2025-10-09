#!/usr/bin/env bash
set -euo pipefail

# One-stop Docker build and push script for Yap STT API
# Usage: ./docker/build.sh [OPTIONS] <username/image:tag>

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Default values
PLATFORM="linux/amd64"

usage() {
    cat << 'EOF'
Usage: ./docker/build.sh [OPTIONS] <username/image:tag>

Build and push Yap STT API Docker image to DockerHub.
Always builds with cache, then pushes to registry.

ARGUMENTS:
  <username/image:tag>    Full image name (e.g., myuser/yap-stt-api:latest)

OPTIONS:
  --platform PLATFORM   Target platform (default: linux/amd64)
  -h, --help            Show this help

EXAMPLES:
  # Build and push latest
  ./docker/build.sh myuser/yap-stt-api:latest
  
  # Build for specific platform
  ./docker/build.sh --platform linux/arm64 myuser/yap-stt-api:latest

REQUIREMENTS:
  - Docker with BuildKit enabled
  - DockerHub login: docker login
  - NVIDIA GPU support for testing (optional)

EOF
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --platform)
            PLATFORM="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        -*)
            echo "Error: Unknown option $1" >&2
            usage
            exit 1
            ;;
        *)
            if [ -z "${IMAGE_TAG:-}" ]; then
                IMAGE_TAG="$1"
            else
                echo "Error: Too many arguments" >&2
                usage
                exit 1
            fi
            shift
            ;;
    esac
done

# Validate image tag
if [ -z "${IMAGE_TAG:-}" ]; then
    echo "Error: Image name required" >&2
    usage
    exit 1
fi

# Validate image format (username/image:tag)
if [[ ! "$IMAGE_TAG" =~ ^[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+:[a-zA-Z0-9._-]+$ ]]; then
    echo "Error: Invalid image format. Use: username/image:tag" >&2
    echo "Example: myuser/yap-stt-api:latest" >&2
    exit 1
fi

# Extract components
USERNAME=$(echo "$IMAGE_TAG" | cut -d'/' -f1)
IMAGE_NAME=$(echo "$IMAGE_TAG" | cut -d'/' -f2 | cut -d':' -f1)
TAG=$(echo "$IMAGE_TAG" | cut -d':' -f2)

echo "=== Yap STT API Docker Build & Push ==="
echo "Username: $USERNAME"
echo "Image: $IMAGE_NAME"
echo "Tag: $TAG"
echo "Full: $IMAGE_TAG"
echo "Platform: $PLATFORM"
echo

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "Error: Docker not found. Please install Docker." >&2
    exit 1
fi

# Check DockerHub access
echo "Checking DockerHub login..."
if ! docker system info >/dev/null 2>&1; then
    echo "Warning: Docker daemon not accessible"
fi
# Skip login check - let Docker handle auth errors during push

cd "$REPO_ROOT"

# Build phase
echo "=== Building Docker image ==="

BUILD_ARGS=(
    "build"
    "-f" "docker/Dockerfile"
    "-t" "$IMAGE_TAG"
    "--platform" "$PLATFORM"
    "."
)

echo "Running: docker ${BUILD_ARGS[*]}"
if ! DOCKER_BUILDKIT=1 docker "${BUILD_ARGS[@]}"; then
    echo "❌ Build failed!" >&2
    exit 1
fi

echo "✅ Build complete: $IMAGE_TAG"

# Show image info
docker images "$IMAGE_TAG" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"

# Push phase
echo
echo "=== Pushing to DockerHub ==="

echo "Running: docker push $IMAGE_TAG"
if ! docker push "$IMAGE_TAG"; then
    echo "❌ Push failed!" >&2
    exit 1
fi

echo "✅ Push complete: $IMAGE_TAG"
echo
echo "Image available at: https://hub.docker.com/r/$USERNAME/$IMAGE_NAME"

echo
echo "=== Usage Instructions ==="
echo "Run your image:"
echo "  docker run --rm -it --gpus all -p 8000:8000 \\"
echo "    -e KYUTAI_API_KEY=your_secret_here \\"
echo "    $IMAGE_TAG"
echo
echo "Test the server:"
echo "  docker exec -e KYUTAI_API_KEY=your_secret_here <container_id> \\"
echo "    python3 /workspace/test/warmup.py --server 127.0.0.1:8000"
echo
echo "Done! 🚀"