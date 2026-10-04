.DEFAULT_GOAL := help
SHELL := /bin/bash

BACKEND := backend
FRONTEND := frontend
UV := uv run --project $(BACKEND)
BACKEND_PORT ?= 8099

.PHONY: help install dev dev-backend dev-frontend test test-backend test-frontend \
	lint lint-backend lint-frontend fmt typecheck typecheck-backend typecheck-frontend build

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

install: ## Install backend (uv) and frontend (npm) dependencies
	uv sync --project $(BACKEND)
	cd $(FRONTEND) && npm ci

dev: ## Run backend (port 8099) and frontend dev server together
	@trap 'kill 0' INT TERM EXIT; \
	$(MAKE) --no-print-directory dev-backend & \
	$(MAKE) --no-print-directory dev-frontend & \
	wait

dev-backend: ## Run backend with auto-reload on port 8099
	cd $(BACKEND) && uv run uvicorn cvidee.main:create_app --factory --reload --host 127.0.0.1 --port $(BACKEND_PORT)

dev-frontend: ## Run Vite dev server (proxies /api to the backend)
	cd $(FRONTEND) && npm run dev

test: test-backend test-frontend ## Run all tests

test-backend:
	cd $(BACKEND) && uv run pytest

test-frontend:
	cd $(FRONTEND) && npm test

lint: lint-backend lint-frontend ## Lint and check formatting

lint-backend:
	cd $(BACKEND) && uv run ruff check . && uv run ruff format --check .

lint-frontend:
	cd $(FRONTEND) && npm run lint && npm run format:check

fmt: ## Auto-format and apply safe lint fixes
	cd $(BACKEND) && uv run ruff check --fix . && uv run ruff format .
	cd $(FRONTEND) && npm run lint -- --fix && npm run format

typecheck: typecheck-backend typecheck-frontend ## Run mypy --strict and tsc

typecheck-backend:
	cd $(BACKEND) && uv run mypy

typecheck-frontend:
	cd $(FRONTEND) && npm run typecheck

build: ## Build the frontend
	cd $(FRONTEND) && npm run build
