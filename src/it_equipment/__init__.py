"""IT Equipment Request Handler.

An MCP server that exposes a mock IT-equipment system, plus a ReAct agent that
uses it to approve, deny, or escalate employee equipment requests.
"""

from importlib.metadata import version

#: Package version, read from the installed distribution so ``pyproject.toml``
#: stays the single source of truth.
__version__: str = version("it-equipment-handler")

__all__ = ["__version__"]
