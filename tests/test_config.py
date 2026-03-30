import os
import tempfile
import pytest
from pipeclear.config import PipeClearConfig


class TestPipeClearConfig:
    def test_from_dict_defaults(self):
        config = PipeClearConfig.from_dict({})
        assert config.mode == "enforce"
        assert config.allowed_registries is None
        assert config.block_mutable_tags is True
        assert config.block_inline_credentials is True
        assert config.max_tasks == 100
        assert config.warn_digest_pinning is False
        assert config.warn_resource_limits is False
        assert config.warn_semver_tags is False
        assert config.warn_duplicate_tasks is True

    def test_from_dict_custom(self):
        config = PipeClearConfig.from_dict({
            "mode": "audit",
            "allowedRegistries": ["quay.io/myorg"],
            "blockMutableTags": False,
            "maxTasks": 50,
        })
        assert config.mode == "audit"
        assert config.allowed_registries == ["quay.io/myorg"]
        assert config.block_mutable_tags is False
        assert config.max_tasks == 50

    def test_from_yaml_file(self):
        yaml_content = """
mode: audit
allowedRegistries:
  - registry.redhat.io
  - quay.io/myorg
blockMutableTags: true
maxTasks: 200
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()
            config = PipeClearConfig.from_yaml(f.name)
        os.unlink(f.name)
        assert config.mode == "audit"
        assert config.allowed_registries == ["registry.redhat.io", "quay.io/myorg"]
        assert config.max_tasks == 200

    def test_from_yaml_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            PipeClearConfig.from_yaml("/nonexistent/path.yaml")

    def test_to_compiler_kwargs(self):
        config = PipeClearConfig.from_dict({
            "mode": "audit",
            "allowedRegistries": ["quay.io"],
            "blockMutableTags": False,
        })
        kwargs = config.to_compiler_kwargs()
        assert kwargs["mode"] == "audit"
        assert kwargs["allowed_registries"] == ["quay.io"]
        assert kwargs["block_mutable_tags"] is False

    def test_camel_to_snake_mapping(self):
        config = PipeClearConfig.from_dict({
            "deniedEnvVarPatterns": ["_TOKEN", "_SECRET"],
            "warnDigestPinning": True,
            "warnResourceLimits": True,
        })
        assert config.denied_env_var_patterns == ["_TOKEN", "_SECRET"]
        assert config.warn_digest_pinning is True
        assert config.warn_resource_limits is True
