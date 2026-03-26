# tests/test_kfp_compiler_plugin.py
import pytest
from unittest.mock import patch, MagicMock
from pipeclear.kfp.compiler import PipeClearCompiler, PipeClearValidationError


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
        with pytest.raises(PipeClearValidationError):
            compiler.compile(pipeline_func=test_pipe, package_path=str(output))


def test_compiler_warns_on_many_tasks():
    """Compiler should block when pipeline has many executors exceeding max_tasks."""
    compiler = PipeClearCompiler(fail_on_critical=False, max_tasks=50)
    # Create spec with 60 executors (exceeds max_tasks=50)
    executors = {f'exec-{i}': {'container': {'image': f'registry.redhat.io/img:{i}'}} for i in range(60)}
    spec = {'deploymentSpec': {'executors': executors}, 'root': {'dag': {'tasks': {}}}}
    result = compiler.validate_pipeline_spec(spec)
    assert len(result['critical']) > 0
    assert any('tasks' in c['message'].lower() for c in result['critical'])


def test_compiler_blocks_excessive_tasks():
    """Compiler should block when pipeline has too many executors."""
    compiler = PipeClearCompiler(fail_on_critical=True)
    executors = {f'exec-{i}': {'container': {'image': f'registry.redhat.io/img:{i}'}} for i in range(110)}
    spec = {'deploymentSpec': {'executors': executors}, 'root': {'dag': {'tasks': {}}}}
    result = compiler.validate_pipeline_spec(spec)
    assert len(result['critical']) > 0
    assert any('tasks' in c['message'].lower() or 'task' in c['message'].lower() for c in result['critical'])


def test_compiler_validates_allowed_registries():
    """Compiler should block images from non-allowed registries."""
    compiler = PipeClearCompiler(
        fail_on_critical=True,
        allowed_registries=['registry.redhat.io', 'quay.io']
    )
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {'image': 'docker.io/library/python:3.11'}},
            },
        },
    }
    result = compiler.validate_pipeline_spec(spec)
    assert len(result['critical']) > 0
    assert any('allowed list' in c['message'].lower() for c in result['critical'])


# ========== Advanced rules tests ==========

def _basic_compiler(**kwargs):
    """Create a compiler with only specified rules enabled (no defaults)."""
    defaults = dict(
        fail_on_critical=False,
        block_mutable_tags=True,
        warn_digest_pinning=False,
        warn_resource_limits=False,
        denied_env_var_patterns=[],
        block_inline_credentials=False,
        warn_duplicate_tasks=False,
        warn_semver_tags=False,
    )
    defaults.update(kwargs)
    return PipeClearCompiler(**defaults)


def test_warn_digest_pinning():
    """Should warn when image lacks @sha256: digest."""
    c = _basic_compiler(warn_digest_pinning=True)
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {'image': 'quay.io/myorg/trainer:v1.2.3'}},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['warnings']) == 1
    assert 'not pinned by digest' in result['warnings'][0]['message']


def test_no_warn_digest_when_pinned():
    """Should not warn when image uses @sha256: digest."""
    c = _basic_compiler(warn_digest_pinning=True)
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {
                    'image': 'quay.io/myorg/trainer@sha256:abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890',
                }},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['warnings']) == 0


def test_warn_missing_resource_limits():
    """Should warn when executor has no resource limits."""
    c = _basic_compiler(warn_resource_limits=True)
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {'image': 'quay.io/myorg/trainer:v1.2.3'}},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['warnings']) == 1
    assert 'no resource limits' in result['warnings'][0]['message']


def test_no_warn_when_resource_limits_set():
    """Should not warn when resource limits are set."""
    c = _basic_compiler(warn_resource_limits=True)
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {
                    'image': 'quay.io/myorg/trainer:v1.2.3',
                    'resources': {
                        'resourceCpuLimit': '2',
                        'resourceMemoryLimit': '4Gi',
                    },
                }},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['warnings']) == 0


