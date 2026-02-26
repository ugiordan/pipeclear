# PipeClear MVP Design

**Date:** 2026-02-25
**Author:** Ugo Giordano
**Status:** Approved

## Overview

Rename "rhoai-pipeline-preflight" to **PipeClear** and evolve it from a hackathon PoC into an MVP product. PipeClear validates Jupyter notebooks before deploying them as Kubeflow Pipelines on Red Hat OpenShift AI (RHOAI), catching failures in seconds instead of minutes.

**Tagline:** "Clear your notebooks for takeoff."

## Goals

1. Rename and restructure as a proper Python package (`pip install pipeclear`)
2. Fix known bugs (function naming, base image accessibility)
3. Build a reusable KFP component (validation gate for any pipeline)
4. Add new validators (image accessibility, name sanitization)
5. Support JSON output for CI/CD integration
6. Package as a container image for cloud-native use

## Non-Goals (Deferred)

- OpenShift Operator (Phase 3)
- RHOAI operator component integration (Phase 3)
- VS Code extension
- Multi-component pipeline splitting

## Architecture

### Project Structure

```
pipeclear/
  pipeclear/                  # Python package
    __init__.py               # Public API exports
    cli.py                    # Typer CLI entry point
    analyzer.py               # Notebook parser (AST-based)
    generator.py              # KFP v2 code generator
    reporter.py               # Issue reporting + time savings
    validators/
      __init__.py
      base.py                 # Validator protocol
      resource.py             # GPU/VRAM estimation
      dependency.py           # PyPI availability
      security.py             # Secrets/paths scanning
      image.py                # Container image accessibility (NEW)
    kfp/
      __init__.py
      component.py            # Reusable KFP component (NEW)
  tests/
    test_analyzer.py
    test_generator.py
    test_reporter.py
    test_validators.py
    test_image_validator.py   # NEW
    test_kfp_component.py     # NEW
    test_integration.py
  examples/
    demo_notebooks/
  Containerfile               # NEW
  pyproject.toml              # Updated
  README.md                   # Rewritten
```

### Component Diagram

```
                    ┌─────────────────────────────┐
                    │         PipeClear            │
                    │                              │
  CLI/SDK/KFP ──>   │  ┌──────────┐               │
                    │  │ Analyzer  │ Parse .ipynb   │
                    │  └────┬─────┘               │
                    │       │                      │
                    │  ┌────▼──────────────────┐   │
                    │  │     Validators         │   │
                    │  │  ┌─────────────────┐  │   │
                    │  │  │ ResourceEstimator│  │   │
                    │  │  │ SecurityScanner  │  │   │
                    │  │  │ DependencyValidator│ │   │
                    │  │  │ ImageValidator   │  │   │  NEW
                    │  │  └─────────────────┘  │   │
                    │  └────┬──────────────────┘   │
                    │       │                      │
                    │  ┌────▼─────┐  ┌──────────┐  │
                    │  │ Reporter │  │ Generator │  │
                    │  └──────────┘  └──────────┘  │
                    └─────────────────────────────┘
                              │            │
                         Report         Pipeline
                      (text/json)     (.py / .yaml)
```

### Entry Points

1. **CLI:** `pipeclear analyze notebook.ipynb`
2. **Python SDK:** `from pipeclear import analyze; report = analyze("notebook.ipynb")`
3. **KFP Component:** `from pipeclear.kfp import preflight_check` (used as pipeline step)
4. **Container:** `podman run quay.io/ugiordano/pipeclear analyze notebook.ipynb`

## Detailed Design

### 1. Project Rename

- Package name: `pipeclear`
- CLI command: `pipeclear`
- PyPI: `pipeclear` (verified available)
- Container: `quay.io/ugiordano/pipeclear`
- All `from src.` imports become `from pipeclear.`

### 2. Bug Fixes

**Bug 1: Function names starting with numbers**

Add `sanitize_name()` in `generator.py`:
```python
import re

def sanitize_name(name: str) -> str:
    name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    if name and name[0].isdigit():
        name = 'pipeline_' + name
    if not name.isidentifier():
        name = 'pipeline_' + name
    return name
```

Apply in `generate_component()` and `generate_pipeline()`.

**Bug 2: Inaccessible base image**

