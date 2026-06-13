import inspect

from src.forge.client import ForgeClient


def test_forge_protocol_has_mr_methods():
    members = {name for name, _ in inspect.getmembers(ForgeClient)}
    assert "create_merge_request" in members
    assert "get_merge_request_diff" in members
