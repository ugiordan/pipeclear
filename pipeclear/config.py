"""Shared configuration for PipeClear validation rules."""

from dataclasses import dataclass
from typing import Optional
import yaml


_CAMEL_TO_SNAKE = {
    "mode": "mode",
    "allowedRegistries": "allowed_registries",
    "blockMutableTags": "block_mutable_tags",
    "blockInlineCredentials": "block_inline_credentials",
    "maxTasks": "max_tasks",
    "deniedEnvVarPatterns": "denied_env_var_patterns",
    "warnDigestPinning": "warn_digest_pinning",
    "warnSemverTags": "warn_semver_tags",
    "warnResourceLimits": "warn_resource_limits",
    "warnDuplicateTasks": "warn_duplicate_tasks",
}


@dataclass
class PipeClearConfig:
    mode: str = "enforce"
    allowed_registries: Optional[list[str]] = None
    block_mutable_tags: bool = True
    block_inline_credentials: bool = True
    max_tasks: int = 100
    denied_env_var_patterns: Optional[list[str]] = None
    warn_digest_pinning: bool = False
    warn_semver_tags: bool = False
    warn_resource_limits: bool = False
    warn_duplicate_tasks: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> "PipeClearConfig":
        kwargs = {}
        for camel_key, snake_key in _CAMEL_TO_SNAKE.items():
            if camel_key in data:
                kwargs[snake_key] = data[camel_key]
        return cls(**kwargs)

    @classmethod
    def from_yaml(cls, path: str) -> "PipeClearConfig":
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return cls.from_dict(data)

    def to_compiler_kwargs(self) -> dict:
        return {
            "mode": self.mode,
            "allowed_registries": self.allowed_registries,
            "block_mutable_tags": self.block_mutable_tags,
            "block_inline_credentials": self.block_inline_credentials,
            "max_tasks": self.max_tasks,
            "denied_env_var_patterns": self.denied_env_var_patterns,
            "warn_digest_pinning": self.warn_digest_pinning,
            "warn_semver_tags": self.warn_semver_tags,
            "warn_resource_limits": self.warn_resource_limits,
            "warn_duplicate_tasks": self.warn_duplicate_tasks,
        }