Change default from `quay.io/modh/runtime-images:ubi9-python-3.11` to `registry.access.redhat.com/ubi9/python-311:latest`.

Add `--base-image` CLI option.

### 3. Validator Protocol

Standardize the validator interface:

```python
from typing import Protocol, Dict
from pipeclear.analyzer import NotebookAnalyzer

class Validator(Protocol):
    def analyze(self, analyzer: NotebookAnalyzer) -> Dict: ...
```

All validators implement this protocol. Enables plugin-style extension.

### 4. Image Validator (New)

Checks whether the target container image is accessible from a registry:

```python
class ImageValidator:
    def check_accessible(self, image: str) -> bool:
        """Check registry API for image manifest."""
        # Parse image into registry/repo:tag
        # HTTP HEAD to registry v2 manifest endpoint
        # Return True if 200, False otherwise

    def analyze(self, analyzer: NotebookAnalyzer) -> Dict:
        """Check base image accessibility."""
        # Uses the configured base image
        # Returns issues if image not accessible
```

This catches the exact failure discovered during live RHOAI testing.

### 5. KFP Reusable Component

A distributable KFP v2 component that acts as a validation gate:

```python
# pipeclear/kfp/component.py

@dsl.component(
    base_image="quay.io/ugiordano/pipeclear:latest",
)
def preflight_check(
    notebook_path: str,
    fail_on_critical: bool = True,
    max_vram_gb: int = 80,
) -> str:
    """Pre-flight validation gate for ML pipelines."""
    from pipeclear import analyze
    report = analyze(notebook_path)

    if fail_on_critical and report["summary"]["critical"] > 0:
        raise RuntimeError(
            f"PipeClear: {report['summary']['critical']} critical issues found. "
            f"Pipeline blocked."
        )

    return json.dumps(report)
```

Usage in any pipeline:
```python
from pipeclear.kfp import preflight_check

@dsl.pipeline(name="my_training")
def training_pipeline():
    check = preflight_check(notebook_path="notebook.ipynb")
    train = train_model().after(check)
```

### 6. Public SDK API

```python
# pipeclear/__init__.py

from pipeclear.analyzer import NotebookAnalyzer
from pipeclear.reporter import IssueReporter
from pipeclear.generator import PipelineGenerator

def analyze(notebook_path: str, format: str = "dict") -> dict:
    """Analyze a notebook and return validation report."""
    ...

def generate(notebook_path: str, output: str = None, compile: bool = False) -> str:
    """Generate KFP pipeline from notebook."""
    ...
```

### 7. JSON/YAML Output

Add `--format` flag to CLI:

```bash
pipeclear analyze notebook.ipynb --format json
pipeclear analyze notebook.ipynb --format yaml
pipeclear analyze notebook.ipynb --format text  # default (Rich)
```

### 8. Single-Command Compile

Add `--compile` flag that generates YAML directly:

```bash
pipeclear analyze notebook.ipynb --output pipeline.yaml --compile
```

Internally runs KFP compiler after generating the Python code.

### 9. Container Image

```dockerfile
FROM registry.access.redhat.com/ubi9/python-311:latest
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir .
ENTRYPOINT ["pipeclear"]
```

### 10. Roadmap: RHOAI Integration (Phase 3)

Long-term vision: integrate PipeClear as a native component in the RHOAI operator.

- Enabled via DataScienceCluster CR:
  ```yaml
  spec:
    components:
      pipeclear:
        managementState: Managed
  ```
- Automatic validation of all pipeline submissions
- Cluster resource querying (real GPU availability, node capacity)
- Dashboard integration showing validation reports

## Testing Strategy

- Extend existing 26 tests to 40+
- Add tests for: `sanitize_name()`, image validator, JSON output, KFP component, SDK API
- Target >80% code coverage
- All existing tests must pass after rename (import path updates)

## Success Criteria

1. `pip install pipeclear` works
2. `pipeclear analyze notebook.ipynb` produces validation report
3. `pipeclear analyze notebook.ipynb --output pipeline.py --compile` generates deployable YAML
4. KFP component can be imported and used in a pipeline definition
5. Container image runs on OpenShift
6. All 40+ tests pass
7. Image validator catches the bug discovered during live testing
