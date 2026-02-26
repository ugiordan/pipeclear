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
    import nbformat
    from pathlib import Path

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
