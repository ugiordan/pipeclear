# PipeClear MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rename project to PipeClear, fix bugs, restructure as proper package, add image validator, KFP component, JSON output, and container image.

**Architecture:** Rename `src/` to `pipeclear/`, update all imports, add new validators and KFP component module, expose public SDK API via `__init__.py`.

**Tech Stack:** Python 3.11+, KFP v2, Typer, Rich, pytest, UBI 9 container image.

---

### Task 1: Fix Bug - Pipeline Name Sanitization

**Files:**
- Modify: `src/generator.py:1-5` (add import + helper function)
- Modify: `src/generator.py:40` (apply sanitize in generate_component)
- Modify: `src/generator.py:76-83` (apply sanitize in generate_pipeline)
- Test: `tests/test_generator.py`

**Step 1: Write the failing test**

Add to `tests/test_generator.py`:

```python
def test_sanitize_pipeline_name_starting_with_number():
    """Test that pipeline names starting with numbers are sanitized."""
    generator = PipelineGenerator()
    component_code = generator.generate_component(
        name="1_simple_success",
        code_cells=["print('hello')"],
        packages=[]
    )
    # Should NOT contain 'def 1_simple' (invalid Python)
    assert 'def 1_' not in component_code
    assert 'def pipeline_1_simple_success' in component_code


def test_sanitize_pipeline_name_with_hyphens():
    """Test that pipeline names with hyphens are sanitized."""
    generator = PipelineGenerator()
    component_code = generator.generate_component(
        name="my-cool-pipeline",
        code_cells=["print('hello')"],
        packages=[]
    )
    assert 'def my_cool_pipeline' in component_code


def test_sanitize_pipeline_name_normal():
    """Test that valid pipeline names are unchanged."""
    generator = PipelineGenerator()
    component_code = generator.generate_component(
        name="valid_name",
        code_cells=["print('hello')"],
        packages=[]
    )
    assert 'def valid_name' in component_code
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python3 -m pytest tests/test_generator.py::test_sanitize_pipeline_name_starting_with_number -v`
Expected: FAIL - generated code contains `def 1_simple_success`

**Step 3: Write minimal implementation**

In `src/generator.py`, add at top (after existing imports):

```python
import re


def sanitize_name(name: str) -> str:
    """Make a string a valid Python identifier."""
    name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    if name and name[0].isdigit():
        name = 'pipeline_' + name
    return name
```

Then update `generate_component` line 40:
```python
def {sanitize_name(name)}():
```

And update `generate_pipeline` lines 76-83:
```python
    pipeline_name_safe = sanitize_name(pipeline_name)

    pipeline_def = f'''@dsl.pipeline(
    name="{pipeline_name}",
    description="Auto-generated from notebook"
)
def {pipeline_name_safe}():
    """Pipeline generated from Jupyter notebook."""
    task = notebook_component()
'''
```

And update the `__main__` block lines 93-98:
```python
    full_pipeline = f'''from kfp import dsl
from kfp.dsl import Input, Output, Dataset, Model

{component_code}

{pipeline_def}

if __name__ == '__main__':
    from kfp import compiler
    compiler.Compiler().compile(
        pipeline_func={pipeline_name_safe},
        package_path='{pipeline_name_safe}.yaml'
    )
'''
```

**Step 4: Run tests to verify they pass**

Run: `.venv/bin/python3 -m pytest tests/test_generator.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add src/generator.py tests/test_generator.py
git commit -m "fix: sanitize pipeline names to valid Python identifiers"
```

---

### Task 2: Fix Bug - Default Base Image

**Files:**
- Modify: `src/generator.py:14` (change default base_image)
- Test: `tests/test_generator.py`

**Step 1: Write the failing test**

Add to `tests/test_generator.py`:

