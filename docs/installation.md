# Installation

## Prerequisites

- **Python 3.13+** — Titlani uses modern Python features
- **uv** (recommended) or **pip** — Package installer

## Install with uv

```bash
uv add titlani
```

## Install with pip

```bash
pip install titlani
```

## Verify Installation

```bash
titlani version
```

You should see output like:

```
Titlani v0.1.0
```

## Development Install

To contribute to Titlani or run from source:

```bash
git clone https://github.com/alanbato/titlani.git
cd titlani
uv sync
```

This installs all runtime and development dependencies. Run the test suite to verify:

```bash
uv run pytest
```

### Development Dependencies

The dev group includes:

- **pytest** + plugins — Testing framework
- **ruff** — Linting and formatting
- **ty** — Type checking
- **hypothesis** — Property-based testing

### Documentation Dependencies

To build the docs locally:

```bash
uv sync --group docs
uv run mkdocs serve
```
