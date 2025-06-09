import unittest
import pandas as pd
import sys
import os

# Add the src directory to the Python path
src_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src")
sys.path.insert(0, src_path)

from dash_imagination.utils.corpus_build import (
    build_corpus,
    get_corpus_size,
    get_corpus,
    get_metadata,
    get_places,
    get_corpus_stats
)

class TestCorpusBuilder(unittest.TestCase):
    def setUp(self):
        """Set up test cases."""
        # Build a test corpus with all books
        self.all_books = build_corpus()
        self.initial_size = len(self.all_books)
        
        # Test data
        self.test_category = "Fiksjon"  # Replace with actual category from your database
        self.test_year_range = (1800, 1850)
        self.test_author = "Ibsen"  # Replace with actual author from your database
    
    def test_build_corpus_all(self):
        """Test building corpus with no filters."""
        corpus = build_corpus()
        self.assertIsInstance(corpus, list)
        self.assertTrue(all(isinstance(x, int) for x in corpus))
        self.assertTrue(len(corpus) > 0)
    
    def test_build_corpus_category(self):
        """Test building corpus with category filter."""
        corpus = build_corpus(category=self.test_category)
        metadata = get_metadata()
        self.assertTrue(all(metadata['category'] == self.test_category))
    
    def test_build_corpus_year_range(self):
        """Test building corpus with year range filter."""
        corpus = build_corpus(year_range=self.test_year_range)
        metadata = get_metadata()
        self.assertTrue(all(
            (metadata['year'] >= self.test_year_range[0]) & 
            (metadata['year'] <= self.test_year_range[1])
        ))
    
    def test_build_corpus_author(self):
        """Test building corpus with author filter."""
        corpus = build_corpus(author=self.test_author)
        metadata = get_metadata()
        self.assertTrue(all(metadata['author'] == self.test_author))
    
    def test_get_metadata(self):
        """Test getting metadata for corpus."""
        metadata = get_metadata()
        self.assertIsInstance(metadata, pd.DataFrame)
        self.assertTrue('dhlabid' in metadata.columns)
        self.assertTrue('author' in metadata.columns)
        self.assertTrue('category' in metadata.columns)
        self.assertTrue('year' in metadata.columns)
    
    def test_get_places(self):
        """Test getting places data for corpus."""
        places = get_places()
        self.assertIsInstance(places, pd.DataFrame)
        self.assertTrue('dhlabid' in places.columns)
        self.assertTrue('place_token' in places.columns)
    
    def test_get_corpus_stats(self):
        """Test getting corpus statistics."""
        stats = get_corpus_stats()
        self.assertIsInstance(stats, dict)
        self.assertTrue('total_books' in stats)
        self.assertTrue('unique_authors' in stats)
        self.assertTrue('categories' in stats)
        self.assertTrue('year_range' in stats)
        self.assertTrue('total_places' in stats)
        
        # Verify stats values
        self.assertIsInstance(stats['total_books'], int)
        self.assertIsInstance(stats['unique_authors'], int)
        self.assertIsInstance(stats['categories'], dict)
        self.assertIsInstance(stats['year_range'], tuple)
        self.assertIsInstance(stats['total_places'], int)
    
    def test_corpus_size_consistency(self):
        """Test that corpus size is consistent across different methods."""
        corpus = get_corpus()
        size = get_corpus_size()
        metadata = get_metadata()
        stats = get_corpus_stats()
        
        self.assertEqual(len(corpus), size)
        self.assertEqual(len(metadata), size)
        self.assertEqual(stats['total_books'], size)

if __name__ == '__main__':
    unittest.main() 