def test_deny_suspicious_env_var_name():
    """Should deny env vars matching denied name patterns."""
    from pipeclear.kfp.compiler import DEFAULT_DENIED_ENV_VAR_PATTERNS
    c = _basic_compiler(denied_env_var_patterns=DEFAULT_DENIED_ENV_VAR_PATTERNS)
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {
                    'image': 'quay.io/myorg/trainer:v1.2.3',
                    'env': [{'name': 'DB_PASSWORD', 'value': 'supersecret'}],
                }},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['critical']) == 1
    assert 'DB_PASSWORD' in result['critical'][0]['message']
    assert 'denied pattern' in result['critical'][0]['message']


def test_deny_inline_credential():
    """Should deny env vars with hardcoded credential values."""
    c = _basic_compiler(block_inline_credentials=True)
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {
                    'image': 'quay.io/myorg/trainer:v1.2.3',
                    'env': [{'name': 'MY_TOKEN', 'value': 'ghp_abcdefghijklmnopqrstuvwxyz1234567890'}],
                }},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['critical']) == 1
    assert 'hardcoded credential' in result['critical'][0]['message']


def test_allow_safe_env_vars():
    """Should allow normal env vars without warnings."""
    from pipeclear.kfp.compiler import DEFAULT_DENIED_ENV_VAR_PATTERNS
    c = _basic_compiler(
        denied_env_var_patterns=DEFAULT_DENIED_ENV_VAR_PATTERNS,
        block_inline_credentials=True,
    )
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {
                    'image': 'quay.io/myorg/trainer:v1.2.3',
                    'env': [
                        {'name': 'MODEL_NAME', 'value': 'llama-7b'},
                        {'name': 'BATCH_SIZE', 'value': '32'},
                    ],
                }},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['critical']) == 0


def test_warn_duplicate_tasks():
    """Should warn on identical executor configurations."""
    c = _basic_compiler(warn_duplicate_tasks=True)
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-train-1': {'container': {
                    'image': 'quay.io/myorg/trainer:v1.2.3',
                    'command': ['python'],
                    'args': ['train.py'],
                }},
                'exec-train-2': {'container': {
                    'image': 'quay.io/myorg/trainer:v1.2.3',
                    'command': ['python'],
                    'args': ['train.py'],
                }},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['warnings']) == 1
    assert 'identical configuration' in result['warnings'][0]['message']


def test_no_duplicate_warn_for_different_args():
    """Should not warn when executors have different args."""
    c = _basic_compiler(warn_duplicate_tasks=True)
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-train': {'container': {
                    'image': 'quay.io/myorg/trainer:v1.2.3',
                    'command': ['python'],
                    'args': ['train.py'],
                }},
                'exec-eval': {'container': {
                    'image': 'quay.io/myorg/trainer:v1.2.3',
                    'command': ['python'],
                    'args': ['eval.py'],
                }},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['warnings']) == 0


def test_warn_non_semver_tag():
    """Should warn when image tag is not semver."""
    c = _basic_compiler(warn_semver_tags=True)
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {'image': 'quay.io/myorg/trainer:dev-build-123'}},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['warnings']) == 1
    assert 'non-semver tag' in result['warnings'][0]['message']


def test_no_warn_semver_tag():
    """Should not warn for valid semver tag."""
    c = _basic_compiler(warn_semver_tags=True)
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {'image': 'quay.io/myorg/trainer:v1.2.3'}},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['warnings']) == 0


# ========== Edge case / regression tests ==========

def test_port_in_registry_mutable_tag():
    """Image with port but no tag should be detected as mutable."""
    from pipeclear.kfp.compiler import _extract_tag
    assert _extract_tag('localhost:5000/myimg') == ''
    assert _extract_tag('localhost:5000/myimg:v1.0') == 'v1.0'
    assert _extract_tag('localhost:5000/myimg:latest') == 'latest'
    # Bare host:port with no path — should return '' (port, not tag)
    assert _extract_tag('localhost:5000') == ''
    assert _extract_tag('') == ''