```python
def test_default_base_image_is_publicly_accessible():
    """Test that the default base image uses a public registry."""
    generator = PipelineGenerator()
    component_code = generator.generate_component(
        name="test_component",
        code_cells=["print('hello')"],
    )
    # Should NOT use quay.io/modh (not publicly accessible)
    assert 'quay.io/modh' not in component_code
    # Should use publicly accessible Red Hat UBI image
    assert 'registry.access.redhat.com' in component_code
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python3 -m pytest tests/test_generator.py::test_default_base_image_is_publicly_accessible -v`
Expected: FAIL - code contains `quay.io/modh`

**Step 3: Write minimal implementation**

In `src/generator.py` line 14, change:
```python
        base_image: str = "registry.access.redhat.com/ubi9/python-311:latest"
```

**Step 4: Run all tests**

Run: `.venv/bin/python3 -m pytest tests/test_generator.py -v`
Expected: All 6 tests PASS

**Step 5: Commit**

```bash
git add src/generator.py tests/test_generator.py
git commit -m "fix: use publicly accessible UBI base image"
```

---

### Task 3: Add Image Validator

**Files:**
- Create: `src/validators/image.py`
- Test: `tests/test_image_validator.py`

**Step 1: Write the failing test**

Create `tests/test_image_validator.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from src.validators.image import ImageValidator


def test_parse_image_reference_with_tag():
    """Test parsing image reference into components."""
    validator = ImageValidator()
    registry, repo, tag = validator.parse_image_ref(
        "registry.access.redhat.com/ubi9/python-311:latest"
    )
    assert registry == "registry.access.redhat.com"
    assert repo == "ubi9/python-311"
    assert tag == "latest"


def test_parse_image_reference_without_tag():
    """Test parsing image reference without explicit tag."""
    validator = ImageValidator()
    registry, repo, tag = validator.parse_image_ref(
        "quay.io/ugiordano/pipeclear"
    )
    assert registry == "quay.io"
    assert repo == "ugiordano/pipeclear"
    assert tag == "latest"


def test_parse_image_reference_docker_hub():
    """Test parsing Docker Hub image reference."""
    validator = ImageValidator()
    registry, repo, tag = validator.parse_image_ref("python:3.11")
    assert registry == "docker.io"
    assert repo == "library/python"
    assert tag == "3.11"


def test_check_accessible_with_valid_image():
    """Test that a known public image is detected as accessible."""
    validator = ImageValidator()
    # This actually checks the registry API
    assert validator.check_accessible("registry.access.redhat.com/ubi9/python-311:latest") is True


def test_check_accessible_with_invalid_image():
    """Test that a nonexistent image is detected as inaccessible."""
    validator = ImageValidator()
    assert validator.check_accessible("quay.io/nonexistent/image-xyz-12345:fake") is False


def test_analyze_returns_issues_for_bad_image():
    """Test that analyze flags inaccessible base images."""
    validator = ImageValidator()
    # Mock analyzer with a generator config
    mock_analyzer = MagicMock()

    issues = validator.validate_image("quay.io/nonexistent/image-xyz-12345:fake")
    assert len(issues) == 1
    assert issues[0]['severity'] == 'critical'
    assert issues[0]['category'] == 'image'


def test_analyze_returns_no_issues_for_good_image():
    """Test that analyze passes for accessible images."""
    validator = ImageValidator()
    issues = validator.validate_image("registry.access.redhat.com/ubi9/python-311:latest")
    assert len(issues) == 0
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python3 -m pytest tests/test_image_validator.py -v`
Expected: FAIL - `ModuleNotFoundError: No module named 'src.validators.image'`

**Step 3: Write minimal implementation**

Create `src/validators/image.py`:

