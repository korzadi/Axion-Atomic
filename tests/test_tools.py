import pytest
from agent.tools import safe_workspace_path

def test_path_traversal_rejected():
    with pytest.raises(ValueError):
        safe_workspace_path("../../etc/passwd")
