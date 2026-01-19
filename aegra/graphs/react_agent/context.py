"""Define the configurable parameters for the agent."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from typing import Annotated

from react_agent import prompts


@dataclass(kw_only=True)
class Context:
    """The context for the agent."""

    system_prompt: str = field(
        default=prompts.SYSTEM_PROMPT,
        metadata={
            "description": "The system prompt to use for the agent's interactions. "
            "This prompt sets the context and behavior for the agent."
        },
    )

    model: Annotated[str, {"__template_metadata__": {"kind": "llm"}}] = field(
        default="openai/gpt-5-mini",
        metadata={
            "description": "The name of the language model to use for the agent's main interactions. "
            "Should be in the form: provider/model-name."
        },
    )

    max_search_results: int = field(
        default=10,
        metadata={
            "description": "The maximum number of search results to return for each search query."
        },
    )

    # Neo4j connection parameters for Graphiti
    neo4j_uri: str = field(
        default="bolt://neo4j:7687",
        metadata={
            "description": "The URI of the Neo4j database for Graphiti knowledge graph."
        },
    )

    neo4j_user: str = field(
        default="neo4j",
        metadata={
            "description": "The username for Neo4j database authentication."
        },
    )

    neo4j_password: str = field(
        default="password123",
        metadata={
            "description": "The password for Neo4j database authentication."
        },
    )

    def __post_init__(self) -> None:
        """Fetch env vars for attributes that were not passed as args."""
        for f in fields(self):
            if not f.init:
                continue

            if getattr(self, f.name) == f.default:
                setattr(self, f.name, os.environ.get(f.name.upper(), f.default))
