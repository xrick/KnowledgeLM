# check_milvus_status.sh
#!/usr/bin/env bash
# This script checks the status of the Milvus standalone container.
# It mimics the logic from the official standalone_embed.sh script.

CONTAINER_NAME="milvus-standalone"

# Check for a "healthy" container, matching the logic in standalone_embed.sh
healthy_count=$(sudo docker ps | grep ${CONTAINER_NAME} | grep "healthy" | wc -l)

if [ ${healthy_count} -eq 1 ]; then
    # Success: Found exactly one healthy container
    echo "Milvus is running and healthy."
    exit 0
else
    # Failure: The primary check failed
    echo "Milvus is not running or not healthy."
    echo "Checking container status..."

    # Diagnostic check: See if the container exists at all
    exists_count=$(sudo docker ps -a | grep ${CONTAINER_NAME} | wc -l)

    if [ ${exists_count} -eq 1 ]; then
        # Container exists but is not healthy. Get its current status.
        status=$(sudo docker ps -a --filter "name=${CONTAINER_NAME}" --format "{{.Status}}" | head -n 1)
        echo "Container '${CONTAINER_NAME}' exists but is not healthy. Current status: ${status}"
    else
        # Container was not found
        echo "Container '${CONTAINER_NAME}' not found."
    fi

    exit 1
fi