"""
MCP (Model Context Protocol) 集成模块

提供了MCP服务器实现，支持工具、资源和提示功能。
"""

from .server import McpServer

__all__ = ["McpServer"]
