# Production Deployment Guide

This document describes the production-ready improvements made to the ReAct Travel Agent.

## Summary of Changes

### 1. Configuration Management (`config.py`)
- Centralized configuration with environment variable support
- Validation of required settings (API keys, numeric ranges)
- Type-safe configuration dataclass
- Support for custom budgets, timeouts, and retry settings

**Key Features:**
- Validates API keys at startup
- Configurable retry logic with exponential backoff
- Customizable token limits and context window sizes
- Safe credential handling (never logged or exposed)

### 2. Production Logging (`logging_config.py`)
- Structured JSON logging for production environments
- Human-readable text format for development
- Context-aware logging with extra metadata
- Optional file-based log output

**Usage:**
```bash
# Development (text logs)
python main.py --log-format text --log-level DEBUG

# Production (JSON logs)
python main.py --log-format json --log-level INFO
```

### 3. Retry Logic & Resilience
- Exponential backoff for API failures
- Configurable retry attempts and delays
- Graceful degradation on repeated failures
- Detailed error logging for debugging

### 4. Docker Support
- Multi-stage Dockerfile for minimal image size
- Non-root user for security
- Health check endpoint
- Optimized layer caching

**Build and Run:**
```bash
docker build -t travel-agent .
docker run --env-file .env travel-agent
```

### 5. Enhanced Testing
- Configuration validation tests
- Existing test suite preserved and extended
- Mock-based testing for environment variables

## Environment Variables

See `.env.example` for a complete template. Required variables:

```bash
# API Keys (at least one LLM provider + Tavily)
OPENAI_API_KEY=sk-...
TAVILY_API_KEY=tvly-...

# Optional: Use Groq instead of OpenAI
# GROQ_API_KEY=gsk_...
# OPENAI_BASE_URL=https://api.groq.com/openai/v1
```

## New Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--log-level` | Logging verbosity | INFO |
| `--log-format` | Output format (json/text) | text |
| `--validate-config` | Validate config and exit | - |
| `--max-steps` | Maximum ReAct iterations | 15 |
| `--quiet` | Suppress step output | false |

## Configuration via Environment

All settings can be configured via environment variables:

```bash
# Budget
export HARD_CAP=1000.0

# ReAct Loop
export MAX_STEPS=20
export MAX_TOKENS=1000
export TEMPERATURE=0.3

# Retry Settings
export MAX_RETRIES=5
export API_TIMEOUT=60
export RETRY_BACKOFF_FACTOR=2.0

# Logging
export LOG_LEVEL=DEBUG
export LOG_FORMAT=json
```

## Quick Start

1. **Copy and configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

2. **Validate configuration:**
   ```bash
   python main.py --validate-config
   ```

3. **Run the agent:**
   ```bash
   # Development mode
   python main.py --log-format text --log-level DEBUG
   
   # Production mode
   python main.py --log-format json --log-level INFO --quiet
   ```

4. **Docker deployment:**
   ```bash
   docker build -t travel-agent .
   docker run --env-file .env travel-agent
   ```

## Monitoring & Observability

### Health Checks
The `--validate-config` flag serves as a health check endpoint:
```bash
python main.py --validate-config
```

Returns exit code 0 on success, 1 on failure.

### Log Format Examples

**Text (Development):**
```
2026-01-15 10:30:45 UTC [INFO] travel_agent: Starting ReAct loop with goal: ...
```

**JSON (Production):**
```json
{
  "timestamp": "2026-01-15T10:30:45.123456+00:00",
  "level": "INFO",
  "logger": "travel_agent",
  "message": "Starting ReAct loop with goal: ...",
  "module": "engine",
  "function": "run_react",
  "line": 372
}
```

## Error Handling

The agent now handles these scenarios gracefully:

1. **Missing API Keys**: Clear error message at startup
2. **Rate Limits**: Automatic retry with exponential backoff
3. **Budget Violations**: Intercepts and requests revision
4. **Token Limits**: Dynamic context window management
5. **Network Failures**: Retry logic with configurable attempts

## Security Best Practices

1. **Never commit `.env` files** - use `.env.example` as template
2. **Use non-root user** in Docker containers
3. **Validate all inputs** - configuration validation at startup
4. **Limit file access** - tools restricted to project directory
5. **Sanitize logs** - API keys never logged

## Troubleshooting

### Configuration Errors
```bash
# Check which keys are missing
python main.py --validate-config
```

### Import Errors
```bash
# Install dependencies
pip install -r requirements.txt
```

### Docker Build Issues
```bash
# Clean build
docker build --no-cache -t travel-agent .
```

## Next Steps for Production

1. **Set up monitoring**: Integrate with Prometheus/Grafana
2. **Add alerting**: Configure alerts for repeated failures
3. **Implement rate limiting**: Add request throttling
4. **Database integration**: Store itineraries persistently
5. **API wrapper**: Expose as REST/GraphQL API
6. **CI/CD pipeline**: Automated testing and deployment
