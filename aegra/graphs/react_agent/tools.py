"""This module provides search tools using Graphiti Core for knowledge graph search.

It includes hybrid search combining semantic similarity and BM25 retrieval,
as well as node search capabilities using Graphiti's search recipes.

These tools leverage the Graphiti knowledge graph for contextual and accurate results.
"""

from collections.abc import Callable
from typing import Any

from graphiti_core import Graphiti
from graphiti_core.search.search_config_recipes import NODE_HYBRID_SEARCH_RRF
from langgraph.runtime import get_runtime

from react_agent.context import Context


async def search(query: str) -> dict[str, Any]:
    """Search for information in the knowledge graph.

    This function performs a hybrid search combining semantic similarity and BM25
    text retrieval using Graphiti. It returns relevant facts and relationships
    from the knowledge graph.

    Args:
        query: The search query to find relevant information.

    Returns:
        A dictionary containing search results with facts and metadata.
    """
    runtime = get_runtime(Context)
    ctx = runtime.context

    graphiti = Graphiti(ctx.neo4j_uri, ctx.neo4j_user, ctx.neo4j_password)

    try:
        results = await graphiti.search(query)

        search_results = []
        for result in results[: ctx.max_search_results]:
            result_data = {
                "uuid": result.uuid,
                "fact": result.fact,
            }
            if hasattr(result, "valid_at") and result.valid_at:
                result_data["valid_from"] = str(result.valid_at)
            if hasattr(result, "invalid_at") and result.invalid_at:
                result_data["valid_until"] = str(result.invalid_at)
            search_results.append(result_data)

        return {
            "query": query,
            "total_results": len(search_results),
            "results": search_results,
        }
    finally:
        await graphiti.close()


async def search_nodes(query: str, limit: int = 5) -> dict[str, Any]:
    """Search for nodes in the knowledge graph using hybrid search.

    This function uses Graphiti's NODE_HYBRID_SEARCH_RRF recipe to retrieve
    nodes directly instead of edges, useful for finding entities.

    Args:
        query: The search query to find relevant nodes.
        limit: Maximum number of nodes to return (default: 5).

    Returns:
        A dictionary containing node search results with names and summaries.
    """
    runtime = get_runtime(Context)
    ctx = runtime.context

    graphiti = Graphiti(ctx.neo4j_uri, ctx.neo4j_user, ctx.neo4j_password)

    try:
        node_search_config = NODE_HYBRID_SEARCH_RRF.model_copy(deep=True)
        node_search_config.limit = limit

        search_results = await graphiti._search(
            query=query,
            config=node_search_config,
        )

        nodes = []
        for node in search_results.nodes:
            node_data = {
                "uuid": node.uuid,
                "name": node.name,
                "summary": (
                    node.summary[:200] + "..."
                    if len(node.summary) > 200
                    else node.summary
                ),
                "labels": list(node.labels),
                "created_at": str(node.created_at),
            }
            if hasattr(node, "attributes") and node.attributes:
                node_data["attributes"] = node.attributes
            nodes.append(node_data)

        return {
            "query": query,
            "total_results": len(nodes),
            "nodes": nodes,
        }
    finally:
        await graphiti.close()


TOOLS: list[Callable[..., Any]] = [search, search_nodes]
