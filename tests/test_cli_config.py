import os
import tempfile
from typer.testing import CliRunner
from pipeclear.cli import app

runner = CliRunner()


def test_analyze_with_config_flag():
    yaml_content = """
mode: audit
allowedRegistries:
  - quay.io/myorg
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        config_path = f.name

    result = runner.invoke(app, ["analyze", "--help"])
    os.unlink(config_path)
    assert "--config" in result.output
