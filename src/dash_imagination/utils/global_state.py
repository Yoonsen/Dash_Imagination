# Global state management for the application

from typing import List, Tuple, Set

import pandas as pd

from dash_imagination.utils.db import get_db_connection

class CorpusState:
    def __init__(self):
        self._books: Set[int] = set()  # dhlabids
        self._places: Set[str] = set()  # place tokens
    
    def _refresh_places(self) -> None:
        """Synchronise the place-token set with the current books."""
        if not self._books:
            self._places.clear()
            return

        conn = get_db_connection()
        try:
            placeholders = ",".join(["?"] * len(self._books))
            query = f"""
                SELECT DISTINCT b.token
                FROM books b
                WHERE b.dhlabid IN ({placeholders})
                  AND b.token IS NOT NULL
            """
            df = pd.read_sql_query(query, conn, params=tuple(self._books))
            self._places = set(df["token"].dropna().tolist())
        finally:
            conn.close()

    def update_from_books(
        self,
        new_books: List[int],
        new_places: List[str],
        operation: str = "intersection",
    ) -> Tuple[List[int], List[str]]:
        """Update state from a books-first flow using the requested set operation."""
        op = (operation or "intersection").lower()
        incoming = set(new_books or [])

        if not self._books:
            if op == "difference":
                self._books.clear()
            else:
                self._books = incoming
        else:
            if op == "union":
                self._books |= incoming
            elif op == "difference":
                self._books -= incoming
            else:
                self._books &= incoming if incoming else set()

        self._refresh_places()
        return list(self._books), list(self._places)

    def update_from_places(
        self,
        new_places: List[str],
        new_books: List[int],
        operation: str = "intersection",
    ) -> Tuple[List[int], List[str]]:
        """Update state from a places-first flow using the requested set operation."""
        # Delegate to the books-first implementation since books remain the source of truth.
        return self.update_from_books(new_books, new_places, operation=operation)
    
    def get_current_state(self) -> Tuple[List[int], List[str]]:
        """Get the current state as a tuple of (books, places)."""
        return list(self._books), list(self._places)
    
    def clear(self):
        """Clear the current state."""
        self._books.clear()
        self._places.clear()

# Global instance
corpus_state = CorpusState()

def update_from_books(new_books: List[int], new_places: List[str], operation: str = "intersection") -> Tuple[List[int], List[str]]:
    """Update the global state from a books-first flow."""
    return corpus_state.update_from_books(new_books, new_places, operation=operation)

def update_from_places(new_places: List[str], new_books: List[int], operation: str = "intersection") -> Tuple[List[int], List[str]]:
    """Update the global state from a places-first flow."""
    return corpus_state.update_from_places(new_places, new_books, operation=operation)

def get_current_state() -> Tuple[List[int], List[str]]:
    """Get the current state."""
    return corpus_state.get_current_state()

def clear_state():
    """Clear the current state."""
    corpus_state.clear() 