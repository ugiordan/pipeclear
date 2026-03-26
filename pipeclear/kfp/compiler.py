"""PipeClear-enhanced KFP compiler with pre-flight validation."""
import os
import re
import sys
import warnings as _warnings
import yaml
from kfp import compiler


# Patterns for env var names that likely contain secrets
DEFAULT_DENIED_ENV_VAR_PATTERNS = [
    "_PASSWORD", "_SECRET", "_TOKEN", "_CREDENTIAL",
    "_API_KEY", "_APIKEY", "_SECRET_KEY", "_ACCESS_KEY", "_PRIVATE_KEY",
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
]

# Prefixes that indicate hardcoded credential values
INLINE_CREDENTIAL_PREFIXES = [
    "ghp_",          # GitHub personal access token
    "gho_",          # GitHub OAuth token
    "ghu_",          # GitHub user-to-server token
    "ghs_",          # GitHub server-to-server token
    "github_pat_",   # GitHub fine-grained PAT
    "glpat-",        # GitLab personal access token
    "sk-",           # OpenAI API key
    "AKIA",          # AWS access key
    "ASIA",          # AWS temporary session credentials
    "hf_",           # HuggingFace token
    "xoxb-",         # Slack bot token
    "xoxp-",         # Slack user token
    "pypi-",         # PyPI API token
    "npm_",          # npm auth token
    "dop_v1_",       # DigitalOcean PAT
    "SG.",           # SendGrid API key
    "-----BEGIN",    # PEM private keys
]

# Semantic versioning regex
SEMVER_RE = re.compile(
    r'^v?[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?(\+[a-zA-Z0-9.]+)?$'
)

# SHA256 digest format validation
SHA256_DIGEST_RE = re.compile(r'@sha256:[a-fA-F0-9]{64}$')

# Minimum value length for inline credential detection.
# Real API keys/tokens are typically 20+ characters; this avoids false positives
# on short values like "sk-learn", "SG.config", or args like "--model=sk-learn".
MIN_CREDENTIAL_LENGTH = 20

# Enforce modes
ENFORCE_MODE_ENFORCE = "enforce"
ENFORCE_MODE_AUDIT = "audit"
ENFORCE_MODE_OFF = "off"


class PipeClearValidationError(Exception):
    """Raised when PipeClear validation finds critical issues."""

    def __init__(self, issues):
        self.issues = issues
        messages = [f"  {i+1}. {iss['message']}" for i, iss in enumerate(issues)]
        super().__init__(
            f"PipeClear validation failed with {len(issues)} critical issue(s):\n"
            + "\n".join(messages)
        )


class PipeClearWarning(UserWarning):
    """Warning issued by PipeClear for non-critical findings."""
    pass


def _extract_tag(image: str) -> str:
    """Extract the tag from an image reference.

    Returns '' if no tag is present or the image uses a digest.
    Correctly handles port-in-registry (e.g., localhost:5000/img).
    """
    # If image uses digest, tag is irrelevant (digest takes priority)
    if '@sha256:' in image:
        return ''
    # Get the last path segment (after the last /)
    name_part = image.rsplit('/', 1)[-1]
    if ':' in name_part:
        candidate = name_part.rsplit(':', 1)[-1]
        # If image has no slash and candidate looks like a port number, it's not a tag
        if '/' not in image and candidate.isdigit() and len(candidate) <= 5:
            return ''
        return candidate
    return ''


def _extract_registry(image: str) -> str:
    """Extract the registry from an image reference.

    Handles Docker Hub shorthand (no dot/colon in first segment = Docker Hub).
    """
    # Strip digest
    if '@' in image:
        image = image[:image.index('@')]
    if '/' not in image:
        return 'docker.io'
    first_segment = image.split('/')[0]
    # A registry contains a dot or colon (port), or is "localhost"
    if '.' in first_segment or ':' in first_segment or first_segment == 'localhost':
        return first_segment
    return 'docker.io'


def _looks_like_file_path(value: str) -> bool:
    """Return True if value appears to be a file path, not a credential."""
    trimmed = value.strip()
    return trimmed.startswith('/') or trimmed.startswith('./') or trimmed.startswith('../')


def _is_registry_allowed(image: str, allowed_registries: list) -> bool:
    """Check if an image's registry matches the allowed list.

    Supports exact hostname match ("quay.io") and prefix match ("quay.io/myorg").
    """
    registry = _extract_registry(image)
    # Strip tag/digest for prefix matching
    image_base = image
    if '@' in image_base:
        image_base = image_base[:image_base.index('@')]
    # Strip tag from the name part only
    last_slash = image_base.rfind('/')
    last_colon = image_base.rfind(':')
    if last_colon > last_slash:
        image_base = image_base[:last_colon]

    for r in allowed_registries:
        if '/' in r:
            # Prefix match: "quay.io/myorg" matches "quay.io/myorg/trainer"
            if image_base.startswith(r + '/') or image_base == r:
                return True
        else:
            # Exact hostname match
            if registry == r:
                return True
    return False