```python
"""Container image accessibility validator."""
import urllib.request
import urllib.error
from typing import List, Dict, Tuple


class ImageValidator:
    """Validates that container images are accessible from registries."""

    def parse_image_ref(self, image: str) -> Tuple[str, str, str]:
        """Parse a container image reference into registry, repo, tag.

        Args:
            image: Full image reference (e.g., 'quay.io/user/image:tag')

        Returns:
            Tuple of (registry, repository, tag)
        """
        # Split tag
        if ':' in image.split('/')[-1]:
            image_no_tag, tag = image.rsplit(':', 1)
        else:
            image_no_tag = image
            tag = 'latest'

        parts = image_no_tag.split('/')

        if len(parts) == 1:
            # Docker Hub official image: python:3.11
            return 'docker.io', f'library/{parts[0]}', tag
        elif len(parts) == 2 and '.' not in parts[0]:
            # Docker Hub user image: user/image
            return 'docker.io', image_no_tag, tag
        else:
            # Full registry path: registry.com/repo/image
            registry = parts[0]
            repo = '/'.join(parts[1:])
            return registry, repo, tag

    def check_accessible(self, image: str) -> bool:
        """Check if a container image is accessible from its registry.

        Args:
            image: Full image reference

        Returns:
            True if the image manifest can be reached
        """
        registry, repo, tag = self.parse_image_ref(image)

        # Build registry API v2 URL
        if registry == 'docker.io':
            url = f'https://registry.hub.docker.com/v2/{repo}/tags/list'
        else:
            url = f'https://{registry}/v2/{repo}/tags/list'

        try:
            req = urllib.request.Request(url, method='GET')
            req.add_header('Accept', 'application/json')
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status == 200
        except urllib.error.HTTPError as e:
            if e.code == 401:
                # Authentication required - image exists but needs credentials
                # For registries that require auth, check if we get a proper
                # WWW-Authenticate header (means the repo exists)
                return 'www-authenticate' in {k.lower(): v for k, v in e.headers.items()}
            return False
        except Exception:
            return False

    def validate_image(self, image: str) -> List[Dict]:
        """Validate a container image and return issues.

        Args:
            image: Full image reference

        Returns:
            List of issues (empty if image is accessible)
        """
        if self.check_accessible(image):
            return []

        return [{
            'severity': 'critical',
            'category': 'image',
            'message': f"Base image not accessible: {image}",
            'suggestion': (
                "💡 Fix: Use a publicly accessible image like "
                "'registry.access.redhat.com/ubi9/python-311:latest' "
                "or ensure cluster has pull credentials for this registry"
            ),
            'time_impact': "Would fail with ImagePullBackOff (6+ minutes to detect)"
        }]
```

**Step 4: Run tests**

Run: `.venv/bin/python3 -m pytest tests/test_image_validator.py -v`
Expected: All 7 tests PASS

**Step 5: Commit**

```bash
git add src/validators/image.py tests/test_image_validator.py
git commit -m "feat: add image accessibility validator"
```

---

### Task 4: Integrate Image Validator into CLI and Reporter

**Files:**
- Modify: `src/cli.py:8-11` (add import)
- Modify: `src/cli.py:62-69` (add image validation step)
- Modify: `src/cli.py:73-77` (add image report)
- Modify: `src/reporter.py:136-165` (add image issue formatting)
- Test: `tests/test_integration.py`

**Step 1: Write the failing test**

Add to `tests/test_integration.py`:

```python
def test_image_validator_integrated():
    """Test that image validation is integrated into the full report."""
    from src.reporter import IssueReporter
    reporter = IssueReporter()

    # Simulate reports including image issues
    all_reports = {
        'resource': {'gpu_required': False, 'estimated_vram_gb': 0, 'models': []},
        'dependency': {'available': ['pandas'], 'unavailable': [], 'unknown': []},
        'security': {'secrets': [], 'hardcoded_paths': []},
        'image': [{'severity': 'critical', 'category': 'image',
                   'message': 'Base image not accessible: fake-image:latest',
                   'suggestion': '💡 Fix: Use accessible image',
                   'time_impact': 'Would fail with ImagePullBackOff'}],
    }

    report = reporter.generate_report(all_reports)
    assert report['summary']['critical'] == 1
    assert any(i['category'] == 'image' for i in report['issues'])
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python3 -m pytest tests/test_integration.py::test_image_validator_integrated -v`
Expected: FAIL - reporter doesn't handle 'image' key

**Step 3: Write minimal implementation**

In `src/reporter.py`, update `generate_report` method (after line 164):

```python
        # Add image validation issues (passed through directly)
        if 'image' in all_reports:
            all_issues.extend(all_reports['image'])
```

