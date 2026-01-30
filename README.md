# RHOAI Pipeline Preflight

Stop wasting hours on pipeline failures. Know what will break before you run it.

## Features

- Zero-annotation notebook-to-pipeline conversion
- Pre-flight validation (resources, dependencies, security)
- Real cluster integration via OpenShift MCP
- Production-ready KFP pipeline generation

## Installation

```bash
pip install -e ".[dev]"
```

## Usage

```bash
rhoai-preflight analyze notebook.ipynb
```

## Development

```bash
pytest tests/
```
