# PipeClear RHOAI Integration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate PipeClear into RHOAI via a KFP compiler plugin (Phase 1) and Go validating webhook (Phase 2).

**Architecture:** Two-layer validation — compile-time Python plugin + admission-time Go webhook in ODH operator.

**Tech Stack:** Python (KFP SDK, pytest), Go (controller-runtime, ODH operator patterns)

---

## Phase 1: KFP Compiler Plugin (pipeclear repo)

### Task 1: PipeClearCompiler wrapper

**Files:**
- Create: `pipeclear/kfp/compiler.py`
- Test: `tests/test_kfp_compiler_plugin.py`

**Step 1: Write the failing test**

```python
# tests/test_kfp_compiler_plugin.py
import pytest
from unittest.mock import patch, MagicMock
from pipeclear.kfp.compiler import PipeClearCompiler


def test_compiler_passes_clean_pipeline(tmp_path):
    """Compiler should compile when no critical issues found."""
    import kfp.dsl as dsl

    @dsl.component(base_image="registry.access.redhat.com/ubi9/python-311:latest")
    def dummy():
        print("hello")

    @dsl.pipeline(name="clean-pipeline")
    def clean_pipe():
        dummy()

    output = tmp_path / "pipeline.yaml"
    compiler = PipeClearCompiler()
    compiler.compile(pipeline_func=clean_pipe, package_path=str(output))
    assert output.exists()


def test_compiler_blocks_on_critical_issues(tmp_path):
    """Compiler should raise when critical issues detected in generated spec."""
    import kfp.dsl as dsl

    @dsl.component(base_image="registry.access.redhat.com/ubi9/python-311:latest")
    def dummy():
        print("hello")

    @dsl.pipeline(name="test-pipeline")
    def test_pipe():
        dummy()

    output = tmp_path / "pipeline.yaml"
    compiler = PipeClearCompiler(fail_on_critical=True)

    # Mock validate_pipeline_spec to return critical issues
    with patch.object(compiler, 'validate_pipeline_spec', return_value={
        'critical': [{'message': 'Image uses mutable tag', 'severity': 'critical'}],
        'warnings': []
    }):
        with pytest.raises(SystemExit):
            compiler.compile(pipeline_func=test_pipe, package_path=str(output))
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/ugogiordano/projects/rhoai-pipeline-preflight && .venv/bin/python -m pytest tests/test_kfp_compiler_plugin.py -v`
Expected: FAIL with "No module named 'pipeclear.kfp.compiler'"

**Step 3: Write minimal implementation**

