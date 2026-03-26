# PipeClear RHOAI Integration Design (Revised)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Date:** 2026-03-19
**Status:** Approved
**Approach:** Layered — Phase 1: KFP Compiler Plugin (Python) + Phase 2: Go Webhook in ODH Operator

## Why the Original Approach Was Rejected

Three independent architect reviews identified blocking issues with the original "DSP sub-feature + Python webhook" plan:

1. **Python webhook in Go operator is architecturally incoherent** — The ODH operator is a single Go binary with `-tags strictfipsruntime`. All 10+ existing webhooks run in-process. No CNCF project uses Python for admission webhooks. FIPS compliance for Python crypto is unproven.
2. **DSP sub-feature is the wrong abstraction** — ArgoWorkflowsControllers is a kustomize parameter toggle, not a runtime service. PipeClear may need to validate beyond pipelines (notebooks, models).
3. **failurePolicy: Fail on an unproven feature risks cluster-wide blockage** — Reddit Pi-Day outage (5+ hours) was caused by an OPA webhook failure.

## Revised Architecture: Two Phases

```
Phase 1: KFP Compiler Plugin (Python, no cluster changes)
  kfp.compiler.Compiler().compile() → PipeClear validation → allow/block compilation

Phase 2: Go Validating Webhook in ODH Operator (follows Kueue pattern)
  PipelineVersion CR creation → K8s API → PipeClear webhook (in-process Go) → allow/deny
```

Both layers are complementary:
- Phase 1 catches the most common path (SDK users) with best UX
- Phase 2 enforces policy at the cluster level regardless of submission method

---

## Phase 1: KFP Compiler Plugin

**Goal:** Validate notebooks/pipelines at compile time, before anything reaches the cluster.

**Architecture:** A Python package (`pipeclear-kfp`) that hooks into the KFP SDK compilation step. When a user compiles a pipeline, PipeClear runs pre-flight checks and blocks compilation if critical issues are found.

**Usage:**
```python
# Option A: Decorator
from pipeclear.kfp import validate

@validate(fail_on_critical=True)
@dsl.pipeline(name="my-pipeline")
def my_pipeline():
    ...

# Option B: Compiler wrapper
from pipeclear.kfp import PipeClearCompiler

PipeClearCompiler().compile(
    pipeline_func=my_pipeline,
    package_path='pipeline.yaml'
)

# Option C: Standalone pre-check
from pipeclear import analyze
report = analyze("notebook.ipynb")
if report['summary']['critical'] > 0:
    raise SystemExit("Pre-flight check failed")
```

**What it validates (notebook-level):**
- Hardcoded secrets/credentials
- Missing or unavailable dependencies
- Resource requirements (GPU/VRAM estimation)
- Base image accessibility
- Pipeline name validity

**Files (in pipeclear repo):**
- `pipeclear/kfp/compiler.py` — PipeClearCompiler wrapper
- `pipeclear/kfp/decorator.py` — @validate decorator
- `tests/test_kfp_compiler.py` — Tests
- Update `pipeclear/kfp/__init__.py` — Export new APIs

**Repo:** `ugiordan/pipeclear`
**Effort:** 2-4 days
**Dependencies:** None (pure Python, pip installable)

---

## Phase 2: Go Validating Webhook in ODH Operator

**Goal:** Enforce pipeline validation policy at the cluster level, catching all submission paths.

**Architecture:** A Go validating webhook registered in the ODH operator's existing webhook infrastructure, following the Kueue webhook pattern (`internal/webhook/kueue/validating.go`). Runs in-process with the operator — no separate deployment, no Python.

**Integration model:** Register as a **Service** (via `internal/controller/services/`), not a DSP sub-feature. This allows future expansion to validate notebooks or model deployments.

**What it validates (IR-level):**
- Container image provenance (registry allowlist, no mutable tags)
- Resource request/limit policy (max memory, CPU, GPU quotas)
- Security context (no privileged containers, no host mounts)
- Pipeline structure (max parallelism, max tasks)

**Key design decisions:**
- **Language:** Go (matches operator ecosystem, FIPS-compliant, in-process)
- **Failure policy:** `Ignore` initially, with a controller that sets `status.validated` condition on PipelineVersion CRs. Graduate to `Fail` once proven stable.
- **Policy storage:** ConfigMap-based validation rules (not compiled into binary). Allows rule updates without operator rebuild.
- **Scope:** Namespace-scoped via label selector (exclude system namespaces)

**DSC configuration:**
```yaml
apiVersion: datasciencecluster.opendatahub.io/v2
kind: DataScienceCluster
spec:
  components:
    datasciencepipelines:
      managementState: Managed
  services:
    pipeclear:
      managementState: Managed
      validationPolicy: default  # references ConfigMap
```

**Files (in opendatahub-operator fork):**

New:
- `internal/webhook/pipeclear/validating.go` — Webhook handler (follows Kueue pattern)
- `internal/webhook/pipeclear/validating_test.go` — Tests
- `internal/controller/services/pipeclear/pipeclear.go` — Service handler
- `config/pipeclear/validation-policy-default.yaml` — Default validation rules ConfigMap

Modified:
- `internal/webhook/webhook.go` — Register PipeClear webhook entry
- `cmd/main.go` — Register PipeClear service handler

**Repo:** `ugiordan/opendatahub-operator` (fork)
**Effort:** 1-2 weeks
**Dependencies:** Phase 1 complete (validates the rule set)

---

## Repositories

| Repo | Phase | Purpose |
|------|-------|---------|
| `ugiordan/pipeclear` | Phase 1 | Python CLI/SDK + KFP compiler plugin |
| `ugiordan/opendatahub-operator` | Phase 2 | Go webhook + service registration |

## Testing Strategy

### Phase 1
1. Unit tests: mock KFP compiler, verify PipeClear blocks on critical issues
2. Integration tests: compile real notebooks, verify validation runs
3. Test against 7 real RHOAI notebooks already in `examples/rhoai_real_notebooks/`

### Phase 2
1. Unit tests: mock AdmissionReview payloads, verify allow/deny decisions
2. Integration tests: kind cluster with KFP CRDs installed
3. E2E: deploy on real RHOAI cluster, submit pipeline with known issues, verify denial

## Architecture Decision Records

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Webhook language | Go | FIPS compliance, in-process with operator, all existing webhooks are Go |
| Integration model | Service (not DSP sub-feature) | Cross-component extensibility, independent lifecycle |
| Failure policy | Ignore (initially) | Avoid cluster-wide blockage for unproven feature |
| Policy storage | ConfigMap | Decouple rules from binary, safe upgrades/rollbacks |
| Phase 1 approach | KFP compiler plugin | Best UX, highest-value path, zero infrastructure |
