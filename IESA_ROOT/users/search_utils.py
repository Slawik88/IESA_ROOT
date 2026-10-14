"""
Search utilities for highlighting matched text in results.
"""

import re

from django.utils.html import escape


def highlight_text(text, query):
    """
    Highlight matching substrings in text. Case-insensitive.
    Returns HTML with <mark> tags around matches.
    
    Args:
        text: The text to highlight
        query: The search query (can contain multiple words)
    
    Returns:
        HTML string with matches highlighted in <mark> tags
    """
    if not text or not query:
        return escape(text) if text else ""
    
    text = str(text)
    query = str(query).strip()
    
    # Match the original text once, then escape both matching and plain parts.
    # Searching escaped HTML can corrupt entities or match inserted <mark> tags.
    tokens = sorted(set(query.split()), key=len, reverse=True)
    if not tokens:
        return escape(text)
    pattern = re.compile('|'.join(re.escape(token) for token in tokens), re.IGNORECASE)
    parts = []
    end = 0
    for match in pattern.finditer(text):
        parts.extend((str(escape(text[end:match.start()])), f'<mark>{escape(match.group())}</mark>'))
        end = match.end()
    parts.append(str(escape(text[end:])))
    return ''.join(parts)


def normalize_search_query(query):
    """
    Normalize a search query: strip whitespace, remove special chars for matching.
    
    Args:
        query: Raw search query string
    
    Returns:
        Normalized query string
    """
    query = query.strip()
    # Remove leading @ symbol if present (often used for username search)
    if query.startswith('@'):
        query = query[1:].strip()
    return query