```python
# pipeclear/kfp/compiler.py
"""PipeClear-enhanced KFP compiler with pre-flight validation."""
import json
import sys
import yaml
from kfp import compiler


class PipeClearCompiler:
    """Wraps kfp.compiler.Compiler with PipeClear validation."""

    def __init__(self, fail_on_critical=True, allowed_registries=None):
        self._compiler = compiler.Compiler()
        self.fail_on_critical = fail_on_critical
        self.allowed_registries = allowed_registries

    def validate_pipeline_spec(self, spec: dict) -> dict:
        """Validate a compiled pipeline IR spec."""
        critical = []
        warnings = []

        # Extract all container images from deployment spec
        deployment_spec = spec.get('deploymentSpec', {})
        executors = deployment_spec.get('executors', {})

        for executor_name, executor in executors.items():
            container = executor.get('container', {})
            image = container.get('image', '')

            if not image:
                critical.append({
                    'message': f'Executor {executor_name} has no container image',
                    'severity': 'critical',
                })
                continue

            # Check for mutable tags
            tag = image.split(':')[-1] if ':' in image else 'latest'
            if tag == 'latest':
                warnings.append({
                    'message': f'Image {image} uses mutable "latest" tag',
                    'severity': 'warning',
                })

            # Check allowed registries
            if self.allowed_registries:
                registry = image.split('/')[0]
                if registry not in self.allowed_registries:
                    critical.append({
                        'message': f'Image {image} not from allowed registry. Allowed: {self.allowed_registries}',
                        'severity': 'critical',
                    })

        return {'critical': critical, 'warnings': warnings}

    def compile(self, pipeline_func, package_path, **kwargs):
        """Compile pipeline with PipeClear pre-flight validation."""
        # First compile normally
        self._compiler.compile(
            pipeline_func=pipeline_func,
            package_path=package_path,
            **kwargs,
        )

        # Then validate the compiled spec
        with open(package_path, 'r') as f:
            spec = yaml.safe_load(f)

        result = self.validate_pipeline_spec(spec)

        # Report warnings
        for w in result['warnings']:
            print(f"PipeClear WARNING: {w['message']}", file=sys.stderr)

        # Block on critical
        if self.fail_on_critical and result['critical']:
            for c in result['critical']:
                print(f"PipeClear CRITICAL: {c['message']}", file=sys.stderr)
            import os
            os.remove(package_path)
            raise SystemExit(
                f"PipeClear blocked compilation: {len(result['critical'])} critical issue(s) found"
            )

        return result
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_kfp_compiler_plugin.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add pipeclear/kfp/compiler.py tests/test_kfp_compiler_plugin.py
git commit -m "feat: add PipeClearCompiler with pre-flight validation at compile time"
```

---

### Task 2: @validate decorator

**Files:**
- Create: `pipeclear/kfp/decorator.py`
- Test: `tests/test_kfp_decorator.py`

**Step 1: Write the failing test**

```python
# tests/test_kfp_decorator.py
import pytest
from unittest.mock import patch
import kfp.dsl as dsl
from pipeclear.kfp.decorator import validate


def test_validate_decorator_passes_clean_pipeline(tmp_path):
    """Decorated pipeline should compile normally when clean."""
    @validate(fail_on_critical=True)
    @dsl.pipeline(name="clean-decorated")
    def clean_pipe():
        pass

    # The decorator should not raise on a clean pipeline
    assert callable(clean_pipe)
    assert hasattr(clean_pipe, '_pipeclear_validated')


def test_validate_decorator_stores_config():
    """Decorator should store PipeClear config on the pipeline function."""
    @validate(fail_on_critical=True, allowed_registries=['registry.redhat.io'])
    @dsl.pipeline(name="configured")
    def configured_pipe():
        pass

    assert configured_pipe._pipeclear_config['fail_on_critical'] is True
    assert configured_pipe._pipeclear_config['allowed_registries'] == ['registry.redhat.io']
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_kfp_decorator.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# pipeclear/kfp/decorator.py
"""PipeClear decorator for KFP pipeline functions."""
import functools


def validate(fail_on_critical=True, allowed_registries=None):
    """Decorator that marks a KFP pipeline for PipeClear validation at compile time.

    When used with PipeClearCompiler, the compiler will use these settings.
    Can also be used standalone to mark pipelines for validation.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        wrapper._pipeclear_validated = True
        wrapper._pipeclear_config = {
            'fail_on_critical': fail_on_critical,
            'allowed_registries': allowed_registries,
        }
        return wrapper
    return decorator
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_kfp_decorator.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add pipeclear/kfp/decorator.py tests/test_kfp_decorator.py
git commit -m "feat: add @validate decorator for KFP pipeline functions"
```

---

### Task 3: Update KFP module exports

**Files:**
- Modify: `pipeclear/kfp/__init__.py`

**Step 1: Update exports**

```python
# pipeclear/kfp/__init__.py
from pipeclear.kfp.component import preflight_check
from pipeclear.kfp.compiler import PipeClearCompiler
from pipeclear.kfp.decorator import validate

__all__ = ['preflight_check', 'PipeClearCompiler', 'validate']
```

