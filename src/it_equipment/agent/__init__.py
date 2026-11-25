"""The agent: reads a request, uses the MCP server's tools, and decides.

It depends only on the MCP protocol, never on the server's internals, and on an
``LLMClient``, so the model provider can be swapped without touching agent code.
"""
