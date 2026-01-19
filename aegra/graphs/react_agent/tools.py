"""This module provides search tools using Graphiti Core for knowledge graph search.

It includes hybrid search combining semantic similarity and BM25 retrieval,
as well as node search capabilities using Graphiti's search recipes.

These tools leverage the Graphiti knowledge graph for contextual and accurate results.
"""

import json
from collections.abc import Callable
from typing import Any

from graphiti_core import Graphiti
from graphiti_core.search.search_config_recipes import NODE_HYBRID_SEARCH_RRF
from langgraph.runtime import get_runtime

from react_agent.context import Context
from react_agent.utils import load_chat_model

PLANNER_PROMPT = """You are a query planner for a SEC 10-K financial research system.

Given a user query, generate a plan of sub-queries to execute against the knowledge graph.

## Available Tools
1. `search` - Hybrid search for facts/relationships. Use for: revenue, risks, financials, business segments
2. `search_nodes` - Find entity nodes. Use for: finding companies, executives, business units
3. `search_with_context` - Contextual search around an entity (requires node UUID from search_nodes)

## Data Scope
Only these 7 companies have data: GOOGL (Alphabet), AMZN (Amazon), AAPL (Apple), META (Meta), MSFT (Microsoft), NVDA (Nvidia), TSLA (Tesla)

## Rules
1. Generate 1-5 sub-queries maximum
2. Each sub-query should target specific information
3. For comparisons, create separate queries per company
4. Be specific - include company name in each query
5. If query is out of scope, return empty plan with reason

## Output Format (JSON only, no markdown):
{{
  "is_in_scope": true/false,
  "out_of_scope_reason": "reason if not in scope, else null",
  "plan": [
    {{"tool": "search|search_nodes", "query": "specific query text", "purpose": "what this finds"}}
  ]
}}

User Query: {user_query}

Generate the plan:"""


async def create_query_plan(user_query: str) -> dict[str, Any]:
    """Generate a query execution plan for the user's question.

    This tool analyzes the user query and creates a structured plan of sub-queries
    to execute against the knowledge graph. Call this FIRST before any search tools.

    Args:
        user_query: The original user question to plan for.

    Returns:
        A plan containing sub-queries to execute with their target tools.
    """
    runtime = get_runtime(Context)
    ctx = runtime.context

    model = load_chat_model(ctx.model)

    prompt = PLANNER_PROMPT.format(user_query=user_query)

    response = await model.ainvoke([{"role": "user", "content": prompt}])

    try:
        # Extract JSON from response
        content = response.content
        if isinstance(content, str):
            # Try to parse as JSON directly
            plan = json.loads(content)
        else:
            plan = {
                "is_in_scope": False,
                "out_of_scope_reason": "Failed to generate plan",
                "plan": [],
            }
    except json.JSONDecodeError:
        # If JSON parsing fails, try to extract JSON from the response
        content_str = str(response.content)
        start = content_str.find("{")
        end = content_str.rfind("}") + 1
        if start != -1 and end > start:
            try:
                plan = json.loads(content_str[start:end])
            except json.JSONDecodeError:
                plan = {
                    "is_in_scope": False,
                    "out_of_scope_reason": "Failed to parse plan",
                    "plan": [],
                }
        else:
            plan = {
                "is_in_scope": False,
                "out_of_scope_reason": "Failed to parse plan",
                "plan": [],
            }

    return {
        "user_query": user_query,
        "is_in_scope": plan.get("is_in_scope", False),
        "out_of_scope_reason": plan.get("out_of_scope_reason"),
        "sub_queries": plan.get("plan", []),
        "total_queries": len(plan.get("plan", [])),
    }


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


async def search_with_context(query: str, center_node_uuid: str) -> dict[str, Any]:
    """Search with context reranking based on graph distance to a center node.

    This function performs a search and reranks results based on their graph
    distance to a specific node, providing more contextually relevant results
    for entity-specific queries.

    Args:
        query: The search query to find relevant information.
        center_node_uuid: UUID of the node to use as the center for reranking.

    Returns:
        A dictionary containing reranked search results.
    """
    runtime = get_runtime(Context)
    ctx = runtime.context

    graphiti = Graphiti(ctx.neo4j_uri, ctx.neo4j_user, ctx.neo4j_password)

    try:
        results = await graphiti.search(query, center_node_uuid=center_node_uuid)

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
            "center_node_uuid": center_node_uuid,
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


TOOLS: list[Callable[..., Any]] = [create_query_plan, search, search_with_context, search_nodes]