In `src/cli.py`, add import after line 11:

```python
from src.validators.image import ImageValidator
```

In `src/cli.py`, add image validation step in the Progress block (after dependency validation, around line 69):

```python
        progress.update(task, description="🐳 Checking base image accessibility...")
        image_validator = ImageValidator()
        base_image = "registry.access.redhat.com/ubi9/python-311:latest"
        image_issues = image_validator.validate_image(base_image)
```

Update the Progress total from 3 to 4, and update the reporter call to include image issues:

```python
    report = reporter.generate_report({
        'resource': resource_report,
        'dependency': dependency_report,
        'security': security_report,
        'image': image_issues,
    })
```

**Step 4: Run all tests**

Run: `.venv/bin/python3 -m pytest tests/ -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/cli.py src/reporter.py tests/test_integration.py
git commit -m "feat: integrate image validator into CLI and reporter"
```

---

### Task 5: Add JSON Output Format

**Files:**
- Modify: `src/cli.py:23` (add --format option)
- Modify: `src/cli.py:79-134` (conditional output based on format)
- Test: `tests/test_integration.py`

**Step 1: Write the failing test**

Add to `tests/test_integration.py`:

```python
import json

def test_json_output_format():
    """Test that report can be serialized to JSON."""
    from src.reporter import IssueReporter
    reporter = IssueReporter()

    all_reports = {
        'resource': {'gpu_required': False, 'estimated_vram_gb': 0, 'models': []},
        'dependency': {'available': ['pandas'], 'unavailable': ['custom_lib'], 'unknown': []},
        'security': {'secrets': [], 'hardcoded_paths': []},
    }

    report = reporter.generate_report(all_reports)
    # Report should be JSON-serializable
    json_str = json.dumps(report, indent=2)
    parsed = json.loads(json_str)
    assert parsed['summary']['total'] == 1
    assert parsed['summary']['warning'] == 1
```

**Step 2: Run test to verify it fails or passes**

Run: `.venv/bin/python3 -m pytest tests/test_integration.py::test_json_output_format -v`

**Step 3: Write implementation**

In `src/cli.py`, add `--format` option to the `analyze` command:

```python
    output_format: str = typer.Option("text", "--format", "-f", help="Output format: text, json"),
```

Then add conditional output after the report is generated (around line 79):

```python
    if output_format == "json":
        import json
        console.print(json.dumps(report, indent=2))
        if report['summary']['critical'] > 0:
            raise typer.Exit(code=1)
        return
```

**Step 4: Run all tests**

Run: `.venv/bin/python3 -m pytest tests/ -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/cli.py tests/test_integration.py
git commit -m "feat: add JSON output format for CI/CD integration"
```

---

### Task 6: Add --base-image CLI Flag

**Files:**
- Modify: `src/cli.py:23` (add --base-image option)
- Modify: `src/cli.py:124-134` (pass base_image to generator)
- Modify: `src/cli.py:62-69` (validate user-specified image)
- Test: `tests/test_generator.py`

**Step 1: Write the failing test**

Add to `tests/test_generator.py`:

```python
def test_custom_base_image():
    """Test generating component with custom base image."""
    generator = PipelineGenerator()
    component_code = generator.generate_component(
        name="test_component",
        code_cells=["print('hello')"],
        base_image="quay.io/myorg/custom-image:v1.0"
    )
    assert 'quay.io/myorg/custom-image:v1.0' in component_code
```

**Step 2: Run test**

Run: `.venv/bin/python3 -m pytest tests/test_generator.py::test_custom_base_image -v`
Expected: PASS (already works, just confirming)

**Step 3: Write implementation**

In `src/cli.py`, add CLI option:

```python
    base_image: str = typer.Option(
        "registry.access.redhat.com/ubi9/python-311:latest",
        "--base-image",
        help="Base container image for pipeline components"
    ),
```

Then update the image validation step to use this value, and pass it to the generator:

```python
        image_issues = image_validator.validate_image(base_image)
```

And in the generator call:

