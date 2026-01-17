import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from graphiti_core import Graphiti
from graphiti_core.driver.neo4j_driver import Neo4jDriver
from graphiti_core.llm_client.openai_client import OpenAIClient, LLMConfig
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from graphiti_core.nodes import EpisodeType
from graphiti_core.utils.maintenance.graph_data_operations import clear_data

load_dotenv()

# Set semaphore limit for concurrency control
os.environ['SEMAPHORE_LIMIT'] = '3'

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


async def add_episode_with_retry(
    graphiti: Graphiti,
    ep: dict,
    episode_num: int,
    total: int,
    max_retries: int = 5,
    base_delay: float = 2.0,
):
    """Add a single episode with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            await graphiti.add_episode(
                name=ep['name'],
                episode_body=ep['content'],
                source=ep['type'],
                source_description=ep['description'],
                reference_time=datetime.now(timezone.utc),
            )
            logger.info(f'Ingested episode {episode_num}/{total}: {ep["name"]}')
            return True
        except Exception as e:
            delay = base_delay * (2 ** attempt)  # Exponential backoff: 2, 4, 8, 16, 32 seconds
            if attempt < max_retries - 1:
                logger.warning(
                    f'Episode {episode_num}/{total} ({ep["name"]}) failed (attempt {attempt + 1}/{max_retries}): {e}. '
                    f'Retrying in {delay:.1f}s...'
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    f'Episode {episode_num}/{total} ({ep["name"]}) failed after {max_retries} attempts: {e}'
                )
                return False
    return False


async def ingest_episodes(
    graphiti: Graphiti,
    episodes: list[dict],
    concurrency: int = 3,
    base_delay: float = 2.0,
    max_retries: int = 5,
):
    """Ingest episodes concurrently with exponential backoff retry."""
    total = len(episodes)
    semaphore = asyncio.Semaphore(concurrency)
    failed_episodes = []
    
    async def process_episode(ep: dict, episode_num: int):
        async with semaphore:
            success = await add_episode_with_retry(
                graphiti, ep, episode_num, total, max_retries, base_delay
            )
            if not success:
                failed_episodes.append(ep['name'])
    
    # Create tasks for all episodes
    tasks = [
        process_episode(ep, i + 1)
        for i, ep in enumerate(episodes)
    ]
    
    # Run all tasks concurrently (limited by semaphore)
    await asyncio.gather(*tasks)
    
    if failed_episodes:
        logger.warning(f'Failed episodes ({len(failed_episodes)}): {failed_episodes}')


async def main():
    # Neo4j connection via driver
    neo4j_driver = Neo4jDriver(
        uri='bolt://neo4j:7687',
        user='neo4j',
        password='password123'
    )

    # Configure Graphiti with Neo4j + OpenAI LLM + OpenAI embeddings/reranking
    graphiti = Graphiti(
        graph_driver=neo4j_driver,
        llm_client=OpenAIClient(
            config=LLMConfig(
                api_key=os.environ.get('OPENAI_API_KEY'),
                model="gpt-5-mini",
                small_model="gpt-5-nano"
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
                model="gpt-5-nano"
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
        
        # Ingest episodes concurrently with exponential backoff
        await ingest_episodes(
            graphiti,
            all_episodes,
            concurrency=3,      # Process 3 episodes at a time
            base_delay=2.0,     # Start retry delay at 2 seconds
            max_retries=5,      # Max 5 retries per episode
        )
        
        logger.info('Ingestion complete!')
        
    finally:
        await graphiti.close()
        logger.info('Connection closed')


if __name__ == '__main__':
    asyncio.run(main())