def test_registry_extraction():
    """Registry should be correctly extracted for various image formats."""
    from pipeclear.kfp.compiler import _extract_registry
    assert _extract_registry('quay.io/user/img:v1') == 'quay.io'
    assert _extract_registry('docker.io/library/python:3.11') == 'docker.io'
    assert _extract_registry('python:3.11') == 'docker.io'  # Docker Hub shorthand
    assert _extract_registry('library/python:3.11') == 'docker.io'  # Docker Hub namespace
    assert _extract_registry('localhost:5000/img:v1') == 'localhost:5000'
    assert _extract_registry('registry.redhat.io/ubi9/python:1') == 'registry.redhat.io'


def test_image_with_digest_and_tag():
    """Image with both tag and digest should extract empty tag (digest takes priority)."""
    from pipeclear.kfp.compiler import _extract_tag
    assert _extract_tag('quay.io/img:v1@sha256:abcdef') == ''


def test_importer_executor_skipped():
    """Executors without a container spec should be silently skipped."""
    c = _basic_compiler()
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-importer': {'importer': {'artifactUri': 'gs://bucket/path'}},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['critical']) == 0
    assert len(result['warnings']) == 0


def test_empty_spec():
    """Empty spec should produce no findings."""
    c = _basic_compiler()
    result = c.validate_pipeline_spec({})
    assert len(result['critical']) == 0
    assert len(result['warnings']) == 0


def test_all_rules_disabled():
    """With all rules disabled, no findings should fire."""
    c = PipeClearCompiler(
        fail_on_critical=False,
        block_mutable_tags=False,
        warn_digest_pinning=False,
        warn_resource_limits=False,
        denied_env_var_patterns=[],
        block_inline_credentials=False,
        warn_duplicate_tasks=False,
        warn_semver_tags=False,
        max_tasks=0,  # 0 = disabled
    )
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {'image': 'quay.io/myorg/trainer:v1.2.3'}},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['critical']) == 0
    assert len(result['warnings']) == 0


def test_decorator_does_not_mutate_compiler_state(tmp_path):
    """Decorator config should not permanently modify the compiler."""
    c = PipeClearCompiler(
        fail_on_critical=False,
        allowed_registries=['quay.io'],
        warn_digest_pinning=False,
        warn_resource_limits=False,
    )
    original_registries = list(c.allowed_registries)

    # Mock the internal compiler and create a dummy YAML
    import yaml
    dummy_spec = {'deploymentSpec': {'executors': {
        'exec-1': {'container': {'image': 'quay.io/myorg/trainer:v1.2.3'}}
    }}}
    output = tmp_path / "pipeline.yaml"
    with open(output, 'w') as f:
        yaml.dump(dummy_spec, f)

    def fake_pipeline():
        pass
    fake_pipeline._pipeclear_config = {
        'fail_on_critical': False,
        'allowed_registries': ['docker.io'],
    }

    # Exercise the save/restore path by actually calling compile
    with patch.object(c._compiler, 'compile', return_value=None):
        c.compile(pipeline_func=fake_pipeline, package_path=str(output))

    # After compile, registries should be restored to original
    assert c.allowed_registries == original_registries


def test_multiple_rules_fire_simultaneously():
    """Multiple rules should accumulate findings."""
    from pipeclear.kfp.compiler import DEFAULT_DENIED_ENV_VAR_PATTERNS
    c = PipeClearCompiler(
        fail_on_critical=False,
        allowed_registries=['quay.io'],
        warn_digest_pinning=True,
        warn_resource_limits=True,
        denied_env_var_patterns=DEFAULT_DENIED_ENV_VAR_PATTERNS,
        block_inline_credentials=True,
        warn_duplicate_tasks=False,
        warn_semver_tags=False,
    )
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {
                    'image': 'docker.io/library/python:latest',
                    'env': [{'name': 'DB_PASSWORD', 'value': 'ghp_fake1234567890abcdef'}],
                }},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    # Should have: disallowed registry, env var name, inline credential = 3 critical
    assert len(result['critical']) >= 3
    # Should have: mutable tag, digest pinning, resource limits = 3 warnings
    assert len(result['warnings']) >= 3


