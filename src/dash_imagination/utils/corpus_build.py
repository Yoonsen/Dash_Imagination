# Corpus Building Module
# This module provides functionality for building and managing corpora in the Dash Imagination app

from typing import List, Tuple, Optional, Set, Dict
import pandas as pd
import dhlab as dh
from .db import get_db_connection

class CorpusBuilder:
    """A class for building and managing corpora of books and their metadata."""
    
    def __init__(self):
        """Initialize the corpus builder with empty state."""
        self._db_conn = None
        self._dhlabids: Set[int] = set()
        self._books_df = None
        self._places_df = None
    
    def _get_db_connection(self):
        """Get database connection if not already established."""
        if self._db_conn is None:
            self._db_conn = get_db_connection()
        return self._db_conn
    
    def _fetch_book_metadata(self) -> pd.DataFrame:
        """Fetch book metadata from the database."""
        conn = self._get_db_connection()
        query = """
        SELECT dhlabid, urn, author, category, year
        FROM corpus
        """
        return pd.read_sql_query(query, conn)
    
    def _fetch_places_data(self) -> pd.DataFrame:
        """Fetch places data from the database."""
        conn = self._get_db_connection()
        query = """
        SELECT DISTINCT dhlabid, token as place_token
        FROM books
        """
        return pd.read_sql_query(query, conn)
    
    def build_corpus(self, dhlabids: Optional[List[int]] = None, 
                    category: Optional[str] = None, 
                    year_range: Optional[Tuple[int, int]] = None, 
                    author: Optional[str] = None) -> List[int]:
        """Build the corpus as a list of dhlabids with optional filters.
        
        Args:
            dhlabids: Optional list of DHLab IDs to filter the corpus
            category: Optional category to filter by
            year_range: Optional tuple of (start_year, end_year) to filter by
            author: Optional author to filter by
        
        Returns:
            List of dhlabids that make up the corpus
        """
        if self._books_df is None:
            self._books_df = self._fetch_book_metadata()
        
        filtered_df = self._books_df.copy()
        
        # Apply filters if provided
        if category:
            filtered_df = filtered_df[filtered_df['category'] == category]
        
        if year_range:
            start_year, end_year = year_range
            filtered_df = filtered_df[(filtered_df['year'] >= start_year) & 
                                    (filtered_df['year'] <= end_year)]
        
        if author:
            # Use case-insensitive substring match for author
            filtered_df = filtered_df[filtered_df['author'].str.contains(author, case=False, na=False)]
        
        if dhlabids:
            filtered_df = filtered_df[filtered_df['dhlabid'].isin(dhlabids)]
        
        self._dhlabids = set(filtered_df['dhlabid'].tolist())
        return list(self._dhlabids)
    
    def get_corpus_size(self) -> int:
        """Get the current size of the corpus."""
        return len(self._dhlabids)
    
    def get_corpus(self) -> List[int]:
        """Get the current corpus as a list of dhlabids."""
        return list(self._dhlabids)
    
    def get_metadata(self) -> pd.DataFrame:
        """Get the metadata for the current corpus."""
        if self._books_df is None:
            self._books_df = self._fetch_book_metadata()
        return self._books_df[self._books_df['dhlabid'].isin(self._dhlabids)]
    
    def get_places(self, max_places: Optional[int] = 2000) -> pd.DataFrame:
        """Get the places data for the current corpus, with optional sampling.
        
        Args:
            max_places: Maximum number of unique places to return. If None or 0, returns all places.
                      Places are sampled based on frequency (most frequent places are kept).
        """
        if self._places_df is None:
            self._places_df = self._fetch_places_data()
        
        # Get places for current corpus
        places_df = self._places_df[self._places_df['dhlabid'].isin(self._dhlabids)]
        
        if max_places and max_places > 0:
            # Count frequency of each place
            place_counts = places_df['place_token'].value_counts()
            # Keep only the top N most frequent places
            top_places = place_counts.head(max_places).index
            # Filter the dataframe to keep only these places
            places_df = places_df[places_df['place_token'].isin(top_places)]
        
        return places_df
    
    def get_corpus_stats(self, max_places: Optional[int] = 2000) -> Dict:
        """Get statistics about the current corpus."""
        metadata = self.get_metadata()
        places = self.get_places(max_places=max_places)
        
        # Count unique authors by splitting on '/'
        author_set = set()
        for author_str in metadata['author'].dropna():
            for author in str(author_str).split('/'):
                author = author.strip()
                if author:
                    author_set.add(author)

        return {
            'total_books': len(self._dhlabids),
            'unique_authors': len(author_set),
            'categories': metadata['category'].value_counts().to_dict(),
            'year_range': (metadata['year'].min(), metadata['year'].max()),
            'total_places': places['place_token'].nunique(),
            'sampled_from': self._places_df[self._places_df['dhlabid'].isin(self._dhlabids)]['place_token'].nunique() if self._places_df is not None else 0
        }

# Create a singleton instance
corpus_builder = CorpusBuilder()

def build_corpus(dhlabids: Optional[List[int]] = None, 
                category: Optional[str] = None, 
                year_range: Optional[Tuple[int, int]] = None, 
                author: Optional[str] = None) -> List[int]:
    """Global function to build the corpus."""
    return corpus_builder.build_corpus(dhlabids, category, year_range, author)

def get_corpus_size() -> int:
    """Get the current size of the corpus."""
    return corpus_builder.get_corpus_size()

def get_corpus() -> List[int]:
    """Get the current corpus as a list of dhlabids."""
    return corpus_builder.get_corpus()

def get_metadata() -> pd.DataFrame:
    """Get the metadata for the current corpus."""
    return corpus_builder.get_metadata()

def get_places() -> pd.DataFrame:
    """Get the places data for the current corpus."""
    return corpus_builder.get_places()

def get_corpus_stats(max_places: Optional[int] = 2000) -> Dict:
    """Get statistics about the current corpus."""
    return corpus_builder.get_corpus_stats(max_places=max_places)

# Add a wrapper for content word counts

def count_words(dhlabids: List[int], words: List[str]) -> pd.DataFrame:
    """
    Given a list of dhlabids and words, map dhlabids to urns and run dh.Counts.
    Returns the resulting DataFrame (words as rows, dhlabids as columns).
    """
    # Get the metadata DataFrame (with urns)
    metadata = corpus_builder._books_df
    if metadata is None:
        metadata = corpus_builder._fetch_book_metadata()
    # Map dhlabids to urns
    urns = metadata[metadata['dhlabid'].isin(dhlabids)]['urn'].dropna().tolist()
    if not urns:
        return pd.DataFrame()
    # Run DH Lab Counts
    import dhlab as dh
    counts_df = dh.Counts(urns, words).frame
    return counts_df 