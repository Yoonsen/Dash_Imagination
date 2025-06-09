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
                "collection_name": collection_name,
                "limit": limit  # Add limit to the API request parameters
            }
            
            logger.info(f"Making request to {self.similar_endpoint} with params: {params}")
            response = requests.get(self.similar_endpoint, params=params)
            
            response.raise_for_status()
            
            results = response.json()
            logger.info(f"Found {len(results)} similar words")
            
            # Log the response status and content for debugging
            logger.info(f"Response status: {response.status_code}")
            logger.info(f"Response content: {response.text[:500]}")  # Log first 500 chars
            
            # Ensure results are in the correct format
            if not isinstance(results, list):
                logger.error(f"Unexpected response format: {type(results)}")
                return []
            
            # Convert results to list of tuples if needed
            formatted_results = []
            for result in results:
                if isinstance(result, dict) and 'word' in result and 'score' in result:
                    formatted_results.append((result['word'], float(result['score'])))
                elif isinstance(result, (list, tuple)) and len(result) == 2:
                    formatted_results.append((str(result[0]), float(result[1])))
                else:
                    logger.warning(f"Skipping malformed result: {result}")
            
            return formatted_results  # No need to slice here since API will return correct number
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error finding similar words: {str(e)}")
            if hasattr(e.response, 'text'):
                logger.error(f"Response content: {e.response.text}")
            return []
        except ValueError as e:
            logger.error(f"JSON parsing error: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error finding similar words: {str(e)}")
            return []

# Example usage:
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    api = WordSimilarityAPI()
    try:
        # Find words similar to "Paris"
        similar = api.find_similar_words("Paris", limit=5)
        print("\nSimilar words to 'Paris':")
        for word, score in similar:
            print(f"{word}: {score:.3f}")
    except Exception as e:
        print(f"Error: {str(e)}") 