def _validate_config(denied_env_var_patterns, mode):
    """Validate configuration to catch misconfigurations early."""
    if denied_env_var_patterns:
        for i, p in enumerate(denied_env_var_patterns):
            if not p or not p.strip():
                raise ValueError(
                    f"denied_env_var_patterns[{i}] is empty - this would match all env vars"
                )
    valid_modes = (ENFORCE_MODE_ENFORCE, ENFORCE_MODE_AUDIT, ENFORCE_MODE_OFF)
    if mode not in valid_modes:
        raise ValueError(
            f"invalid mode {mode!r} - must be \"enforce\", \"audit\", or \"off\""
        )


class PipeClearCompiler:
    """Wraps kfp.compiler.Compiler with PipeClear validation."""

    def __init__(
        self,
        fail_on_critical=True,
        allowed_registries=None,
        max_tasks=100,
        delete_on_failure=False,
        block_mutable_tags=True,
        # Advanced rules (digest pinning and resource limits off by default to reduce dev noise)
        warn_digest_pinning=False,
        warn_resource_limits=False,
        denied_env_var_patterns=None,
        block_inline_credentials=True,
        warn_duplicate_tasks=True,
        warn_semver_tags=False,
        # Operational
        mode=ENFORCE_MODE_ENFORCE,
    ):
        self._compiler = compiler.Compiler()
        self.fail_on_critical = fail_on_critical
        self.allowed_registries = allowed_registries
        self.max_tasks = max_tasks
        self.delete_on_failure = delete_on_failure
        self.block_mutable_tags = block_mutable_tags
        self.warn_digest_pinning = warn_digest_pinning
        self.warn_resource_limits = warn_resource_limits
        self.denied_env_var_patterns = list(
            denied_env_var_patterns if denied_env_var_patterns is not None
            else DEFAULT_DENIED_ENV_VAR_PATTERNS
        )
        self.block_inline_credentials = block_inline_credentials
        self.warn_duplicate_tasks = warn_duplicate_tasks
        self.warn_semver_tags = warn_semver_tags
        self.mode = mode

        # Validate config at construction time
        _validate_config(self.denied_env_var_patterns, self.mode)

    def validate_pipeline_spec(self, spec: dict, allowed_registries_override=None) -> dict:
        """Validate a compiled pipeline IR spec."""
        # If validation is disabled, return empty result
        if self.mode == ENFORCE_MODE_OFF:
            return {'critical': [], 'warnings': []}

        # Use override if provided (from decorator config), otherwise use instance default
        allowed_registries = (
            allowed_registries_override
            if allowed_registries_override is not None
            else self.allowed_registries
        )

        critical = []
        warnings = []

        deployment_spec = spec.get('deploymentSpec', {})
        executors = deployment_spec.get('executors', {})

        # Pre-compute upper-cased denied patterns
        upper_patterns = [(p, p.upper()) for p in self.denied_env_var_patterns] if self.denied_env_var_patterns else []

        # Track fingerprints for duplicate detection
        fingerprints = {}  # fingerprint -> first executor name

        # Sort executor names for deterministic output
        for executor_name in sorted(executors.keys()):
            executor = executors[executor_name]
            container = executor.get('container', {})
            if not container:
                continue

            image = container.get('image', '').strip()

            if not image:
                critical.append({
                    'message': f'executor "{executor_name}" has no container image specified',
                    'severity': 'critical',
                })
                continue

            tag = _extract_tag(image)

            is_digest_pinned = bool(SHA256_DIGEST_RE.search(image))

            # Check mutable tags (handles port-in-registry correctly)
            # Skip mutable tag check for digest-pinned images
            if self.block_mutable_tags and not is_digest_pinned and (tag == '' or tag == 'latest'):
                warnings.append({
                    'message': f'image "{image}" uses mutable tag - consider using a specific version',
                    'severity': 'warning',
                })

            # Check allowed registries (supports prefix matching for org-level control)
            if allowed_registries:
                if not _is_registry_allowed(image, allowed_registries):
                    critical.append({
                        'message': f'image "{image}" uses registry not in allowed list {allowed_registries}',
                        'severity': 'critical',
                    })

            # Check digest pinning
            if self.warn_digest_pinning:
                if not is_digest_pinned:
                    warnings.append({
                        'message': f'image "{image}" is not pinned by digest - consider using @sha256: for reproducibility',
                        'severity': 'warning',
                    })

            # Check semver tags
            if self.warn_semver_tags:
                if tag and not SEMVER_RE.match(tag):
                    warnings.append({
                        'message': f'image "{image}" has non-semver tag "{tag}"',
                        'severity': 'warning',
                    })

            # Check resource limits
            if self.warn_resource_limits:
                resources = container.get('resources', {})
                if not resources or (
                    not resources.get('resourceCpuLimit')
                    and not resources.get('resourceMemoryLimit')
                ):
                    warnings.append({
                        'message': f'executor "{executor_name}" has no resource limits specified - consider setting CPU/memory limits',
                        'severity': 'warning',
                    })

            # Check env var restrictions
            for env_var in container.get('env', []):
                env_name = env_var.get('name', '')
                env_value = env_var.get('value', '')

                # Check denied env var name patterns
                # Skip if value looks like a file path (e.g., GOOGLE_APPLICATION_CREDENTIALS=/var/secrets/key.json)
                if upper_patterns and not _looks_like_file_path(env_value):
                    upper_name = env_name.upper()
                    for pattern, upper_pattern in upper_patterns:
                        if upper_name.endswith(upper_pattern):
                            critical.append({
                                'message': (
                                    f'executor "{executor_name}" has suspicious env var '
                                    f'"{env_name}" matching denied pattern "{pattern}" '
                                    f'- use Kubernetes Secrets instead'
                                ),
                                'severity': 'critical',
                            })
                            break

                # Check inline credential values (trim whitespace to prevent bypass)
                # Require minimum length to avoid false positives on short values like "sk-learn"
                if self.block_inline_credentials and env_value:
                    trimmed_value = env_value.strip()
                    if len(trimmed_value) >= MIN_CREDENTIAL_LENGTH:
                        for prefix in INLINE_CREDENTIAL_PREFIXES:
                            if trimmed_value.startswith(prefix):
                                critical.append({
                                    'message': (
                                        f'executor "{executor_name}" env var "{env_name}" '
                                        f'contains what appears to be a hardcoded credential '
                                        f'- use Kubernetes Secrets instead'
                                    ),
                                    'severity': 'critical',
                                })
                                break

            # Scan command/args for credential patterns
            # Require minimum string length to avoid false positives on short args
            if self.block_inline_credentials:
                all_strings = container.get('command', []) + container.get('args', [])
                for s in all_strings:
                    trimmed_s = s.strip()
                    if len(trimmed_s) < MIN_CREDENTIAL_LENGTH:
                        continue
                    for prefix in INLINE_CREDENTIAL_PREFIXES:
                        if prefix in trimmed_s:
                            critical.append({
                                'message': (
                                    f'executor "{executor_name}" command/args contain '
                                    f'what appears to be a hardcoded credential '
                                    f'- use Kubernetes Secrets instead'
                                ),
                                'severity': 'critical',
                            })
                            break
                    else:
                        continue
                    break

            # Track fingerprint for duplicate detection (use null separator to avoid ambiguity)
            if self.warn_duplicate_tasks:
                fp = (
                    image,
                    '\x00'.join(container.get('command', [])),
                    '\x00'.join(container.get('args', [])),
                )
                if fp in fingerprints:
                    warnings.append({
                        'message': (
                            f'executor "{executor_name}" has identical configuration to '
                            f'"{fingerprints[fp]}" - possible unintentional duplicate'
                        ),
                        'severity': 'warning',
                    })
                else:
                    fingerprints[fp] = executor_name

        # Task count validation (max_tasks=0 disables the check)
        executor_count = len(executors)
        if self.max_tasks > 0 and executor_count > self.max_tasks:
            critical.append({
                'message': f'pipeline has {executor_count} tasks, exceeding maximum of {self.max_tasks}',
                'severity': 'critical',
            })

        # In audit mode, convert all denials to warnings
        if self.mode == ENFORCE_MODE_AUDIT:
            for c in critical:
                warnings.append({
                    'message': '[AUDIT] ' + c['message'],
                    'severity': 'warning',
                })
            critical = []

        return {'critical': critical, 'warnings': warnings}

    def compile(self, pipeline_func, package_path, **kwargs):
        """Compile pipeline with PipeClear pre-flight validation."""
        # Read decorator config as local overrides (no mutation of self)
        fail_on_critical = self.fail_on_critical
        allowed_registries = self.allowed_registries

        if hasattr(pipeline_func, '_pipeclear_config'):
            config = pipeline_func._pipeclear_config
            if config.get('fail_on_critical') is not None:
                fail_on_critical = config['fail_on_critical']
            if config.get('allowed_registries') is not None:
                allowed_registries = config['allowed_registries']

        self._compiler.compile(
            pipeline_func=pipeline_func,
            package_path=package_path,
            **kwargs,
        )

        with open(package_path, 'r') as f:
            spec = yaml.safe_load(f)

        result = self.validate_pipeline_spec(spec, allowed_registries_override=allowed_registries)

        for w in result['warnings']:
            _warnings.warn(w['message'], PipeClearWarning, stacklevel=2)

        if fail_on_critical and result['critical']:
            for c in result['critical']:
                print(f"PipeClear CRITICAL: {c['message']}", file=sys.stderr)
            if self.delete_on_failure:
                try:
                    os.remove(package_path)
                except OSError:
                    pass
            raise PipeClearValidationError(result['critical'])

        return result
