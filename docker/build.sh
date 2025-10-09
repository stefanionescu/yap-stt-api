#!/usr/bin/env bash
set -euo pipefail

# Yap STT API - Docker build and push script
# Behavior preserved; structure modularized; parameter names clarified.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DEFAULT_PLATFORM="linux/amd64"

print_usage() {
    cat << 'EOF'
Usage: ./docker/build.sh [OPTIONS] <username/image:tag>

Build and push Yap STT API Docker image to DockerHub.
Always builds with cache, then pushes to registry.

ARGUMENTS:
  <username/image:tag>    Full image name (e.g., myuser/yap-stt-api:latest)

OPTIONS:
  --platform PLATFORM     Target platform (default: linux/amd64)
  -h, --help              Show this help

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

validate_image_ref() {
    local image_ref="$1"
    if [[ -z "${image_ref}" ]]; then
        echo "Error: Image name required" >&2
        print_usage
        exit 1
    fi
    # Validate image format (username/image:tag) - keep logic identical
    if [[ ! "${image_ref}" =~ ^[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+:[a-zA-Z0-9._-]+$ ]]; then
        echo "Error: Invalid image format. Use: username/image:tag" >&2
        echo "Example: myuser/yap-stt-api:latest" >&2
        exit 1
    fi
}

split_image_ref() {
    # Echo three values: username image_name tag
    local image_ref="$1"
    local username image_name tag
    username="$(echo "${image_ref}" | cut -d'/' -f1)"
    image_name="$(echo "${image_ref}" | cut -d'/' -f2 | cut -d':' -f1)"
    tag="$(echo "${image_ref}" | cut -d':' -f2)"
    echo "${username}" "${image_name}" "${tag}"
}

check_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        echo "Error: Docker not found. Please install Docker." >&2
        exit 1
    fi
    echo "Checking DockerHub login..."
    if ! docker system info >/dev/null 2>&1; then
        echo "Warning: Docker daemon not accessible"
    fi
    # Skip login check - let Docker handle auth errors during push
}

build_image() {
    local image_ref="$1"
    local platform="$2"
    local -a build_args=(
        build
        -f docker/Dockerfile
        -t "${image_ref}"
        --platform "${platform}"
        .
    )

    echo "=== Building Docker image ==="
    echo "Running: docker ${build_args[*]}"
    if ! DOCKER_BUILDKIT=1 docker "${build_args[@]}"; then
        echo "❌ Build failed!" >&2
        exit 1
    fi
    echo "✅ Build complete: ${image_ref}"
}

show_image_info() {
    local image_ref="$1"
    docker images "${image_ref}" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
}

push_image() {
    local image_ref="$1"
    echo
    echo "=== Pushing to DockerHub ==="
    echo "Running: docker push ${image_ref}"
    if ! docker push "${image_ref}"; then
        echo "❌ Push failed!" >&2
        exit 1
    fi
    echo "✅ Push complete: ${image_ref}"
}

print_run_instructions() {
    local username="$1"
    local image_name="$2"
    local image_ref="$3"
    echo
    echo "Image available at: https://hub.docker.com/r/${username}/${image_name}"
    echo
    echo "=== Usage Instructions ==="
    echo "Run your image:"
    echo "  docker run --rm -it --gpus all -p 8000:8000 \\
    -e KYUTAI_API_KEY=your_secret_here \\
    ${image_ref}"
    echo
    echo "Test the server:"
    echo "  docker exec -e KYUTAI_API_KEY=your_secret_here <container_id> \\
    python3 /workspace/test/warmup.py --server 127.0.0.1:8000"
    echo
    echo "Done! 🚀"
}

main() {
    local platform="${DEFAULT_PLATFORM}"
    local image_ref=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --platform)
                platform="$2"
                shift 2
                ;;
            -h|--help)
                print_usage
                exit 0
                ;;
            -*)
                echo "Error: Unknown option $1" >&2
                print_usage
                exit 1
                ;;
            *)
                if [[ -z "${image_ref}" ]]; then
                    image_ref="$1"
                else
                    echo "Error: Too many arguments" >&2
                    print_usage
                    exit 1
                fi
                shift
                ;;
        esac
    done

    validate_image_ref "${image_ref}"
    read -r username image_name tag <<< "$(split_image_ref "${image_ref}")"

    echo "=== Yap STT API Docker Build & Push ==="
    echo "Username: ${username}"
    echo "Image: ${image_name}"
    echo "Tag: ${tag}"
    echo "Full: ${image_ref}"
    echo "Platform: ${platform}"
    echo

    check_docker

    cd "${REPO_ROOT}"
    build_image "${image_ref}" "${platform}"
    show_image_info "${image_ref}"
    push_image "${image_ref}"
    print_run_instructions "${username}" "${image_name}" "${image_ref}"
}

main "$@"