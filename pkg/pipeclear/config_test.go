package pipeclear

import (
	"os"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestParseConfig_Defaults(t *testing.T) {
	config, err := ParseConfig([]byte("{}"))
	require.NoError(t, err)
	assert.Equal(t, EnforceModeEnforce, config.Mode)
	assert.True(t, config.BlockMutableTags)
	assert.True(t, config.BlockInlineCredentials)
	assert.Equal(t, 100, config.MaxTasksPerPipeline)
	assert.True(t, config.WarnDuplicateTasks)
	assert.False(t, config.WarnDigestPinning)
	assert.False(t, config.WarnResourceLimits)
	assert.False(t, config.WarnSemverTags)
}

func TestParseConfig_Custom(t *testing.T) {
	yamlData := `
mode: audit
allowedRegistries:
  - quay.io/myorg
  - registry.redhat.io
blockMutableTags: false
maxTasks: 50
`
	config, err := ParseConfig([]byte(yamlData))
	require.NoError(t, err)
	assert.Equal(t, EnforceModeAudit, config.Mode)
	assert.Equal(t, []string{"quay.io/myorg", "registry.redhat.io"}, config.AllowedRegistries)
	assert.False(t, config.BlockMutableTags)
	assert.Equal(t, 50, config.MaxTasksPerPipeline)
}

func TestLoadConfig_File(t *testing.T) {
	content := `
mode: "off"
maxTasks: 200
`
	f, err := os.CreateTemp("", "pipeclear-*.yaml")
	require.NoError(t, err)
	defer os.Remove(f.Name())
	_, err = f.WriteString(content)
	require.NoError(t, err)
	f.Close()

	config, err := LoadConfig(f.Name())
	require.NoError(t, err)
	assert.Equal(t, EnforceModeOff, config.Mode)
	assert.Equal(t, 200, config.MaxTasksPerPipeline)
}

func TestLoadConfig_FileNotFound(t *testing.T) {
	_, err := LoadConfig("/nonexistent/path.yaml")
	assert.Error(t, err)
}

func TestDefaultConfig(t *testing.T) {
	config := DefaultConfig()
	assert.Equal(t, EnforceModeEnforce, config.Mode)
	assert.True(t, config.BlockMutableTags)
	assert.True(t, config.BlockInlineCredentials)
	assert.Equal(t, 100, config.MaxTasksPerPipeline)
}
