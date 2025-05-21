
#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Default to development environment if not specified
ENVIRONMENT=${1:-dev}

# Validate environment parameter
if [ "$ENVIRONMENT" != "dev" && "$ENVIRONMENT" != "prod" ]; then
  echo "Error: Environment must be either 'dev' or 'prod'"
  echo "Usage: ./deploy.sh [dev|prod]"
  exit 1
fi

# Set environment file and compose files based on environment
ENV_FILE=".env.${ENVIRONMENT}"
echo "Using environment file: $ENV_FILE"
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.${ENVIRONMENT}.yml"
echo "Using compose files: $COMPOSE_FILES"
PROJECT_NAME="ikmimart_${ENVIRONMENT}"
echo "Using project name: $PROJECT_NAME"

# Check if the environment file exists
if [ ! -f "$ENV_FILE" ]; then
  echo "Error: Environment file $ENV_FILE not found!"
  exit 1
fi

# Stop and remove existing containers
echo "Stopping existing Docker Compose services for ${ENVIRONMENT} environment (if any)..."
docker compose -p $PROJECT_NAME $COMPOSE_FILES --env-file $ENV_FILE down

# Start services
echo "Building and starting new Docker Compose services for ${ENVIRONMENT} environment..."
docker compose -p $PROJECT_NAME $COMPOSE_FILES --env-file $ENV_FILE up -d --build

# Wait a few seconds to make sure DB is ready
echo "Waiting for database to be ready..."
sleep 3  # (you can adjust depending on how fast your DB starts)

# 🔧 Run migrations
echo "🔧 Running migrations..."
if ! docker compose -p $PROJECT_NAME $COMPOSE_FILES --env-file $ENV_FILE run --rm "${PROJECT_NAME}_migrate"; then
  echo "Warning: Migration step failed. Continuing deployment anyway."
else
  echo "Migrations services is removed."
fi

# Display different messages based on environment with dynamic port extraction
if [ "$ENVIRONMENT" = "dev" ]; then
  # Extract port from environment file (assuming PORT or APP_PORT variable exists)
  if grep -q "PORT=" "$ENV_FILE"; then
    PORT=$(grep "PORT=" "$ENV_FILE" | cut -d'=' -f2)
    echo "Deployment complete! Development environment is now running at http://localhost:$PORT"
  elif grep -q "APP_PORT=" "$ENV_FILE"; then
    PORT=$(grep "APP_PORT=" "$ENV_FILE" | cut -d'=' -f2)
    echo "Deployment complete! Development environment is now running at http://localhost:$PORT"
  else
    echo "Deployment complete! Development environment is now running."
  fi
else
  echo "Deployment complete! Production environment is now running"
fi

# Show logs
docker compose -p $PROJECT_NAME $COMPOSE_FILES --env-file $ENV_FILE logs -f