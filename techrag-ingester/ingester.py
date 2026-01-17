import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from graphiti_core import Graphiti
from graphiti_core.llm_client.openai_client import OpenAIClient, LLMConfig
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from graphiti_core.nodes import EpisodeType
from graphiti_core.utils.maintenance.graph_data_operations import clear_data

load_dotenv()

# Set semaphore limit for concurrency control
os.environ['SEMAPHORE_LIMIT'] = '1'

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

# Path to clean chunks
CLEAN_CHUNKS_DIR = Path(__file__).parent / 'clean_chunks'


def load_episodes_from_file(file_path: Path) -> list[dict]:
    """Load episodes from a single clean chunks JSON file."""
    episodes = []
    company_name = file_path.stem.replace('_clean', '')
    
    with open(file_path, 'r') as f:
        chunks = json.load(f)
    
    for chunk in chunks:
        chunk_id = chunk.get('chunk_id', 0)
        info = chunk.get('info', '')
        data = chunk.get('data', {})
        
        # Add text episode if info is not empty
        if info and info.strip():
            episodes.append({
                'name': f'{company_name}_chunk_{chunk_id}_text',
                'content': info,
                'type': EpisodeType.text,
                'description': f'{company_name} 10-K filing text',
            })
        
        # Add JSON episode if data is not empty
        if data:
            episodes.append({
                'name': f'{company_name}_chunk_{chunk_id}_json',
                'content': json.dumps(data),
                'type': EpisodeType.json,
                'description': f'{company_name} 10-K filing structured data',
            })
    
    return episodes


async def ingest_episodes(graphiti: Graphiti, episodes: list[dict], delay_seconds: int = 20):
    """Ingest episodes one at a time with delay."""
    total = len(episodes)
    failed_episodes = []
    
    for i, ep in enumerate(episodes):
        episode_num = i + 1
        
        try:
            await graphiti.add_episode(
                name=ep['name'],
                episode_body=ep['content'],
                source=ep['type'],
                source_description=ep['description'],
                reference_time=datetime.now(timezone.utc),
            )
            logger.info(f'Ingested episode {episode_num}/{total}: {ep["name"]}')
        except Exception as e:
            logger.error(f'Failed episode {episode_num}/{total} ({ep["name"]}): {e}')
            failed_episodes.append(ep['name'])
            await asyncio.sleep(delay_seconds)
        
        # Wait before next episode
        if episode_num < total:
            logger.info(f'Waiting {delay_seconds} seconds...')
            await asyncio.sleep(delay_seconds)
    
    if failed_episodes:
        logger.warning(f'Failed episodes: {len(failed_episodes)}')


async def main():
    # Neo4j connection configuration
    neo4j_uri = 'bolt://neo4j:7687'
    neo4j_user = 'neo4j'
    neo4j_password = 'password123'

    # Configure Graphiti with Neo4j + OpenAI LLM + OpenAI embeddings/reranking
    graphiti = Graphiti(
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password,
        llm_client=OpenAIClient(
            config=LLMConfig(
                api_key=os.environ.get('OPENAI_API_KEY'),
                model="gpt-4o-mini",
                small_model="gpt-4o-mini"
            )
        ),
        embedder=OpenAIEmbedder(
            config=OpenAIEmbedderConfig(
                api_key=os.environ.get('OPENAI_API_KEY'),
                embedding_model="text-embedding-3-small"
            )
        ),
        cross_encoder=OpenAIRerankerClient(
            config=LLMConfig(
                api_key=os.environ.get('OPENAI_API_KEY'),
                model="gpt-4o-mini"
            )
        )
    )

    try:
        # Clear existing data from the database
        logger.info('Clearing existing data...')
        await clear_data(graphiti.driver)
        
        # Initialize the graph database with graphiti's indices
        logger.info('Building indices and constraints...')
        await graphiti.build_indices_and_constraints()
        
        # Load all episodes from clean chunks
        logger.info(f'Loading episodes from {CLEAN_CHUNKS_DIR}')
        all_episodes = []
        
        for file_path in sorted(CLEAN_CHUNKS_DIR.glob('*.json')):
            logger.info(f'Loading {file_path.name}')
            episodes = load_episodes_from_file(file_path)
            all_episodes.extend(episodes)
        
        logger.info(f'Total episodes to ingest: {len(all_episodes)}')
        
        # Ingest episodes one at a time with 20 second delay
        await ingest_episodes(graphiti, all_episodes, delay_seconds=15)
        
        logger.info('Ingestion complete!')
        
    finally:
        await graphiti.close()
        logger.info('Connection closed')


if __name__ == '__main__':
    asyncio.run(main())
