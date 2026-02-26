#!/usr/bin/env python3
"""Test script to verify RHOAI deployment readiness."""

import sys
from pathlib import Path

print("=" * 60)
print("RHOAI Pipeline Deployment Test")
print("=" * 60)

# Step 1: Generate pipeline from notebook
print("\n[Step 1] Generating pipeline from notebook...")
from pipeclear.analyzer import NotebookAnalyzer
from pipeclear.generator import PipelineGenerator

notebook_path = Path("examples/demo_notebooks/1_simple_success.ipynb")
analyzer = NotebookAnalyzer(notebook_path)
generator = PipelineGenerator()

pipeline_code = generator.generate_pipeline(analyzer, "test_rhoai_pipeline")
output_path = Path("/tmp/test_rhoai_pipeline.py")
output_path.write_text(pipeline_code)

print(f"✓ Pipeline generated: {output_path}")

# Step 2: Verify it's valid Python
print("\n[Step 2] Verifying generated code is valid Python...")
try:
    compile(pipeline_code, '<string>', 'exec')
    print("✓ Generated code is syntactically valid")
except SyntaxError as e:
    print(f"✗ Syntax error: {e}")
    sys.exit(1)

# Step 3: Try to compile to YAML (RHOAI format)
print("\n[Step 3] Compiling to Kubeflow YAML format...")
try:
    import subprocess
    import os

    # Use the generated Python file directly
    yaml_output = Path("/tmp/test_rhoai_pipeline.yaml")

    # Run the generated pipeline file (it has compilation in __main__)
    result = subprocess.run(
        [sys.executable, str(output_path)],
        cwd="/tmp",
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"✗ Compilation failed:")
        print(result.stderr)
        sys.exit(1)

    if yaml_output.exists():
        print(f"✓ Successfully compiled to YAML: {yaml_output}")
        print(f"  Size: {yaml_output.stat().st_size} bytes")
    else:
        print(f"✗ YAML file not created at {yaml_output}")
        sys.exit(1)

except ImportError:
    print("⚠️  kfp not installed - cannot test YAML compilation")
    print("   Install with: pip install kfp")
    print("   (Not required for validation, only for actual deployment)")
except Exception as e:
    print(f"✗ Compilation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Step 4: Check if generated YAML is valid
print("\n[Step 4] Validating generated YAML...")
try:
    import yaml

    with open(yaml_output, 'r') as f:
        yaml_content = yaml.safe_load(f)

    # Check for KFP v2 fields (different structure than v1)
    # KFP v2 has either 'pipelineSpec' or root-level pipeline definition
    has_pipeline_spec = 'pipelineSpec' in yaml_content
    has_components = 'components' in yaml_content
    has_deployment_spec = 'deploymentSpec' in yaml_content

    if not (has_pipeline_spec or (has_components and has_deployment_spec)):
        print(f"✗ Invalid KFP YAML structure")
        print(f"  Found keys: {list(yaml_content.keys())}")
        sys.exit(1)

    print("✓ YAML is valid Kubeflow Pipeline v2 IR format")
    if 'pipelineInfo' in yaml_content:
        print(f"  Pipeline: {yaml_content['pipelineInfo'].get('name', 'unknown')}")
    print(f"  Components: {len(yaml_content.get('components', {}))}")
    print(f"  Deployment specs: {len(yaml_content.get('deploymentSpec', {}).get('executors', {}))}")

except Exception as e:
    print(f"✗ YAML validation failed: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ DEPLOYMENT READINESS TEST PASSED")
print("=" * 60)
print("\nThis pipeline is ready to deploy to RHOAI!")
print("\nNext steps:")
print("  1. Upload to RHOAI cluster using Web UI or CLI")
print("  2. Create a pipeline run")
print("  3. Monitor execution in RHOAI dashboard")
print("\nGenerated files:")
print(f"  - Python: {output_path}")
print(f"  - YAML:   {yaml_output}")
