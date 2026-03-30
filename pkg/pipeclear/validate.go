package pipeclear

import (
	"encoding/json"
	"fmt"
	"runtime/debug"
	"sort"
	"strings"

	"github.com/kubeflow/pipelines/api/v2alpha1/go/pipelinespec"
	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/types/known/structpb"
)

// SafeValidate wraps Validate with panic recovery.
// If validation panics, it returns an error instead of crashing the caller.
func SafeValidate(specJSON []byte, config *Config) (result *Result, err error) {
	defer func() {
		if r := recover(); r != nil {
			result = nil
			err = fmt.Errorf("PipeClear validation panicked: %v\n%s", r, debug.Stack())
		}
	}()
	return Validate(specJSON, config)
}

// Validate runs PipeClear validation on a raw KFP pipeline spec (JSON or YAML).
// The spec should be the full KFP IR with pipelineInfo, deploymentSpec, etc.
func Validate(specJSON []byte, config *Config) (*Result, error) {
	if config == nil {
		config = DefaultConfig()
	}

	result := &Result{}

	if config.Mode == EnforceModeOff {
		return result, nil
	}

	if err := config.Validate(); err != nil {
		return nil, fmt.Errorf("invalid PipeClear config: %w", err)
	}

	// Parse the pipeline spec to extract the deployment spec
	var rawSpec struct {
		DeploymentSpec json.RawMessage `json:"deploymentSpec"`
	}
	if err := json.Unmarshal(specJSON, &rawSpec); err != nil {
		return nil, fmt.Errorf("failed to parse pipeline spec: %w", err)
	}

	if rawSpec.DeploymentSpec == nil {
		return result, nil
	}

	// Parse DeploymentSpec as structpb.Struct first, then as PipelineDeploymentConfig
	var deploymentStruct structpb.Struct
	if err := protojson.Unmarshal(rawSpec.DeploymentSpec, &deploymentStruct); err != nil {
		return nil, fmt.Errorf("failed to parse deployment spec: %w", err)
	}

	deploymentJSON, err := protojson.Marshal(&deploymentStruct)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal deployment spec: %w", err)
	}

	var deploymentConfig pipelinespec.PipelineDeploymentConfig
	if err := protojson.Unmarshal(deploymentJSON, &deploymentConfig); err != nil {
		return nil, fmt.Errorf("failed to parse deployment config: %w", err)
	}

	executors := deploymentConfig.GetExecutors()

	if config.MaxTasksPerPipeline > 0 && len(executors) > config.MaxTasksPerPipeline {
		result.Denials = append(result.Denials,
			fmt.Sprintf("pipeline has %d tasks, exceeding maximum of %d", len(executors), config.MaxTasksPerPipeline))
	}

	executorNames := make([]string, 0, len(executors))
	for name := range executors {
		executorNames = append(executorNames, name)
	}
	sort.Strings(executorNames)

	type upperPattern struct {
		original string
		upper    string
	}
	upperPatterns := make([]upperPattern, len(config.DeniedEnvVarPatterns))
	for i, p := range config.DeniedEnvVarPatterns {
		upperPatterns[i] = upperPattern{original: p, upper: strings.ToUpper(p)}
	}

	type executorFingerprint struct {
		image   string
		command string
		args    string
	}
	fingerprints := make(map[executorFingerprint]string)

	for _, name := range executorNames {
		executor := executors[name]
		containerSpec := executor.GetContainer()
		if containerSpec == nil {
			continue
		}

		image := strings.TrimSpace(containerSpec.GetImage())
		if image == "" {
			result.Denials = append(result.Denials,
				fmt.Sprintf("executor %q has no container image specified", name))
			continue
		}

		tag := ExtractTag(image)
		isDigestPinned := sha256DigestRegex.MatchString(image)

		if config.BlockMutableTags && !isDigestPinned {
			if tag == "" || tag == "latest" {
				result.Warnings = append(result.Warnings,
					fmt.Sprintf("image %q uses mutable tag - consider using a specific version", image))
			}
		}

		if len(config.AllowedRegistries) > 0 {
			allowed := isRegistryAllowed(image, config.AllowedRegistries)
			if !allowed {
				result.Denials = append(result.Denials,
					fmt.Sprintf("image %q uses registry not in allowed list %v", image, config.AllowedRegistries))
			}
		}

		if config.WarnDigestPinning {
			if !isDigestPinned {
				result.Warnings = append(result.Warnings,
					fmt.Sprintf("image %q is not pinned by digest - consider using @sha256: for reproducibility", image))
			}
		}

		if config.WarnSemverTags {
			if tag != "" && !semverRegex.MatchString(tag) {
				result.Warnings = append(result.Warnings,
					fmt.Sprintf("image %q has non-semver tag %q", image, tag))
			}
		}

		if config.WarnResourceLimits {
			resources := containerSpec.GetResources()
			if resources == nil || (resources.GetResourceCpuLimit() == "" && resources.GetResourceMemoryLimit() == "") {
				result.Warnings = append(result.Warnings,
					fmt.Sprintf("executor %q has no resource limits specified - consider setting CPU/memory limits", name))
			}
		}

		for _, envVar := range containerSpec.GetEnv() {
			envName := envVar.GetName()
			envValue := envVar.GetValue()

			if len(upperPatterns) > 0 && !looksLikeFilePath(envValue) {
				upperName := strings.ToUpper(envName)
				for _, up := range upperPatterns {
					if strings.HasSuffix(upperName, up.upper) {
						result.Denials = append(result.Denials,
							fmt.Sprintf("executor %q has suspicious env var %q matching denied pattern %q - use Kubernetes Secrets instead", name, envName, up.original))
						break
					}
				}
			}

			if config.BlockInlineCredentials && envValue != "" {
				trimmedValue := strings.TrimSpace(envValue)
				if len(trimmedValue) >= minCredentialLength {
					for _, prefix := range inlineCredentialPrefixes {
						if strings.HasPrefix(trimmedValue, prefix) {
							result.Denials = append(result.Denials,
								fmt.Sprintf("executor %q env var %q contains what appears to be a hardcoded credential - use Kubernetes Secrets instead", name, envName))
							break
						}
					}
				}
			}
		}

		if config.BlockInlineCredentials {
			cmd := containerSpec.GetCommand()
			args := containerSpec.GetArgs()
			allStrings := make([]string, 0, len(cmd)+len(args))
			allStrings = append(allStrings, cmd...)
			allStrings = append(allStrings, args...)
			found := false
			for _, s := range allStrings {
				if len(s) < minCredentialLength {
					continue
				}
				for _, prefix := range inlineCredentialPrefixes {
					if strings.Contains(s, prefix) {
						result.Denials = append(result.Denials,
							fmt.Sprintf("executor %q command/args contain what appears to be a hardcoded credential - use Kubernetes Secrets instead", name))
						found = true
						break
					}
				}
				if found {
					break
				}
			}
		}

		if config.WarnDuplicateTasks {
			fp := executorFingerprint{
				image:   image,
				command: strings.Join(containerSpec.GetCommand(), "\x00"),
				args:    strings.Join(containerSpec.GetArgs(), "\x00"),
			}
			if firstName, exists := fingerprints[fp]; exists {
				result.Warnings = append(result.Warnings,
					fmt.Sprintf("executor %q has identical configuration to %q - possible unintentional duplicate", name, firstName))
			} else {
				fingerprints[fp] = name
			}
		}
	}

	if config.Mode == EnforceModeAudit {
		for _, d := range result.Denials {
			result.Warnings = append(result.Warnings, "[AUDIT] "+d)
		}
		result.Denials = nil
	}

	return result, nil
}
