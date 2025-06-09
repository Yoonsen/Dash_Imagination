from .word_similarity import WordSimilarityAPI
import json

def test_api():
    api = WordSimilarityAPI()
    
    # Test search
    print("\nTesting word search:")
    print("-" * 50)
    try:
        results = api.search_words("krig", limit=5)
        print("Search results for 'krig':")
        print(json.dumps(results, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Search error: {str(e)}")
    
    # Test similar words
    print("\nTesting similar words:")
    print("-" * 50)
    try:
        similar = api.find_similar_words("slag", limit=5)
        print("Similar words to 'slag':")
        print(json.dumps(similar, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Similar words error: {str(e)}")

if __name__ == "__main__":
    test_api() 