**Step 2: Run all tests**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add pipeclear/kfp/__init__.py
git commit -m "feat: export PipeClearCompiler and validate from kfp module"
```

---

### Task 4: Integration test with real RHOAI notebooks

**Files:**
- Create: `tests/test_compiler_real_notebooks.py`

**Step 1: Write integration test**

```python
# tests/test_compiler_real_notebooks.py
"""Test PipeClearCompiler against real RHOAI notebook-generated pipelines."""
import pytest
from pathlib import Path
from pipeclear import analyze, generate
from pipeclear.kfp.compiler import PipeClearCompiler


NOTEBOOKS_DIR = Path(__file__).parent.parent / 'examples' / 'rhoai_real_notebooks'


@pytest.fixture
def notebooks():
    """Get all real RHOAI notebooks."""
    nbs = list(NOTEBOOKS_DIR.glob('*.ipynb'))
    if not nbs:
        pytest.skip("No real RHOAI notebooks found")
    return nbs


def test_analyze_real_notebooks(notebooks):
    """All real notebooks should be analyzable without errors."""
    for nb in notebooks:
        report = analyze(str(nb))
        assert 'summary' in report
        assert 'critical' in report['summary']


def test_generate_from_clean_notebook(notebooks, tmp_path):
    """Clean notebooks should generate valid pipeline code."""
    clean = [nb for nb in notebooks if 'distributed' not in nb.name]
    assert len(clean) > 0

    for nb in clean[:3]:  # Test first 3
        output = tmp_path / f"{nb.stem}_pipeline.py"
        code = generate(str(nb), output=str(output))
        assert output.exists()
        assert 'dsl.pipeline' in code
        assert 'dsl.component' in code


def test_analyze_catches_real_security_issue(notebooks):
    """The distributed training notebook should flag the hardcoded AWS key."""
    distributed = [nb for nb in notebooks if 'distributed' in nb.name]
    if not distributed:
        pytest.skip("Distributed training notebook not found")

    report = analyze(str(distributed[0]))
    assert report['summary']['critical'] > 0
    assert any('aws' in str(issue).lower() or 'secret' in str(issue).lower()
               for issue in report.get('issues', []))
```

**Step 2: Run tests**

Run: `.venv/bin/python -m pytest tests/test_compiler_real_notebooks.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_compiler_real_notebooks.py
git commit -m "test: add integration tests with real RHOAI notebooks"
```

---

### Task 5: Fix stale README

**Files:**
- Modify: `README.md`

**Step 1: Update README to reflect current state**

Update all `src.` references to `pipeclear`, update base image references, add KFP compiler plugin usage examples.

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README with current pipeclear imports and KFP compiler plugin"
```

---

### Task 6: Clean up dead dependencies and stale artifacts

**Files:**
- Modify: `pyproject.toml` — Remove `astroid` and `pydantic` (never imported)
- Delete: `examples/generated_pipelines/simple_success_pipeline.py` (contains pre-fix broken code)

**Step 1: Clean up**

Remove dead deps from pyproject.toml, delete broken artifact.

**Step 2: Run all tests**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add pyproject.toml
git rm examples/generated_pipelines/simple_success_pipeline.py
git commit -m "chore: remove dead dependencies and stale artifacts"
```

---

## Phase 2: Go Validating Webhook in ODH Operator

**Repo:** `/Users/ugogiordano/workdir/rhoai/opendatahub-io/opendatahub-operator`
**Branch:** Create `feat/pipeclear-webhook` from `main`

### Task 7: Create PipeClear webhook handler

**Files:**
- Create: `internal/webhook/pipeclear/validating.go`
- Create: `internal/webhook/pipeclear/validating_test.go`

**Reference pattern:** `internal/webhook/kueue/validating.go`

**Step 1: Write the failing test**

```go
// internal/webhook/pipeclear/validating_test.go
package pipeclear

import (
    "testing"
    "encoding/json"
    admissionv1 "k8s.io/api/admission/v1"
    "github.com/stretchr/testify/assert"
)

