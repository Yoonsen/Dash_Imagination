# Global state management for the application

from typing import List, Tuple, Optional, Set
import pandas as pd

class CorpusState:
    def __init__(self):
        self._books: Set[int] = set()  # dhlabids
        self._places: Set[str] = set()  # place tokens
    
    def update_from_books(self, new_books: List[int], new_places: List[str]) -> Tuple[List[int], List[str]]:
        """Update state from a books-first flow. 
        If either new_books or new_places is empty, it's treated as a reset."""
        if not new_books or not new_places:
            # Reset state
            self._books = set(new_books)
            self._places = set(new_places)
        elif not self._books and not self._places:
            # Initial state, just set both
            self._books = set(new_books)
            self._places = set(new_places)
        else:
            # Enforce intersection
            self._books = self._books.intersection(set(new_books))
            self._places = self._places.intersection(set(new_places))
        
        return list(self._books), list(self._places)
    
    def update_from_places(self, new_places: List[str], new_books: List[int]) -> Tuple[List[int], List[str]]:
        """Update state from a places-first flow.
        If either new_places or new_books is empty, it's treated as a reset."""
        if not new_places or not new_books:
            # Reset state
            self._books = set(new_books)
            self._places = set(new_places)
        elif not self._books and not self._places:
            # Initial state, just set both
            self._books = set(new_books)
            self._places = set(new_places)
        else:
            # Enforce intersection
            self._books = self._books.intersection(set(new_books))
            self._places = self._places.intersection(set(new_places))
        
        return list(self._books), list(self._places)
    
    def get_current_state(self) -> Tuple[List[int], List[str]]:
        """Get the current state as a tuple of (books, places)."""
        return list(self._books), list(self._places)
    
    def clear(self):
        """Clear the current state."""
        self._books.clear()
        self._places.clear()

# Global instance
corpus_state = CorpusState()

def update_from_books(new_books: List[int], new_places: List[str]) -> Tuple[List[int], List[str]]:
    """Update the global state from a books-first flow."""
    return corpus_state.update_from_books(new_books, new_places)

def update_from_places(new_places: List[str], new_books: List[int]) -> Tuple[List[int], List[str]]:
    """Update the global state from a places-first flow."""
    return corpus_state.update_from_places(new_places, new_books)

def get_current_state() -> Tuple[List[int], List[str]]:
    """Get the current state."""
    return corpus_state.get_current_state()

def clear_state():
    """Clear the current state."""
    corpus_state.clear() 