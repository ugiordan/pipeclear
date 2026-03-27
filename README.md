# PipeClear

**Pipeline pre-flight validation for [Kubeflow Pipelines](https://www.kubeflow.org/docs/components/pipelines/).**

Works with upstream KFP, [OpenDataHub](https://opendatahub.io/), and [Red Hat OpenShift AI](https://www.redhat.com/en/technologies/cloud-computing/openshift/openshift-ai).

PipeClear catches pipeline issues (unauthorized registries, mutable tags, hardcoded credentials, policy violations) **before** they run. Two layers of defense: compile-time in the notebook, and admission-time on the cluster.

## Why

Data scientists build ML pipelines using the [KFP SDK](https://www.kubeflow.org/docs/components/pipelines/), compile them to YAML (the KFP Intermediate Representation), and submit them to the KFP API Server for execution.

When something goes wrong (a `:latest` tag, a leaked API key, an unauthorized registry) the failure happens **after** the pipeline is already running. Each failure wastes 10-30 minutes in submit-wait-fail cycles.

PipeClear shifts validation left:

```mermaid
flowchart LR
    A[KFP Pipeline\nDefinition] --> B[PipeClearCompiler\npip install pipeclear]
    B -->|pipeline.yaml| C[KFP API Server\nValidatePipelineSpec]
    C -->|Approved| D[Pipeline Runs]

    B -.->|Denied| E[BLOCKED\nat compile time]
    C -.->|Denied| F[BLOCKED\nat submission time]

    style A fill:#1565C0,stroke:#0D47A1,color:#fff
    style B fill:#FF6D00,stroke:#E65100,color:#fff
    style C fill:#CC0000,stroke:#990000,color:#fff
    style D fill:#2E7D32,stroke:#1B5E20,color:#fff
    style E fill:#D32F2F,stroke:#B71C1C,color:#fff
    style F fill:#D32F2F,stroke:#B71C1C,color:#fff
```

## Two-Layer Architecture

### Layer 1: Python SDK (`pip install pipeclear`)

Wraps the KFP compiler with pre-flight validation. Catches issues at compile time in the notebook, before pipeline YAML is created.

```python
from pipeclear.kfp import PipeClearCompiler

compiler = PipeClearCompiler(
    allowed_registries=["registry.redhat.io", "quay.io/myorg"],
    block_mutable_tags=True,
    block_inline_credentials=True,
)
compiler.compile(my_pipeline, "pipeline.yaml")
# Validates images, tags, registries, credentials at compile time
```

### Layer 2: Server-Side Validation (`ValidatePipelineSpec`)

Runs inside the existing KFP API Server binary, same process, same lifecycle, zero new infrastructure. Type-safe protobuf access with panic recovery.

```go
result, err := webhook.SafeValidatePipelineSpec(tmpl, config)
if len(result.Denials) > 0 {
    // Pipeline blocked at submission time
}
```

## Validation Rules

```mermaid
flowchart LR
    START[Pipeline\nSubmitted] --> MODE{Enforce\nMode?}

    MODE -->|off| SKIP[Skip] --> APPROVE
    MODE -->|enforce / audit| RULES

    subgraph RULES [Validation Rules Engine]
        direction TB
        R1[Mutable Tags]
        R2[Registry Allowlist]
        R3[Credential Detection]
        R4[Pipeline Hygiene]
    end

    RULES --> RESULT{Denials?}

    RESULT -->|No| APPROVE[APPROVED]
    RESULT -->|Yes + enforce| DENY[DENIED]
    RESULT -->|Yes + audit| AUDIT[APPROVED\nwith warnings]

    style START fill:#1565C0,stroke:#0D47A1,color:#fff
    style MODE fill:#FF6D00,stroke:#E65100,color:#fff
    style RESULT fill:#FF6D00,stroke:#E65100,color:#fff
    style SKIP fill:#757575,stroke:#424242,color:#fff
    style R1 fill:#1565C0,stroke:#0D47A1,color:#fff
    style R2 fill:#1565C0,stroke:#0D47A1,color:#fff
    style R3 fill:#CC0000,stroke:#990000,color:#fff
    style R4 fill:#1565C0,stroke:#0D47A1,color:#fff
    style APPROVE fill:#2E7D32,stroke:#1B5E20,color:#fff
    style DENY fill:#D32F2F,stroke:#B71C1C,color:#fff
    style AUDIT fill:#FF6D00,stroke:#E65100,color:#fff
```

| Rule | What it catches | Severity |
|------|----------------|----------|
| **Mutable Tags** | `:latest` or missing tags on container images | Warning |
| **Registry Allowlist** | Images from unauthorized registries | Denial |
| **Credential Detection** | Hardcoded API keys, tokens, PEM keys in env vars or args | Denial |
| **Denied Env Vars** | Env var names matching secret patterns (`_PASSWORD`, `_TOKEN`, etc.) | Denial |
| **Max Tasks** | Pipelines exceeding task count limit (default: 100) | Denial |
| **Digest Pinning** | Images not pinned by `@sha256:` digest | Warning |
| **Semver Tags** | Non-semver image tags | Warning |
| **Resource Limits** | Missing CPU/memory limits on executors | Warning |
| **Duplicate Tasks** | Identical executor configurations | Warning |

## Enforce Modes

Three operational modes for gradual rollout:

| Mode | Behavior | Use case |
|------|----------|----------|
| **enforce** (default) | Denials block pipeline submission | Production: policy compliance is mandatory |
| **audit** | Denials converted to `[AUDIT]` warnings, pipeline proceeds | Rollout: tune policies before enforcing |
| **off** | All validation skipped | Development or emergency bypass |

## Configuration

All rules are configurable via `PipeClearConfig`:

```python
compiler = PipeClearCompiler(
    block_mutable_tags=True,           # Warn on :latest / no tag
    allowed_registries=["quay.io"],    # Registry allowlist (None = all allowed)
    max_tasks=100,                     # Max tasks per pipeline (0 = unlimited)
    block_inline_credentials=True,     # Detect hardcoded credentials
    denied_env_var_patterns=[          # Env var name patterns to deny
        "_PASSWORD", "_SECRET", "_TOKEN", "_API_KEY",
    ],
    warn_digest_pinning=False,         # Opt-in: warn on missing @sha256:
    warn_resource_limits=False,        # Opt-in: warn on missing CPU/mem limits
    warn_semver_tags=False,            # Opt-in: warn on non-semver tags
    warn_duplicate_tasks=True,         # Warn on duplicate executor configs
    mode="enforce",                    # enforce | audit | off
)
```

## Quick Start

```bash
pip install -e ".[dev]"
```

### KFP Compiler Plugin

```python
from kfp import dsl
from pipeclear.kfp import PipeClearCompiler

@dsl.pipeline(name="training-pipeline")
def my_pipeline():
    train = dsl.ContainerOp(
        name="train",
        image="quay.io/myorg/trainer:v1.2.3",
    )

compiler = PipeClearCompiler()
compiler.compile(my_pipeline, "pipeline.yaml")
```

### CLI

```bash
pipeclear analyze notebook.ipynb
pipeclear analyze notebook.ipynb --format json
pipeclear analyze notebook.ipynb --base-image registry.redhat.io/ubi9/python-311:latest
```

## Deployment Model

```mermaid
flowchart TB
    subgraph OP [Operator / Admin]
        CR[ConfigMap or CR\nPipeClearConfig]
    end

    subgraph KFP [KFP API Server Pod]
        API[API Server]
        WH[ValidatePipelineSpec\nPipeClear webhook]
    end

    subgraph NB [Jupyter Notebook]
        SDK[PipeClearCompiler\npip install pipeclear]
    end

    CR -->|configures| WH
    SDK -->|compile-time\nvalidation| API
    API -->|admission-time\nvalidation| WH

    style CR fill:#FF6D00,stroke:#E65100,color:#fff
    style API fill:#CC0000,stroke:#990000,color:#fff
    style WH fill:#CC0000,stroke:#990000,color:#fff
    style SDK fill:#1565C0,stroke:#0D47A1,color:#fff
```

Zero new pods. Reuses the existing operator-managed API server binary and certificates. Configuration flows through:
- **Upstream KFP:** ConfigMap in the KFP namespace
- **OpenDataHub / RHOAI:** `DataSciencePipelinesApplication` (DSPA) CR via the DSPO operator, giving platform admins per-namespace control

## Server-Side Integration

The server-side validation is implemented in a [fork of data-science-pipelines](https://github.com/ugiordan/data-science-pipelines/tree/feat/pipeclear-validation) (`feat/pipeclear-validation` branch), adding two files to the existing webhook package:

```
backend/src/apiserver/webhook/
├── pipelineversion_webhook.go      # Existing: validates PipelineVersion CRs
├── pipelineversion_webhook_test.go  # Existing
├── pipeclear.go                     # NEW: validation rules engine
└── pipeclear_test.go                # NEW: 31 test functions
```

**How it works:**

1. The KFP API Server already runs a `ValidatingWebhookConfiguration` for `PipelineVersion` custom resources. PipeClear hooks into this existing path
2. When a pipeline is submitted, the webhook deserializes the KFP IR (protobuf), extracts the `DeploymentSpec`, and iterates over each executor's container spec
3. `SafeValidatePipelineSpec` wraps validation with panic recovery so a bug in validation never crashes the API server
4. Configuration flows from a ConfigMap (upstream) or DSPA CR (OpenDataHub/RHOAI), giving platform admins per-namespace control

No new Deployments, Services, or TLS certificates. The validation runs in-process with sub-millisecond overhead.

**KEP:** [kubeflow/pipelines#13151](https://github.com/kubeflow/pipelines/issues/13151) | **PR:** [kubeflow/pipelines#13152](https://github.com/kubeflow/pipelines/pull/13152)

## Test Coverage

- **Server-Side Validation (Go):** 31 test functions, all passing
- **Python SDK:** 48 test functions, all passing
- **4 independent architecture reviews** confirmed stability

## Development

```bash
pytest tests/ -v
pytest --cov=pipeclear tests/
```

## License

Apache License 2.0. See [LICENSE](LICENSE).

---

Built with the assistance of [Claude](https://claude.ai) (Anthropic).
