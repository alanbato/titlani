# Contributing to Titlani

Thank you for your interest in contributing to Titlani! This guide will help you get started.

## Development Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/alanbato/titlani.git
   cd titlani
   ```

2. Install dependencies (requires [uv](https://docs.astral.sh/uv/) and Python 3.13+):

   ```bash
   uv sync
   ```

3. Verify everything works:

   ```bash
   uv run pytest
   ```

## Development Workflow

### Running Tests

```bash
# Full suite
uv run pytest

# Single file or test
uv run pytest tests/test_protocol/test_request.py
uv run pytest tests/test_protocol/test_request.py::TestFromHeader::test_valid_header

# By marker
uv run pytest -m integration
uv run pytest -m "not integration"
```

### Linting and Formatting

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

### Type Checking

```bash
uv run ty check src/
```

## Code Style

- Python 3.13+
- Ruff with line-length 90
- Ruff rules: E, W, F, I, C, B, UP
- pytest with `asyncio_mode = "auto"` (no `@pytest.mark.asyncio` needed)

## Submitting Changes

1. Fork the repository and create a branch from `main`.
2. Make your changes and add tests for new functionality.
3. Ensure all tests pass and linting is clean.
4. Open a pull request with a clear description of the change.

## Building Documentation

```bash
uv sync --group docs
uv run mkdocs serve
```

This starts a local preview at `http://127.0.0.1:8000`.

## Project Structure

The library is split into layers under `src/titlani/`:

- **protocol/** — Wire format parsing, status codes, constants
- **content/** — Gemmail message format and message ID generation
- **identity/** — Misfin identity certificate generation and handling
- **server/** — asyncio.Protocol-based server and mailbox handler
- **client/** — asyncio.Protocol-based client with TOFU support
- **encryption/** — At-rest encryption for stored messages
- **verification/** — Probe-based sender verification
- **gmap/** — GMAP (Gemini Mailbox Access Protocol) support
- **cli/** — CLI commands and utilities

## Questions?

Open an issue on [GitHub](https://github.com/alanbato/titlani/issues) if you have questions or run into problems.
