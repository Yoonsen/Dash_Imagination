import requests
from typing import List, Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class WordSimilarityAPI:
    def __init__(self, base_url: str = "https://api.nb.no/dhlab/similarity"):
        """Initialize the WordSimilarityAPI with the base URL."""
        self.base_url = base_url.rstrip('/')
        self.similar_endpoint = f"{self.base_url}/sim_words"

    def find_similar_words(self, word: str, collection_name: str = "vss_1850_cos", limit: int = 20) -> List[Tuple[str, float]]:
        """
        Find words similar to the given word.
        
        Args:
            word: The reference word
            collection_name: The Qdrant collection name
            limit: Maximum number of results to return
            
        Returns:
            List of tuples containing (word, score) pairs
        """
        try:
            params = {
                "word": word,
                "collection_name": collection_name
            }
            
            response = requests.get(self.similar_endpoint, params=params)
            response.raise_for_status()
            
            results = response.json()
            return results[:limit]  # The API returns all results, we limit them here
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error finding similar words: {str(e)}")
            raise

# Example usage:
if __name__ == "__main__":
    api = WordSimilarityAPI()
    try:
        # Find words similar to "Paris"
        similar = api.find_similar_words("Paris", limit=5)
        print("\nSimilar words to 'Paris':")
        for word, score in similar:
            print(f"{word}: {score:.3f}")
    except Exception as e:
        print(f"Error: {str(e)}") 