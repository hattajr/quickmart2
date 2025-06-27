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

2. Deploy using Docker Compose:
   - For Production:
      ```bash
      docker compose -p ikmimart_prod -f docker-compose.base.yml -f docker-compose.prod.yml --env-file .env.prod up -d
      ```
   - For Development at port `http://192.168.50.14:8001`:
      ```bash
      docker compose -p ikmimart_dev -f docker-compose.base.yml -f docker-compose.dev.yml --env-file .env.dev up -d
      ```   


