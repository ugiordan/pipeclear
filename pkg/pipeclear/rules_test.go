package pipeclear

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestExtractRegistry(t *testing.T) {
	assert.Equal(t, "docker.io", ExtractRegistry("docker.io/library/python:3.11"))
	assert.Equal(t, "quay.io", ExtractRegistry("quay.io/myorg/myimage:v1"))
	assert.Equal(t, "registry.redhat.io", ExtractRegistry("registry.redhat.io/ubi9:latest"))
	assert.Equal(t, "docker.io", ExtractRegistry("python:3.11"))
}

func TestExtractTag(t *testing.T) {
	assert.Equal(t, "3.11", ExtractTag("python:3.11"))
	assert.Equal(t, "latest", ExtractTag("python:latest"))
	assert.Equal(t, "", ExtractTag("python"))
	assert.Equal(t, "", ExtractTag("python@sha256:abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"))
}

func TestIsRegistryAllowed(t *testing.T) {
	assert.True(t, isRegistryAllowed("quay.io/myorg/image:v1", []string{"quay.io/myorg", "registry.redhat.io"}))
	assert.True(t, isRegistryAllowed("registry.redhat.io/ubi9:latest", []string{"quay.io/myorg", "registry.redhat.io"}))
	assert.False(t, isRegistryAllowed("docker.io/library/python:3.11", []string{"quay.io/myorg", "registry.redhat.io"}))
}

func TestLooksLikeFilePath(t *testing.T) {
	assert.True(t, looksLikeFilePath("/usr/bin/python"))
	assert.True(t, looksLikeFilePath("./script.sh"))
	assert.True(t, looksLikeFilePath("../data/file"))
	assert.False(t, looksLikeFilePath("ghp_abc123def456"))
	assert.False(t, looksLikeFilePath("some-value"))
}

func TestConfigValidate(t *testing.T) {
	config := DefaultConfig()
	assert.NoError(t, config.Validate())

	config.DeniedEnvVarPatterns = []string{"_SECRET", ""}
	assert.Error(t, config.Validate())

	config.DeniedEnvVarPatterns = nil
	config.Mode = "invalid"
	assert.Error(t, config.Validate())
}
