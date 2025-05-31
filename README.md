# QuickMart2

Product search and recognition application with image processing capabilities.

## Overview

QuickMart2 lets users search grocery products by text or image, using Gemini AI to identify products from photos.

## Tech Stack

- Python 3.12 + FastAPI
- HTMX + Tailwind CSS
- PostgreSQL + Redis
- Gemini AI API
- Polars for data processing
- Docker + Docker Compose

## Features

- Camera-based product search
- Text-based search
- Shopping cart management
- Session tracking and analytics

## Quick Start

1. Set up environment variables in `.env.dev` (development) or `.env.prod` (production)

2. Deploy using the deployment script:
   ```bash
   # For development
   ./deploy.sh dev
   
   # For production
   ./deploy.sh prod
   ```

3. Access at `http://localhost:8000` (or configured APP_PORT)



