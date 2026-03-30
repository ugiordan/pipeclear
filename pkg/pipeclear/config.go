package pipeclear

import (
	"encoding/json"
	"os"

	"sigs.k8s.io/yaml"
)

// EnforceMode controls how PipeClear handles denials.
type EnforceMode string

const (
	EnforceModeEnforce EnforceMode = "enforce"
	EnforceModeAudit   EnforceMode = "audit"
	EnforceModeOff     EnforceMode = "off"
)

// Config holds all PipeClear validation settings.
// Field names use camelCase JSON tags for compatibility with the shared YAML schema.
type Config struct {
	Mode                   EnforceMode `json:"mode" yaml:"mode"`
	AllowedRegistries      []string    `json:"allowedRegistries" yaml:"allowedRegistries"`
	BlockMutableTags       bool        `json:"blockMutableTags" yaml:"blockMutableTags"`
	BlockInlineCredentials bool        `json:"blockInlineCredentials" yaml:"blockInlineCredentials"`
	MaxTasksPerPipeline    int         `json:"maxTasks" yaml:"maxTasks"`
	DeniedEnvVarPatterns   []string    `json:"deniedEnvVarPatterns" yaml:"deniedEnvVarPatterns"`
	WarnDigestPinning      bool        `json:"warnDigestPinning" yaml:"warnDigestPinning"`
	WarnSemverTags         bool        `json:"warnSemverTags" yaml:"warnSemverTags"`
	WarnResourceLimits     bool        `json:"warnResourceLimits" yaml:"warnResourceLimits"`
	WarnDuplicateTasks     bool        `json:"warnDuplicateTasks" yaml:"warnDuplicateTasks"`
}

// DefaultConfig returns a Config with sensible defaults.
func DefaultConfig() *Config {
	return &Config{
		Mode:                   EnforceModeEnforce,
		BlockMutableTags:       true,
		BlockInlineCredentials: true,
		MaxTasksPerPipeline:    100,
		WarnDuplicateTasks:     true,
	}
}

// ParseConfig parses a Config from raw YAML or JSON bytes.
// Missing fields are filled with defaults.
func ParseConfig(data []byte) (*Config, error) {
	config := DefaultConfig()
	jsonData, err := yaml.YAMLToJSON(data)
	if err != nil {
		return nil, err
	}
	if err := json.Unmarshal(jsonData, config); err != nil {
		return nil, err
	}
	return config, nil
}

// LoadConfig reads and parses a Config from a YAML file.
func LoadConfig(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	return ParseConfig(data)
}
