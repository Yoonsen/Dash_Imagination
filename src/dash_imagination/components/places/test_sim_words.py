import requests

def test_sim_words():
    url = "https://api.nb.no/dhlab/similarity/sim_words"
    params = {
        "word": "Paris",
        "collection_name": "vss_1850_cos"
    }
    
    print("\nTesting similar words for 'Paris':")
    print("-" * 50)
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        results = response.json()
        
        print("\nResults:")
        for word, score in results:
            print(f"{word}: {score:.3f}")
            
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    test_sim_words() 