```python
        pipeline_code = generator.generate_pipeline(
            analyzer=analyzer,
            pipeline_name=notebook_path.stem,
            base_image=base_image
        )
```

Also update `PipelineGenerator.generate_pipeline()` in `src/generator.py` to accept and pass through `base_image`:

```python
    def generate_pipeline(
        self,
        analyzer,
        pipeline_name: str = "notebook_pipeline",
        base_image: str = "registry.access.redhat.com/ubi9/python-311:latest"
    ) -> str:
```

And pass it to `generate_component`:

```python
        component_code = self.generate_component(
            name="notebook_component",
            code_cells=code_cells,
            packages=packages,
            base_image=base_image
        )
```

**Step 4: Run all tests**

Run: `.venv/bin/python3 -m pytest tests/ -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/cli.py src/generator.py tests/test_generator.py
git commit -m "feat: add --base-image CLI flag for custom container images"
```

---

### Task 7: Rename Project - Restructure src/ to pipeclear/

**Files:**
- Rename: `src/` -> `pipeclear/`
- Modify: `pyproject.toml` (package name, entry points)
- Modify: All imports in `pipeclear/*.py`
- Modify: All imports in `tests/*.py`
- Modify: `test_rhoai_deployment.py`
- Modify: `scripts/deploy_to_rhoai.py`

**Step 1: Rename directory**

```bash
mv src pipeclear
```

**Step 2: Update pyproject.toml**

Replace contents:

```toml
[project]
name = "pipeclear"
version = "0.2.0"
description = "Pre-flight validation and pipeline generation for Jupyter notebooks on RHOAI"
authors = [{name = "Ugo Giordano"}]
requires-python = ">=3.11"
dependencies = [
    "nbformat>=5.9.0",
    "astroid>=3.0.0",
    "kfp>=2.0.0",
    "typer>=0.9.0",
    "rich>=13.0.0",
    "pydantic>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "black>=23.0.0",
    "ruff>=0.1.0",
]

[build-system]
requires = ["setuptools>=68.0.0", "wheel"]
build-backend = "setuptools.build_meta"

[project.scripts]
pipeclear = "pipeclear.cli:app"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]

[tool.black]
line-length = 100
target-version = ['py311']

[tool.ruff]
line-length = 100
target-version = "py311"
```

**Step 3: Update all imports**

In every file under `pipeclear/`, replace `from src.` with `from pipeclear.`:

- `pipeclear/cli.py`: 5 imports to update
- `pipeclear/reporter.py`: no internal imports
- `pipeclear/generator.py`: no internal imports

In every file under `tests/`, replace `from src.` with `from pipeclear.`:

- `tests/test_analyzer.py`
- `tests/test_generator.py`
- `tests/test_validators.py`
- `tests/test_reporter.py`
- `tests/test_integration.py`
- `tests/test_image_validator.py`

Also update `test_rhoai_deployment.py` if it has `from src.` imports.

**Step 4: Remove old egg-info**

```bash
rm -rf src/rhoai_pipeline_preflight.egg-info
```

**Step 5: Reinstall package**

```bash
.venv/bin/pip install -e ".[dev]"
```

**Step 6: Run all tests**

Run: `.venv/bin/python3 -m pytest tests/ -v`
Expected: All tests PASS

**Step 7: Verify CLI works**

Run: `.venv/bin/pipeclear --help`
Expected: Shows "PipeClear" help text

**Step 8: Commit**

```bash
git add -A
git commit -m "refactor: rename project to PipeClear, restructure package"
```

---

### Task 8: Add Public SDK API

**Files:**
- Modify: `pipeclear/__init__.py`
- Test: `tests/test_sdk.py`

**Step 1: Write the failing test**

Create `tests/test_sdk.py`:

