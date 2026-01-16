import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.llm_client.groq_client import GroqClient, LLMConfig
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from graphiti_core.nodes import EpisodeType
from graphiti_core.utils.maintenance.graph_data_operations import clear_data


@dataclass
class RawEpisode:
    name: str
    content: str
    source: EpisodeType
    source_description: str
    reference_time: datetime
    uuid: str | None = None

load_dotenv()

# Set semaphore limit for concurrency control
os.environ['SEMAPHORE_LIMIT'] = '5'

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


async def ingest_episodes_batch(graphiti: Graphiti, episodes: list[dict], batch_size: int = 5):
    """Ingest episodes in batches."""
    total = len(episodes)
    failed_batches = []
    
    for i in range(0, total, batch_size):
        batch = episodes[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size
        
        # Prepare bulk episodes using RawEpisode objects
        bulk_episodes = [
            RawEpisode(
                name=ep['name'],
                content=ep['content'],
                source=ep['type'],
                source_description=ep['description'],
                reference_time=datetime.now(timezone.utc),
            )
            for ep in batch
        ]
        
        try:
            # Bulk add episodes
            await graphiti.add_episode_bulk(bulk_episodes)
            logger.info(f'Ingested batch {batch_num}/{total_batches} ({len(batch)} episodes)')
        except Exception as e:
            logger.error(f'Failed batch {batch_num}/{total_batches}: {e}')
            failed_batches.append(batch_num)
            continue
    
    if failed_batches:
        logger.warning(f'Failed batches: {failed_batches}')


async def main():
    # FalkorDB connection
    falkor_driver = FalkorDriver(
        host=os.environ.get('FALKORDB_HOST', 'localhost'),
        port=os.environ.get('FALKORDB_PORT', '6379'),
        username=os.environ.get('FALKORDB_USERNAME', None),
        password=os.environ.get('FALKORDB_PASSWORD', None)
    )

    # Configure Graphiti with FalkorDB + Groq LLM + OpenAI embeddings/reranking
    graphiti = Graphiti(
        graph_driver=falkor_driver,
        llm_client=GroqClient(
            config=LLMConfig(
                api_key=os.environ.get('GROQ_API_KEY'),
                model="llama-3.1-8b-instant",
                small_model="llama-3.1-8b-instant"
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
                model="gpt-4.1-nano"
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
        
        # Ingest episodes in batches of 5
        await ingest_episodes_batch(graphiti, all_episodes, batch_size=5)
        
        logger.info('Ingestion complete!')
        
    finally:
        await graphiti.close()
        logger.info('Connection closed')


if __name__ == '__main__':
    asyncio.run(main())
