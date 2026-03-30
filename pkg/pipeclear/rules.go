package pipeclear

import (
	"fmt"
	"regexp"
	"strings"
)

// DefaultDeniedEnvVarPatterns are patterns for env var names likely to contain secrets.
var DefaultDeniedEnvVarPatterns = []string{
	"_PASSWORD", "_SECRET", "_TOKEN", "_CREDENTIAL",
	"_API_KEY", "_APIKEY", "_SECRET_KEY", "_ACCESS_KEY", "_PRIVATE_KEY",
	"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
	"GOOGLE_APPLICATION_CREDENTIALS",
}

// inlineCredentialPrefixes are prefixes that indicate a hardcoded credential value.
var inlineCredentialPrefixes = []string{
	"ghp_",        // GitHub personal access token
	"gho_",        // GitHub OAuth token
	"ghu_",        // GitHub user-to-server token
	"ghs_",        // GitHub server-to-server token
	"github_pat_", // GitHub fine-grained PAT
	"glpat-",      // GitLab personal access token
	"sk-",         // OpenAI API key
	"AKIA",        // AWS access key
	"ASIA",        // AWS temporary session credentials
	"hf_",         // HuggingFace token
	"xoxb-",       // Slack bot token
	"xoxp-",       // Slack user token
	"pypi-",       // PyPI API token
	"npm_",        // npm auth token
	"dop_v1_",     // DigitalOcean PAT
	"SG.",         // SendGrid API key
	"-----BEGIN",  // PEM private keys
}

// semverRegex matches semantic versioning tags like v1.2.3, 1.0.0-rc1, etc.
var semverRegex = regexp.MustCompile(`^v?[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?(\+[a-zA-Z0-9.]+)?$`)

// sha256DigestRegex validates the format of a SHA256 digest reference.
var sha256DigestRegex = regexp.MustCompile(`@sha256:[a-fA-F0-9]{64}$`)

// minCredentialLength is the minimum value length for inline credential detection.
const minCredentialLength = 20

// Result holds validation findings.
type Result struct {
	Warnings []string
	Denials  []string
}

// Validate checks the config for invalid values.
func (c *Config) Validate() error {
	for i, p := range c.DeniedEnvVarPatterns {
		if strings.TrimSpace(p) == "" {
			return fmt.Errorf("DeniedEnvVarPatterns[%d] is empty - this would match all env vars", i)
		}
	}
	if c.Mode != "" && c.Mode != EnforceModeEnforce && c.Mode != EnforceModeAudit && c.Mode != EnforceModeOff {
		return fmt.Errorf("invalid Mode %q - must be \"enforce\", \"audit\", or \"off\"", c.Mode)
	}
	return nil
}

// looksLikeFilePath returns true if the value appears to be a file path.
func looksLikeFilePath(value string) bool {
	trimmed := strings.TrimSpace(value)
	return strings.HasPrefix(trimmed, "/") || strings.HasPrefix(trimmed, "./") || strings.HasPrefix(trimmed, "../")
}

// isRegistryAllowed checks if an image's registry matches the allowed list.
func isRegistryAllowed(image string, allowedRegistries []string) bool {
	registry := ExtractRegistry(image)
	imageBase := image
	if idx := strings.Index(imageBase, "@"); idx >= 0 {
		imageBase = imageBase[:idx]
	}
	if idx := strings.LastIndex(imageBase, ":"); idx >= 0 {
		lastSlash := strings.LastIndex(imageBase, "/")
		if idx > lastSlash {
			imageBase = imageBase[:idx]
		}
	}

	for _, r := range allowedRegistries {
		if strings.Contains(r, "/") {
			if strings.HasPrefix(imageBase, r+"/") || imageBase == r {
				return true
			}
		} else {
			if registry == r {
				return true
			}
		}
	}
	return false
}

// ExtractTag returns the tag portion of an image reference.
func ExtractTag(image string) string {
	if strings.Contains(image, "@sha256:") {
		return ""
	}
	lastSlash := strings.LastIndex(image, "/")
	nameTag := image
	if lastSlash >= 0 {
		nameTag = image[lastSlash+1:]
	}
	if colonIdx := strings.LastIndex(nameTag, ":"); colonIdx >= 0 {
		candidate := nameTag[colonIdx+1:]
		if lastSlash < 0 && isPort(candidate) {
			return ""
		}
		return candidate
	}
	return ""
}

// isPort returns true if the string looks like a port number.
func isPort(s string) bool {
	if len(s) == 0 || len(s) > 5 {
		return false
	}
	for _, c := range s {
		if c < '0' || c > '9' {
			return false
		}
	}
	return true
}

// ExtractRegistry extracts the registry from an image reference.
func ExtractRegistry(image string) string {
	if idx := strings.Index(image, "@"); idx >= 0 {
		image = image[:idx]
	}
	if !strings.Contains(image, "/") {
		return "docker.io"
	}
	firstSegment := strings.SplitN(image, "/", 2)[0]
	if strings.Contains(firstSegment, ".") || strings.Contains(firstSegment, ":") || firstSegment == "localhost" {
		return firstSegment
	}
	return "docker.io"
}