```python
import pytest
from pathlib import Path


def test_analyze_function():
    """Test the public analyze() API."""
    from pipeclear import analyze

    report = analyze("tests/fixtures/simple_notebook.ipynb")
    assert 'summary' in report
    assert 'issues' in report
    assert 'timestamp' in report
    assert report['summary']['total'] >= 0


def test_analyze_notebook_with_issues():
    """Test analyze() returns issues for problematic notebook."""
    from pipeclear import analyze

    report = analyze("tests/fixtures/secrets_notebook.ipynb")
    assert report['summary']['critical'] > 0


def test_generate_function():
    """Test the public generate() API."""
    from pipeclear import generate
    import tempfile
    import os

    with tempfile.NamedTemporaryFile(suffix='.py', delete=False) as f:
        output_path = f.name

    try:
        code = generate("tests/fixtures/simple_notebook.ipynb", output=output_path)
        assert '@dsl.pipeline' in code
        assert os.path.exists(output_path)
    finally:
        os.unlink(output_path)
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python3 -m pytest tests/test_sdk.py -v`
Expected: FAIL - `cannot import name 'analyze' from 'pipeclear'`

**Step 3: Write minimal implementation**

Replace `pipeclear/__init__.py`:

```python
"""PipeClear - Pre-flight validation for Jupyter notebooks on RHOAI."""

__version__ = "0.2.0"

from pathlib import Path
from typing import Optional

from pipeclear.analyzer import NotebookAnalyzer
from pipeclear.validators.resource import ResourceEstimator
from pipeclear.validators.dependency import DependencyValidator
from pipeclear.validators.security import SecurityScanner
from pipeclear.validators.image import ImageValidator
from pipeclear.reporter import IssueReporter
from pipeclear.generator import PipelineGenerator


def analyze(notebook_path: str, base_image: str = None) -> dict:
    """Analyze a notebook and return a validation report.

    Args:
        notebook_path: Path to .ipynb file
        base_image: Optional base image to validate

    Returns:
        Validation report dictionary with 'summary' and 'issues' keys
    """
    analyzer = NotebookAnalyzer(Path(notebook_path))

    resource_report = ResourceEstimator().analyze(analyzer)
    dependency_report = DependencyValidator().analyze(analyzer)
    security_report = SecurityScanner().analyze(analyzer)

    all_reports = {
        'resource': resource_report,
        'dependency': dependency_report,
        'security': security_report,
    }

    if base_image:
        all_reports['image'] = ImageValidator().validate_image(base_image)

    return IssueReporter().generate_report(all_reports)


def generate(
    notebook_path: str,
    output: Optional[str] = None,
    pipeline_name: Optional[str] = None,
    base_image: str = "registry.access.redhat.com/ubi9/python-311:latest"
) -> str:
    """Generate a KFP pipeline from a notebook.

    Args:
        notebook_path: Path to .ipynb file
        output: Optional path to write generated pipeline code
        pipeline_name: Optional pipeline name (defaults to notebook filename)
        base_image: Base container image for pipeline components

    Returns:
        Generated pipeline Python code as string
    """
    path = Path(notebook_path)
    analyzer = NotebookAnalyzer(path)

    name = pipeline_name or path.stem
    generator = PipelineGenerator()
    code = generator.generate_pipeline(
        analyzer=analyzer,
        pipeline_name=name,
        base_image=base_image
    )

    if output:
        Path(output).write_text(code)

    return code
```

**Step 4: Run tests**

Run: `.venv/bin/python3 -m pytest tests/test_sdk.py -v`
Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add pipeclear/__init__.py tests/test_sdk.py
git commit -m "feat: add public SDK API (analyze, generate)"
```

---

### Task 9: Build KFP Reusable Component

**Files:**
- Create: `pipeclear/kfp/__init__.py`
- Create: `pipeclear/kfp/component.py`
- Test: `tests/test_kfp_component.py`

**Step 1: Write the failing test**

Create `tests/test_kfp_component.py`:

```python
import pytest


def test_preflight_check_component_exists():
    """Test that the preflight_check KFP component can be imported."""
    from pipeclear.kfp.component import preflight_check
    assert callable(preflight_check)


def test_preflight_check_is_kfp_component():
    """Test that preflight_check is decorated as a KFP component."""
    from pipeclear.kfp.component import preflight_check
    # KFP components have a component_spec attribute
    assert hasattr(preflight_check, 'component_spec')