# ========== Security tests (Round 2) ==========

def test_whitespace_bypass_credential_detection():
    """Whitespace-padded credential values should still be caught."""
    c = _basic_compiler(block_inline_credentials=True)
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {
                    'image': 'quay.io/myorg/trainer:v1.2.3',
                    'env': [{'name': 'TOKEN', 'value': '  ghp_abcdefghijklmnopqrstuvwxyz123'}],
                }},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['critical']) == 1
    assert 'hardcoded credential' in result['critical'][0]['message']


def test_whitespace_only_image_denied():
    """Whitespace-only image string should be treated as missing."""
    c = _basic_compiler()
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-ws': {'container': {'image': '   '}},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['critical']) == 1
    assert 'no container image' in result['critical'][0]['message']


def test_credential_in_command_args():
    """Credential patterns in command/args should be detected."""
    c = _basic_compiler(block_inline_credentials=True)
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {
                    'image': 'quay.io/myorg/trainer:v1.2.3',
                    'command': ['sh', '-c'],
                    'args': ['curl -H "Authorization: token ghp_secrettoken123" https://api.github.com'],
                }},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['critical']) == 1
    assert 'command/args' in result['critical'][0]['message']


def test_expanded_credential_prefixes():
    """New credential prefixes should be detected."""
    c = _basic_compiler(block_inline_credentials=True)
    prefixes_to_test = [
        ('GITLAB', 'glpat-abcdefghijklmnop'),
        ('GITHUB_PAT', 'github_pat_abcdefghijklmnop'),
        ('AWS_SESSION', 'ASIAabcdefghijklmnop'),
        ('PYPI', 'pypi-abcdefghijklmnop'),
        ('PEM_KEY', '-----BEGIN RSA PRIVATE KEY-----'),
    ]
    for name, value in prefixes_to_test:
        spec = {
            'deploymentSpec': {
                'executors': {
                    'exec-1': {'container': {
                        'image': 'quay.io/myorg/trainer:v1.2.3',
                        'env': [{'name': name, 'value': value}],
                    }},
                },
            },
        }
        result = c.validate_pipeline_spec(spec)
        assert len(result['critical']) == 1, f"Failed to detect credential prefix for {name}={value}"


def test_refined_key_pattern_no_false_positive():
    """CACHE_KEY should not be flagged (refined from broad _KEY to _API_KEY etc)."""
    from pipeclear.kfp.compiler import DEFAULT_DENIED_ENV_VAR_PATTERNS
    c = _basic_compiler(denied_env_var_patterns=DEFAULT_DENIED_ENV_VAR_PATTERNS)
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {
                    'image': 'quay.io/myorg/trainer:v1.2.3',
                    'env': [
                        {'name': 'CACHE_KEY', 'value': 'some_key'},
                        {'name': 'SORT_KEY', 'value': 'some_sort'},
                    ],
                }},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['critical']) == 0, "CACHE_KEY and SORT_KEY should not be flagged"


def test_api_key_pattern_still_caught():
    """Specific key patterns like _API_KEY should still be caught."""
    from pipeclear.kfp.compiler import DEFAULT_DENIED_ENV_VAR_PATTERNS
    c = _basic_compiler(denied_env_var_patterns=DEFAULT_DENIED_ENV_VAR_PATTERNS)
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {
                    'image': 'quay.io/myorg/trainer:v1.2.3',
                    'env': [{'name': 'OPENAI_API_KEY', 'value': 'mykey'}],
                }},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['critical']) == 1
    assert 'OPENAI_API_KEY' in result['critical'][0]['message']


def test_block_mutable_tags_toggle():
    """block_mutable_tags=False should suppress mutable tag warnings."""
    c = _basic_compiler(block_mutable_tags=False)
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {'image': 'quay.io/myorg/trainer:latest'}},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert all('mutable tag' not in w['message'] for w in result['warnings'])


