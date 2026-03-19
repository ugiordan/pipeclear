# PipeClear

**Clear your notebooks for takeoff.** Pre-flight validation for Jupyter notebooks on Red Hat OpenShift AI.

PipeClear catches pipeline failures in seconds — not minutes. It validates notebooks before deployment, scanning for security risks, dependency issues, resource mismatches, and inaccessible container images.

## The Problem

Data scientists write ML code in Jupyter notebooks, then deploy them as pipelines on RHOAI. But the pipeline environment is different — things break silently:

- **Security risks**: Hardcoded AWS keys baked into pipeline containers
- **Missing dependencies**: Packages available locally but not in the pipeline image
- **Invalid images**: Base container image doesn't exist or isn't pullable
- **Resource mismatches**: Notebook needs a GPU but pipeline isn't configured for one

Each failure wastes 10-30 minutes in submit-wait-fail cycles.

## Quick Start

```bash
pip install -e ".[dev]"
```

### CLI

```bash
# Analyze a notebook
pipeclear analyze notebook.ipynb

# Generate a KFP pipeline
pipeclear analyze notebook.ipynb --output pipeline.py

# JSON output for CI/CD
pipeclear analyze notebook.ipynb --format json

# Custom base image
pipeclear analyze notebook.ipynb --base-image registry.redhat.io/ubi9/python-311:latest
```

### Python SDK

```python
from pipeclear import analyze, generate

# Pre-flight validation
report = analyze("notebook.ipynb")
if report['summary']['critical'] > 0:
    print("Issues found!")

# Generate pipeline
code = generate("notebook.ipynb", output="pipeline.py")
```

### KFP Compiler Plugin

```python
from pipeclear.kfp import PipeClearCompiler, validate

# Option A: Compiler wrapper — validates at compile time
compiler = PipeClearCompiler(
    fail_on_critical=True,
    allowed_registries=['registry.redhat.io', 'registry.access.redhat.com']
)
compiler.compile(pipeline_func=my_pipeline, package_path='pipeline.yaml')

# Option B: Decorator — marks pipelines for validation
@validate(fail_on_critical=True)
@dsl.pipeline(name="my-pipeline")
def my_pipeline():
    train_step()
```

### KFP Reusable Component

```python
from pipeclear.kfp import preflight_check

@dsl.pipeline(name="validated-pipeline")
def my_pipeline():
    check = preflight_check(notebook_path="notebook.ipynb")
    train = train_component().after(check)
```

## Validators

| Validator | Checks | Severity |
|-----------|--------|----------|
| **Security Scanner** | AWS keys, API tokens, hardcoded secrets | Critical |
| **Image Validator** | Base image accessibility, registry auth | Critical |
| **Dependency Validator** | PyPI availability, stdlib detection | Warning |
| **Resource Estimator** | GPU/VRAM requirements, model sizes | Warning |

## Real-World Validation

Tested against 7 real notebooks from Red Hat AI Services repos:

- **fraud-detection** (rh-aiservices-bu) — caught hardcoded AWS secret key
- **insurance-claim-processing** — clean
- **llm-on-openshift** (LangChain, RAG) — clean

## Architecture

```
Notebook → Analyzer → Validators → Reporter → Generator
              ↓           ↓          ↓           ↓
           AST Parse   Resource   Issues    KFP Pipeline
                       Deps       (JSON)
                       Security
                       Image
```

**Entry points:** CLI (`pipeclear analyze`), SDK (`from pipeclear import analyze`), KFP component, KFP compiler plugin

## Development

```bash
# Run tests
pytest tests/ -v

# Run with coverage
pytest --cov=pipeclear tests/
```

## RHOAI Integration

PipeClear integrates into RHOAI at two layers:

1. **Compile-time** — KFP compiler plugin validates before pipeline submission
2. **Admission-time** — Go webhook in ODH operator validates PipelineVersion CRs

See `docs/plans/2026-03-19-pipeclear-rhoai-integration-design.md` for the full architecture.

## License

MIT
