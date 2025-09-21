"""
GraphQL API implementation for v1.

Provides a comprehensive GraphQL interface for querying combat log data
with type-safe resolvers and efficient data loading.
"""

from .schema import schema, app

__all__ = ["schema", "app"]