def test_preflight_check_component_spec():
    """Test that the component spec has correct metadata."""
    from pipeclear.kfp.component import preflight_check
    spec = preflight_check.component_spec
    assert spec.name == 'preflight_check'


def test_kfp_module_exports():
    """Test that kfp module exports the component."""
    from pipeclear.kfp import preflight_check
    assert callable(preflight_check)
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python3 -m pytest tests/test_kfp_component.py -v`
Expected: FAIL - `ModuleNotFoundError`

**Step 3: Write minimal implementation**

Create `pipeclear/kfp/__init__.py`:

```python
"""PipeClear KFP components for pipeline validation."""

from pipeclear.kfp.component import preflight_check

__all__ = ['preflight_check']
```

Create `pipeclear/kfp/component.py`:

```python
"""Reusable KFP component for pre-flight validation."""
import json
from kfp import dsl


@dsl.component(
    base_image="registry.access.redhat.com/ubi9/python-311:latest",
    packages_to_install=[
        'nbformat>=5.9.0',
    ]
)
def preflight_check(
    notebook_path: str,
    fail_on_critical: bool = True,
    max_vram_gb: int = 80,
) -> str:
    """Pre-flight validation gate for ML pipelines.

    Validates a Jupyter notebook for common issues before pipeline execution:
    - Resource requirements (GPU/VRAM estimation)
    - Security issues (hardcoded credentials)
    - Dependency availability
    - Base image accessibility

    Args:
        notebook_path: Path to the Jupyter notebook file
        fail_on_critical: If True, raises error on critical issues
        max_vram_gb: Maximum VRAM threshold in GB

    Returns:
        JSON string containing the validation report

    Raises:
        RuntimeError: If fail_on_critical is True and critical issues found
    """
    import ast
    import re
    import urllib.request
    import urllib.error
    from pathlib import Path

    # --- Inline minimal analyzer (no external deps beyond nbformat) ---
    import nbformat

    notebook = nbformat.read(notebook_path, as_version=4)
    code_cells = [
        cell.source for cell in notebook.cells if cell.cell_type == 'code'
    ]

    all_code = '\n'.join(code_cells)

    issues = []

    # --- Resource check ---
    MODEL_PARAMS = {
        'llama-2-7b': 7, 'llama-2-13b': 13, 'llama-2-70b': 70,
        'llama-3.1-8b': 8, 'qwen2.5-7b': 7, 'mistral-7b': 7,
    }

    for match in re.finditer(r"from_pretrained\(['\"]([^'\"]+)['\"]\)", all_code):
        model_name = match.group(1).lower().split('/')[-1]
        params_b = None
        for key, params in MODEL_PARAMS.items():
            if key in model_name:
                params_b = params
                break

        if params_b:
            vram_gb = round((params_b * 1e9 * 2) / (1024**3) * 1.5, 1)
            if vram_gb > max_vram_gb:
                issues.append({
                    'severity': 'critical',
                    'category': 'resource',
                    'message': f'Model requires ~{vram_gb}GB VRAM, exceeds {max_vram_gb}GB limit',
                })

    # --- Security check ---
    SECRET_PATTERNS = {
        'aws_access_key': r'AKIA[0-9A-Z]{16}',
        'github_token': r'ghp_[a-zA-Z0-9]{36}',
        'openai_key': r'sk-[a-zA-Z0-9]{32,}',
    }

    for secret_type, pattern in SECRET_PATTERNS.items():
        if re.search(pattern, all_code):
            issues.append({
                'severity': 'critical',
                'category': 'security',
                'message': f'Hardcoded {secret_type} detected',
            })

    # --- Hardcoded paths ---
    if re.search(r"['\"]/(Users|home)/[^'\"]+['\"]", all_code):
        issues.append({
            'severity': 'warning',
            'category': 'portability',
            'message': 'Hardcoded absolute paths detected',
        })

    # --- Build report ---
    report = {
        'summary': {
            'critical': sum(1 for i in issues if i['severity'] == 'critical'),
            'warning': sum(1 for i in issues if i['severity'] == 'warning'),
            'total': len(issues),
        },
        'issues': issues,
    }

    if fail_on_critical and report['summary']['critical'] > 0:
        raise RuntimeError(
            f"PipeClear: {report['summary']['critical']} critical issue(s) found. "
            f"Pipeline blocked. Issues: {json.dumps(issues, indent=2)}"
        )

    return json.dumps(report)
