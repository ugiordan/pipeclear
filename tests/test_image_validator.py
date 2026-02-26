import pytest
from unittest.mock import patch, MagicMock
from src.validators.image import ImageValidator


def test_parse_image_reference_with_tag():
    """Test parsing image reference into components."""
    validator = ImageValidator()
    registry, repo, tag = validator.parse_image_ref(
        "registry.access.redhat.com/ubi9/python-311:latest"
    )
    assert registry == "registry.access.redhat.com"
    assert repo == "ubi9/python-311"
    assert tag == "latest"


def test_parse_image_reference_without_tag():
    """Test parsing image reference without explicit tag."""
    validator = ImageValidator()
    registry, repo, tag = validator.parse_image_ref(
        "quay.io/ugiordano/pipeclear"
    )
    assert registry == "quay.io"
    assert repo == "ugiordano/pipeclear"
    assert tag == "latest"


def test_parse_image_reference_docker_hub():
    """Test parsing Docker Hub image reference."""
    validator = ImageValidator()
    registry, repo, tag = validator.parse_image_ref("python:3.11")
    assert registry == "docker.io"
    assert repo == "library/python"
    assert tag == "3.11"


def test_check_accessible_with_valid_image():
    """Test that a known public image is detected as accessible."""
    validator = ImageValidator()
    assert validator.check_accessible("registry.access.redhat.com/ubi9/python-311:latest") is True


def test_check_accessible_with_invalid_image():
    """Test that a nonexistent image is detected as inaccessible."""
    validator = ImageValidator()
    assert validator.check_accessible("quay.io/nonexistent/image-xyz-12345:fake") is False


def test_validate_image_returns_issues_for_bad_image():
    """Test that validate_image flags inaccessible base images."""
    validator = ImageValidator()
    issues = validator.validate_image("quay.io/nonexistent/image-xyz-12345:fake")
    assert len(issues) == 1
    assert issues[0]['severity'] == 'critical'
    assert issues[0]['category'] == 'image'


def test_validate_image_returns_no_issues_for_good_image():
    """Test that validate_image passes for accessible images."""
    validator = ImageValidator()
    issues = validator.validate_image("registry.access.redhat.com/ubi9/python-311:latest")
    assert len(issues) == 0