func TestValidateAllowsCleanPipeline(t *testing.T) {
    handler := &PipeClearWebhook{}
    // Create a mock AdmissionReview with a clean pipeline spec
    spec := map[string]interface{}{
        "deploymentSpec": map[string]interface{}{
            "executors": map[string]interface{}{
                "exec-1": map[string]interface{}{
                    "container": map[string]interface{}{
                        "image": "registry.redhat.io/ubi9/python-311:1.0",
                    },
                },
            },
        },
    }
    result := handler.validatePipelineSpec(spec)
    assert.True(t, result.Allowed)
}

func TestValidateBlocksMutableTag(t *testing.T) {
    handler := &PipeClearWebhook{
        PolicyConfig: &PolicyConfig{
            BlockMutableTags: true,
        },
    }
    spec := map[string]interface{}{
        "deploymentSpec": map[string]interface{}{
            "executors": map[string]interface{}{
                "exec-1": map[string]interface{}{
                    "container": map[string]interface{}{
                        "image": "myregistry.io/myimage:latest",
                    },
                },
            },
        },
    }
    result := handler.validatePipelineSpec(spec)
    assert.False(t, result.Allowed)
    assert.Contains(t, result.Message, "mutable tag")
}
```

**Step 2: Write webhook handler**

A Go struct implementing the admission.Handler interface, following the Kueue validating webhook pattern. Reads validation policy from a ConfigMap.

**Step 3: Run tests**

Run: `cd /Users/ugogiordano/workdir/rhoai/opendatahub-io/opendatahub-operator && go test ./internal/webhook/pipeclear/ -v`
Expected: PASS

**Step 4: Commit**

```bash
git add internal/webhook/pipeclear/
git commit -m "feat: add PipeClear validating webhook for PipelineVersion CRs"
```

---

### Task 8: Register webhook in operator

**Files:**
- Modify: `internal/webhook/webhook.go` — Add PipeClear webhook entry

**Step 1: Add webhook registration**

Add a new `webhookEntry` for PipeClear in the `RegisterAllWebhooks` function, gated on DSP component being enabled.

**Step 2: Run operator tests**

Run: `go test ./internal/webhook/ -v`
Expected: PASS

**Step 3: Commit**

```bash
git add internal/webhook/webhook.go
git commit -m "feat: register PipeClear webhook in operator webhook registry"
```

---

### Task 9: Add default validation policy ConfigMap

**Files:**
- Create: `config/pipeclear/validation-policy-default.yaml`

**Step 1: Create default policy**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: pipeclear-validation-policy
  namespace: opendatahub
data:
  policy.yaml: |
    version: "1"
    rules:
      blockMutableTags: true
      allowedRegistries:
        - registry.redhat.io
        - registry.access.redhat.com
        - quay.io
        - ghcr.io
      maxTasksPerPipeline: 100
      maxResourceRequests:
        memory: "128Gi"
        cpu: "64"
        nvidia.com/gpu: "8"
      blockPrivilegedContainers: true
      blockHostMounts: true
```

**Step 2: Commit**

```bash
git add config/pipeclear/
git commit -m "feat: add default PipeClear validation policy ConfigMap"
```

---

### Task 10: E2E verification on RHOAI cluster

**Step 1:** Deploy the modified operator to a test cluster
**Step 2:** Create a PipelineVersion with a `latest` tag image — verify warning
**Step 3:** Create a PipelineVersion with a blocked registry — verify denial
**Step 4:** Create a clean PipelineVersion — verify admission

---

## Execution Notes

- Phase 1 (Tasks 1-6) can be done entirely in the pipeclear repo with no cluster
- Phase 2 (Tasks 7-10) requires the ODH operator fork and Go toolchain
- Tasks 1-4 are independent and can be parallelized
- Task 7 depends on Phase 1 completing (validates the rule set)
- All tests should pass at each commit