def test_exactly_max_tasks_passes():
    """Pipeline with exactly max_tasks executors should pass."""
    c = _basic_compiler(max_tasks=2)
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {'image': 'quay.io/myorg/trainer:v1.0.0'}},
                'exec-2': {'container': {'image': 'quay.io/myorg/trainer:v2.0.0'}},
            },
        },
        'root': {'dag': {'tasks': {}}},
    }
    result = c.validate_pipeline_spec(spec)
    task_criticals = [c for c in result['critical'] if 'tasks' in c['message'].lower()]
    assert len(task_criticals) == 0, "exactly max_tasks should not be denied"


def test_multiple_denied_env_vars_in_same_executor():
    """Each denied env var should produce its own denial."""
    from pipeclear.kfp.compiler import DEFAULT_DENIED_ENV_VAR_PATTERNS
    c = _basic_compiler(denied_env_var_patterns=DEFAULT_DENIED_ENV_VAR_PATTERNS)
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {
                    'image': 'quay.io/myorg/trainer:v1.2.3',
                    'env': [
                        {'name': 'DB_PASSWORD', 'value': 'pass1'},
                        {'name': 'MY_SECRET', 'value': 'sec1'},
                        {'name': 'AUTH_TOKEN', 'value': 'tok1'},
                    ],
                }},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['critical']) == 3


def test_env_var_empty_name():
    """Empty env var name should not match denied patterns."""
    from pipeclear.kfp.compiler import DEFAULT_DENIED_ENV_VAR_PATTERNS
    c = _basic_compiler(
        denied_env_var_patterns=DEFAULT_DENIED_ENV_VAR_PATTERNS,
        block_inline_credentials=True,
    )
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {
                    'image': 'quay.io/myorg/trainer:v1.2.3',
                    'env': [{'name': '', 'value': 'somevalue'}],
                }},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['critical']) == 0


def test_short_credential_value_no_false_positive():
    """Short values like sk-learn, SG.config should not be flagged as credentials."""
    c = _basic_compiler(block_inline_credentials=True)
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {
                    'image': 'quay.io/myorg/trainer:v1.2.3',
                    'env': [
                        {'name': 'MODEL_TYPE', 'value': 'sk-learn'},
                        {'name': 'ENDPOINT', 'value': 'SG.config'},
                        {'name': 'FRAMEWORK', 'value': 'hf_hub'},
                    ],
                }},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['critical']) == 0, "short values should not be flagged as credentials"


def test_short_credential_in_command_no_false_positive():
    """Short args like --model=sk-learn should not be flagged."""
    c = _basic_compiler(block_inline_credentials=True)
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {
                    'image': 'quay.io/myorg/trainer:v1.2.3',
                    'command': ['python'],
                    'args': ['--model=sk-learn'],
                }},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['critical']) == 0, "short args should not be flagged"


def test_malformed_digest_not_treated_as_pinned():
    """Malformed digest (not 64 hex chars) should not suppress warnings."""
    c = _basic_compiler(block_mutable_tags=True, warn_digest_pinning=True)
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {
                    'image': 'evil.io/malware:latest@sha256:abc',
                    'command': ['python'],
                }},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['warnings']) > 0, "malformed digest should trigger warnings"


def test_inline_credentials_disabled():
    """With block_inline_credentials=False, credential-like values should pass."""
    c = _basic_compiler(block_inline_credentials=False)
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {
                    'image': 'quay.io/myorg/trainer:v1.2.3',
                    'env': [{'name': 'MY_TOKEN', 'value': 'ghp_realtoken1234567890abcdef'}],
                }},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert all('hardcoded credential' not in c['message'] for c in result['critical'])


# ========== Architect review fixes ==========

def test_config_validates_empty_pattern():
    """Empty denied env var patterns should raise ValueError at construction."""
    import pytest
    with pytest.raises(ValueError, match="empty"):
        _basic_compiler(denied_env_var_patterns=["_PASSWORD", ""])


def test_config_validates_invalid_mode():
    """Invalid mode should raise ValueError at construction."""
    import pytest
    with pytest.raises(ValueError, match="invalid mode"):
        _basic_compiler(mode="invalid")


