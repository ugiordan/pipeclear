"""Container image accessibility validator."""
import json
import re
import urllib.request
import urllib.error
from typing import List, Dict, Tuple, Optional


class ImageValidator:
    """Validates that container images are accessible from registries."""

    def parse_image_ref(self, image: str) -> Tuple[str, str, str]:
        """Parse a container image reference into registry, repo, tag.

        Args:
            image: Full image reference (e.g., 'quay.io/user/image:tag')

        Returns:
            Tuple of (registry, repository, tag)
        """
        if ':' in image.split('/')[-1]:
            image_no_tag, tag = image.rsplit(':', 1)
        else:
            image_no_tag = image
            tag = 'latest'

        parts = image_no_tag.split('/')

        if len(parts) == 1:
            return 'docker.io', f'library/{parts[0]}', tag
        elif len(parts) == 2 and '.' not in parts[0]:
            return 'docker.io', image_no_tag, tag
        else:
            registry = parts[0]
            repo = '/'.join(parts[1:])
            return registry, repo, tag

    def _parse_www_authenticate(self, header: str) -> Optional[Dict[str, str]]:
        """Parse a WWW-Authenticate Bearer header into its components.

        Args:
            header: The WWW-Authenticate header value

        Returns:
            Dict with realm, service, scope keys, or None if not Bearer
        """
        if not header.lower().startswith('bearer '):
            return None

        params = {}
        for match in re.finditer(r'(\w+)="([^"]*)"', header):
            params[match.group(1)] = match.group(2)

        return params if 'realm' in params else None

    def _get_bearer_token(self, auth_params: Dict[str, str]) -> Optional[str]:
        """Obtain a Bearer token from the auth realm.

        Args:
            auth_params: Parsed WWW-Authenticate parameters (realm, service, scope)

        Returns:
            The token string, or None if token acquisition failed
        """
        realm = auth_params['realm']
        query_parts = []
        if 'service' in auth_params:
            query_parts.append(f"service={urllib.request.quote(auth_params['service'])}")
        if 'scope' in auth_params:
            query_parts.append(f"scope={urllib.request.quote(auth_params['scope'])}")

        token_url = realm
        if query_parts:
            token_url += '?' + '&'.join(query_parts)

        try:
            req = urllib.request.Request(token_url, method='GET')
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                return data.get('token') or data.get('access_token')
        except Exception:
            return None

    def check_accessible(self, image: str) -> bool:
        """Check if a container image is accessible from its registry.

        Uses the Docker Registry HTTP API v2 to verify image accessibility.
        Handles Bearer token authentication flow for registries that require it.

        Args:
            image: Full image reference

        Returns:
            True if the image manifest can be reached
        """
        registry, repo, tag = self.parse_image_ref(image)

        if registry == 'docker.io':
            url = f'https://registry.hub.docker.com/v2/{repo}/tags/list'
        else:
            url = f'https://{registry}/v2/{repo}/tags/list'

        try:
            req = urllib.request.Request(url, method='GET')
            req.add_header('Accept', 'application/json')
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status == 200
        except urllib.error.HTTPError as e:
            if e.code == 401:
                # Registry requires authentication -- attempt Bearer token flow
                www_auth = None
                for key, value in e.headers.items():
                    if key.lower() == 'www-authenticate':
                        www_auth = value
                        break

                if not www_auth:
                    return False

                auth_params = self._parse_www_authenticate(www_auth)
                if not auth_params:
                    return False

                token = self._get_bearer_token(auth_params)
                if not token:
                    return False

                # Retry the request with the token
                return self._check_with_token(url, token)
            return False
        except Exception:
            return False

    def _check_with_token(self, url: str, token: str) -> bool:
        """Retry a registry request using a Bearer token.

        Args:
            url: The registry API URL
            token: The Bearer token

        Returns:
            True if the authenticated request succeeds
        """
        try:
            req = urllib.request.Request(url, method='GET')
            req.add_header('Accept', 'application/json')
            req.add_header('Authorization', f'Bearer {token}')
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status == 200
        except Exception:
            return False

    def validate_image(self, image: str) -> List[Dict]:
        """Validate a container image and return issues.

        Args:
            image: Full image reference

        Returns:
            List of issues (empty if image is accessible)
        """
        if self.check_accessible(image):
            return []

        return [{
            'severity': 'critical',
            'category': 'image',
            'message': f"Base image not accessible: {image}",
            'suggestion': (
                "Fix: Use a publicly accessible image like "
                "'registry.access.redhat.com/ubi9/python-311:latest' "
                "or ensure cluster has pull credentials for this registry"
            ),
            'time_impact': "Would fail with ImagePullBackOff (6+ minutes to detect)"
        }]
