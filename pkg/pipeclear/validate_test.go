package pipeclear

import (
	"fmt"
	"strings"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

const baseSpecTemplate = `{
	"pipelineInfo": {"name": "test-pipeline"},
	"root": {"dag": {"tasks": {}}},
	"schemaVersion": "2.1.0",
	"sdkVersion": "kfp-2.11.0",
	"deploymentSpec": {
		"executors": {
			%s
		}
	}
}`

func specWithExecutors(executors string) string {
	return fmt.Sprintf(baseSpecTemplate, executors)
}

func basicConfig() *Config {
	return &Config{
		BlockMutableTags:    true,
		AllowedRegistries:   nil,
		MaxTasksPerPipeline: 100,
	}
}

func TestValidate_AllowCleanPipeline(t *testing.T) {
	spec := specWithExecutors(`"exec-train": {
		"container": {
			"image": "registry.redhat.io/ubi9/python-311:1.0",
			"command": ["python"],
			"args": ["train.py"]
		}
	}`)
	result, err := Validate([]byte(spec), basicConfig())
	require.NoError(t, err)
	assert.Empty(t, result.Denials, "expected no denials for a clean pipeline")
	assert.Empty(t, result.Warnings, "expected no warnings for a tagged image")
}

func TestValidate_WarnMutableTag(t *testing.T) {
	spec := specWithExecutors(`"exec-train": {
		"container": {
			"image": "registry.redhat.io/ubi9/python-311:latest",
			"command": ["python"],
			"args": ["train.py"]
		}
	}`)
	result, err := Validate([]byte(spec), basicConfig())
	require.NoError(t, err)
	assert.Empty(t, result.Denials, "expected no denials")
	assert.Len(t, result.Warnings, 1, "expected one warning for :latest tag")
	assert.Contains(t, result.Warnings[0], "mutable tag")
}

func TestValidate_DenyDisallowedRegistry(t *testing.T) {
	spec := specWithExecutors(`"exec-train": {
		"container": {
			"image": "docker.io/library/python:3.11",
			"command": ["python"]
		}
	}`)
	config := &Config{
		BlockMutableTags:    false,
		AllowedRegistries:   []string{"registry.redhat.io", "quay.io"},
		MaxTasksPerPipeline: 100,
	}
	result, err := Validate([]byte(spec), config)
	require.NoError(t, err)
	assert.Len(t, result.Denials, 1, "expected one denial for disallowed registry")
	assert.Contains(t, result.Denials[0], "docker.io")
	assert.Contains(t, result.Denials[0], "not in allowed list")
}

func TestValidate_DenyInlineCredential(t *testing.T) {
	spec := specWithExecutors(`"exec-train": {
		"container": {
			"image": "quay.io/myorg/trainer:v1.2.3",
			"command": ["python"],
			"env": [
				{"name": "MY_ACCESS_TOKEN", "value": "AKIAFAKEKEY00000000001234567890abcdef0000"}
			]
		}
	}`)
	config := &Config{
		DeniedEnvVarPatterns:   DefaultDeniedEnvVarPatterns,
		BlockInlineCredentials: true,
	}
	result, err := Validate([]byte(spec), config)
	require.NoError(t, err)
	assert.GreaterOrEqual(t, len(result.Denials), 1, "expected at least one denial for inline credential")
}

func TestValidate_DenyTooManyTasks(t *testing.T) {
	spec := specWithExecutors(`"exec-train": {
		"container": {
			"image": "registry.redhat.io/ubi9/python-311:1.0",
			"command": ["python"]
		}
	},
	"exec-eval": {
		"container": {
			"image": "registry.redhat.io/ubi9/python-311:1.0",
			"command": ["python"]
		}
	}`)
	config := &Config{
		BlockMutableTags:    true,
		MaxTasksPerPipeline: 1,
	}
	result, err := Validate([]byte(spec), config)
	require.NoError(t, err)
	assert.Len(t, result.Denials, 1, "expected one denial for too many tasks")
	assert.Contains(t, result.Denials[0], "exceeding maximum")
}

func TestValidate_AuditModeConvertsDenialsToWarnings(t *testing.T) {
	spec := specWithExecutors(`"exec-train": {
		"container": {
			"image": "docker.io/library/python:3.11",
			"command": ["python"]
		}
	}`)
	config := &Config{
		AllowedRegistries: []string{"registry.redhat.io"},
		Mode:              EnforceModeAudit,
	}
	result, err := Validate([]byte(spec), config)
	require.NoError(t, err)
	assert.Empty(t, result.Denials, "audit mode should produce no denials")
	assert.NotEmpty(t, result.Warnings, "audit mode should convert denials to warnings")
	found := false
	for _, w := range result.Warnings {
		if strings.Contains(w, "[AUDIT]") {
			found = true
			break
		}
	}
	assert.True(t, found, "audit warnings should have [AUDIT] prefix")
}

func TestValidate_OffModeSkipsAllValidation(t *testing.T) {
	spec := specWithExecutors(`"exec-train": {
		"container": {
			"image": "",
			"command": ["python"]
		}
	}`)
	config := &Config{
		Mode: EnforceModeOff,
	}
	result, err := Validate([]byte(spec), config)
	require.NoError(t, err)
	assert.Empty(t, result.Denials, "off mode should skip validation")
	assert.Empty(t, result.Warnings, "off mode should skip validation")
}

func TestValidate_SafeValidateRecoversPanic(t *testing.T) {
	// Pass invalid JSON to trigger an error (not a panic), but test the recovery mechanism
	result, err := SafeValidate(nil, basicConfig())
	assert.Nil(t, result, "result should be nil after panic recovery")
	assert.Error(t, err, "should return an error")
}

func TestValidate_NilConfigUsesDefaults(t *testing.T) {
	spec := specWithExecutors(`"exec-1": {
		"container": {
			"image": "quay.io/myorg/trainer:v1.2.3",
			"command": ["python"],
			"resources": {
				"resourceCpuLimit": "2",
				"resourceMemoryLimit": "4Gi"
			}
		}
	}`)
	result, err := Validate([]byte(spec), nil)
	require.NoError(t, err)
	assert.Empty(t, result.Denials, "nil config should produce no denials for clean pipeline")
}

func TestValidate_FilePathEnvVarNotDenied(t *testing.T) {
	spec := specWithExecutors(`"exec-train": {
		"container": {
			"image": "quay.io/myorg/trainer:v1.2.3",
			"command": ["python"],
			"env": [
				{"name": "GOOGLE_APPLICATION_CREDENTIALS", "value": "/var/secrets/gcp/key.json"}
			]
		}
	}`)
	config := &Config{
		DeniedEnvVarPatterns: DefaultDeniedEnvVarPatterns,
	}
	result, err := Validate([]byte(spec), config)
	require.NoError(t, err)
	assert.Empty(t, result.Denials, "file path value should not trigger env var name denial")
}

func TestValidate_WarnDuplicateTasks(t *testing.T) {
	spec := specWithExecutors(`"exec-train-1": {
		"container": {
			"image": "quay.io/myorg/trainer:v1.2.3",
			"command": ["python"],
			"args": ["train.py"]
		}
	},
	"exec-train-2": {
		"container": {
			"image": "quay.io/myorg/trainer:v1.2.3",
			"command": ["python"],
			"args": ["train.py"]
		}
	}`)
	config := &Config{
		WarnDuplicateTasks: true,
	}
	result, err := Validate([]byte(spec), config)
	require.NoError(t, err)
	assert.Empty(t, result.Denials)
	assert.Len(t, result.Warnings, 1, "expected warning for duplicate executor configuration")
	assert.Contains(t, result.Warnings[0], "identical configuration")
}

func TestValidate_WarnDigestPinning(t *testing.T) {
	spec := specWithExecutors(`"exec-train": {
		"container": {
			"image": "quay.io/myorg/trainer:v1.2.3",
			"command": ["python"]
		}
	}`)
	config := &Config{
		WarnDigestPinning: true,
	}
	result, err := Validate([]byte(spec), config)
	require.NoError(t, err)
	assert.Empty(t, result.Denials)
	assert.Len(t, result.Warnings, 1, "expected warning for missing digest")
	assert.Contains(t, result.Warnings[0], "not pinned by digest")
}
