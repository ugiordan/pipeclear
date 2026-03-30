import os
import tempfile
import pytest
from pipeclear.kfp import PipeClearCompiler


class TestPipeClearCompilerFromConfig:
    def test_from_config_yaml(self):
        yaml_content = """
mode: audit
allowedRegistries:
  - quay.io/myorg
blockMutableTags: false
maxTasks: 50
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            compiler = PipeClearCompiler.from_config(f.name)
        os.unlink(f.name)
        assert compiler.mode == "audit"
        assert compiler.allowed_registries == ["quay.io/myorg"]
        assert compiler.block_mutable_tags is False
        assert compiler.max_tasks == 50

    def test_from_config_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            PipeClearCompiler.from_config("/nonexistent.yaml")

    def test_from_config_overrides(self):
        yaml_content = """
mode: audit
maxTasks: 50
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            compiler = PipeClearCompiler.from_config(f.name, mode="enforce")
        os.unlink(f.name)
        assert compiler.mode == "enforce"
        assert compiler.max_tasks == 50