def test_audit_mode_converts_denials_to_warnings():
    """Audit mode should convert denials to warnings with [AUDIT] prefix."""
    from pipeclear.kfp.compiler import ENFORCE_MODE_AUDIT
    c = PipeClearCompiler(
        fail_on_critical=False,
        allowed_registries=['registry.redhat.io'],
        mode=ENFORCE_MODE_AUDIT,
    )
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {
                    'image': 'docker.io/library/python:3.11',
                    'command': ['python'],
                }},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['critical']) == 0, "audit mode should produce no criticals"
    audit_warnings = [w for w in result['warnings'] if '[AUDIT]' in w['message']]
    assert len(audit_warnings) > 0, "audit mode should convert denials to [AUDIT] warnings"


def test_off_mode_skips_validation():
    """Off mode should skip all validation."""
    from pipeclear.kfp.compiler import ENFORCE_MODE_OFF
    c = PipeClearCompiler(
        fail_on_critical=False,
        mode=ENFORCE_MODE_OFF,
    )
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {'image': ''}},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['critical']) == 0, "off mode should skip validation"
    assert len(result['warnings']) == 0, "off mode should skip validation"


def test_file_path_env_var_not_denied():
    """Env vars with file path values should not trigger name-based denial."""
    from pipeclear.kfp.compiler import DEFAULT_DENIED_ENV_VAR_PATTERNS
    c = _basic_compiler(denied_env_var_patterns=DEFAULT_DENIED_ENV_VAR_PATTERNS)
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {
                    'image': 'quay.io/myorg/trainer:v1.2.3',
                    'env': [
                        {'name': 'GOOGLE_APPLICATION_CREDENTIALS', 'value': '/var/secrets/gcp/key.json'},
                        {'name': 'MLFLOW_TRACKING_TOKEN', 'value': '/mnt/secrets/mlflow-token'},
                    ],
                }},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['critical']) == 0, "file path values should not trigger env var name denial"


def test_registry_prefix_match():
    """Registry prefix like 'quay.io/myorg' should match 'quay.io/myorg/trainer'."""
    c = _basic_compiler(allowed_registries=['quay.io/myorg'])
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {
                    'image': 'quay.io/myorg/trainer:v1.2.3',
                    'command': ['python'],
                }},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['critical']) == 0, "prefix match should allow quay.io/myorg/trainer"


def test_registry_prefix_denies_other_org():
    """Registry prefix 'quay.io/myorg' should NOT match 'quay.io/evilorg'."""
    c = _basic_compiler(allowed_registries=['quay.io/myorg'])
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {
                    'image': 'quay.io/evilorg/malware:v1.0.0',
                    'command': ['python'],
                }},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['critical']) == 1, "prefix should not match different org"


def test_registry_error_shows_allowed_list():
    """Registry denial message should include the allowed list."""
    c = _basic_compiler(allowed_registries=['registry.redhat.io', 'quay.io'])
    spec = {
        'deploymentSpec': {
            'executors': {
                'exec-1': {'container': {
                    'image': 'docker.io/library/python:3.11',
                    'command': ['python'],
                }},
            },
        },
    }
    result = c.validate_pipeline_spec(spec)
    assert len(result['critical']) == 1
    msg = result['critical'][0]['message']
    assert 'registry.redhat.io' in msg, "error should show allowed registries"
    assert 'quay.io' in msg, "error should show allowed registries"


def test_default_delete_on_failure_is_false():
    """Default delete_on_failure should be False."""
    c = PipeClearCompiler(fail_on_critical=False)
    assert c.delete_on_failure is False, "delete_on_failure should default to False"


def test_default_digest_and_resource_warnings_off():
    """Default config should have digest pinning and resource limit warnings off."""
    c = PipeClearCompiler(fail_on_critical=False)
    assert c.warn_digest_pinning is False, "warn_digest_pinning should default to False"
    assert c.warn_resource_limits is False, "warn_resource_limits should default to False"
