# RHOAI Pipeline Preflight

**Stop wasting hours on pipeline failures. Know what will break BEFORE you run it.**

RHOAI Pipeline Preflight automatically converts Jupyter notebooks to Kubeflow pipelines while detecting resource issues, dependency problems, and security concerns before deployment.

## The Problem

Data scientists spend hours waiting for pipeline failures:
- **Resource errors**: "Out of memory" after 2 hours of training
- **Dependency hell**: Missing packages discovered at runtime
- **Security risks**: Hardcoded credentials in production pipelines
- **Portability issues**: Absolute paths that don't exist in containers

## The Solution

Pre-flight validation catches issues early:

```bash
$ python -m src.cli analyze my_notebook.ipynb

Pre-Flight Analysis Summary
┏━━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Severity       ┃ Count ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━┩
│ 🚨 Critical    │     2 │
│ ⚠️  Warning    │     1 │
└────────────────┴───────┘

🚨 [RESOURCE] Estimated VRAM requirement (140GB) exceeds available GPU (80GB)
🚨 [SECURITY] Line 5: Hardcoded aws_access_key detected
⚠️  [PORTABILITY] Line 12: Hardcoded path '/Users/data.csv'
```

## Features

### 🔍 Pre-Flight Validators

**Resource Estimator**
- Detects LLM model loading patterns
- Estimates GPU memory requirements
- Warns about cluster capacity mismatches

**Dependency Validator**
- Extracts all package imports
- Checks PyPI availability
- Identifies custom/internal packages

**Security Scanner**
- Detects AWS keys, API tokens, secrets
- Finds hardcoded absolute paths
- Flags portability issues

### 🚀 Zero-Annotation Conversion

Unlike Kale (requires `#pipeline` comments) or Elyra (manual drag-and-drop), we analyze notebooks automatically:

```python
# Your notebook cells
import pandas as pd
from transformers import AutoModel

model = AutoModel.from_pretrained('bert-base')
df = pd.read_csv('data.csv')
```

Becomes a production KFP pipeline - no changes needed!

### 📊 Smart Reporting

Beautiful terminal output with actionable insights:
- Critical issues block deployment
- Warnings suggest improvements
- Exit codes for CI/CD integration

## Installation

```bash
git clone <repo>
cd rhoai-pipeline-preflight
pip install -e ".[dev]"
```

## Usage

### Basic Analysis

```bash
python -m src.cli analyze notebook.ipynb
```

### Generate Pipeline

```bash
python -m src.cli analyze notebook.ipynb --output pipeline.py
```

The generated pipeline is ready for deployment:

```python
from kfp import dsl

@dsl.component(
    base_image="quay.io/modh/runtime-images:ubi9-python-3.11",
    packages_to_install=['pandas', 'transformers']
)
def notebook_component():
    # Your notebook code here
    ...

@dsl.pipeline(name="my_pipeline")
def my_pipeline():
    task = notebook_component()
```

## Demo Notebooks

Try the examples:

```bash
# Clean notebook - passes all checks
python -m src.cli analyze examples/demo_notebooks/1_simple_success.ipynb

# Large model - resource warnings
python -m src.cli analyze examples/demo_notebooks/2_resource_problem.ipynb

# Multiple issues - security + resource + dependency
python -m src.cli analyze examples/demo_notebooks/3_kitchen_sink.ipynb
```

## Architecture

```
Notebook → Analyzer → Validators → Reporter → Generator
              ↓           ↓          ↓           ↓
           AST Parse   Resource   Issues    KFP Pipeline
                       Deps
                       Security
```

**Components:**
- `analyzer.py`: Notebook parsing, import extraction, dependency graphs
- `validators/`: Resource, dependency, and security validators
- `reporter.py`: Issue formatting and summary generation
- `generator.py`: KFP pipeline code generation
- `cli.py`: User-friendly command-line interface

## Development

### Run Tests

```bash
pytest tests/ -v
```

### Test Coverage

```bash
pytest --cov=src tests/
```

## Hackathon Scoring

**Time Savings (40%)**
- Catches failures in seconds vs hours
- No more waiting for pipelines to crash
- Automated conversion saves manual work

**Customer Value (30%)**
- Data scientists ship faster
- Less debugging, more innovation
- Production-ready from day 1

**Innovation (15%)**
- First tool with pre-flight validation
- Zero-annotation conversion
- Smart resource estimation

**Technical Implementation (10%)**
- TDD from start (18 tests, all passing)
- Clean architecture
- Production-ready code

**Presentation (5%)**
- Live demo with real notebooks
- Clear problem → solution narrative
- Measurable impact

## Roadmap

**Post-Hackathon:**
- [ ] Cluster integration via OpenShift MCP
- [ ] Multi-component pipeline splitting
- [ ] Custom resource profiles
- [ ] CI/CD integration
- [ ] VS Code extension

## License

MIT

## Contributors

Built for Red Hat AI Hackathon 2026 by Ugo Giordano
