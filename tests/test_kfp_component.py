import pytest


def test_preflight_check_component_exists():
    """Test that the preflight_check KFP component can be imported."""
    from pipeclear.kfp.component import preflight_check
    assert callable(preflight_check)


def test_preflight_check_is_kfp_component():
    """Test that preflight_check is decorated as a KFP component."""
    from pipeclear.kfp.component import preflight_check
    assert hasattr(preflight_check, 'component_spec')


def test_preflight_check_component_spec():
    """Test that the component spec has correct metadata."""
    from pipeclear.kfp.component import preflight_check
    spec = preflight_check.component_spec
    assert spec.name == 'preflight-check'


def test_kfp_module_exports():
    """Test that kfp module exports the component."""
    from pipeclear.kfp import preflight_check
    assert callable(preflight_check)