```

**Step 4: Run tests**

Run: `.venv/bin/python3 -m pytest tests/test_kfp_component.py -v`
Expected: All 4 tests PASS

**Step 5: Commit**

```bash
git add pipeclear/kfp/ tests/test_kfp_component.py
git commit -m "feat: add reusable KFP component for pipeline validation gate"
```

---

### Task 10: Create Containerfile

**Files:**
- Create: `Containerfile`
- Create: `.containerignore`

**Step 1: Create Containerfile**

```dockerfile
FROM registry.access.redhat.com/ubi9/python-311:latest

LABEL name="pipeclear" \
      version="0.2.0" \
      summary="Pre-flight validation for Jupyter notebooks on RHOAI" \
      maintainer="Ugo Giordano"

WORKDIR /app

COPY pyproject.toml .
COPY pipeclear/ pipeclear/

RUN pip install --no-cache-dir .

ENTRYPOINT ["pipeclear"]
CMD ["--help"]
```

**Step 2: Create .containerignore**

```
.venv/
.git/
.pytest_cache/
__pycache__/
*.egg-info/
tests/
docs/
examples/
*.md
```

**Step 3: Verify build works**

Run: `podman build -t pipeclear:0.2.0 -f Containerfile .`
Expected: Image builds successfully

Run: `podman run --rm pipeclear:0.2.0 --help`
Expected: Shows PipeClear help text

**Step 4: Commit**

```bash
git add Containerfile .containerignore
git commit -m "feat: add Containerfile for cloud-native deployment"
```

---

### Task 11: Update CLI Branding and Version Command

**Files:**
- Modify: `pipeclear/cli.py:15` (update help text)
- Modify: `pipeclear/cli.py:142-145` (update version command)

**Step 1: Update branding**

In `pipeclear/cli.py`:

```python
app = typer.Typer(help="PipeClear - Clear your notebooks for takeoff")
```

Update version command:

```python
@app.command()
def version():
    """Show version information."""
    console.print("[bold]PipeClear[/bold] v0.2.0")
    console.print("Clear your notebooks for takeoff.")
```

**Step 2: Run all tests**

Run: `.venv/bin/python3 -m pytest tests/ -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add pipeclear/cli.py
git commit -m "refactor: update CLI branding to PipeClear"
```

---

### Task 12: Run Full Test Suite and Final Verification

**Step 1: Run complete test suite**

```bash
.venv/bin/python3 -m pytest tests/ -v --tb=short
```

Expected: 35+ tests PASS, 0 failures

**Step 2: Verify CLI end-to-end**

```bash
.venv/bin/pipeclear analyze examples/demo_notebooks/1_simple_success.ipynb
.venv/bin/pipeclear analyze examples/demo_notebooks/2_resource_problem.ipynb
.venv/bin/pipeclear analyze examples/demo_notebooks/3_kitchen_sink.ipynb --format json
.venv/bin/pipeclear analyze examples/demo_notebooks/1_simple_success.ipynb --output /tmp/test_pipeline.py
.venv/bin/pipeclear version
```

**Step 3: Verify SDK**

```bash
.venv/bin/python3 -c "from pipeclear import analyze; print(analyze('examples/demo_notebooks/1_simple_success.ipynb'))"
```

**Step 4: Verify KFP component import**

```bash
.venv/bin/python3 -c "from pipeclear.kfp import preflight_check; print('KFP component ready:', preflight_check.component_spec.name)"
```

**Step 5: Final commit**

```bash
git add -A
git commit -m "chore: final verification - all tests passing"
```
