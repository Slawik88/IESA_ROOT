"""
Search utilities for highlighting matched text in results.
"""

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
    
    # Escape the text first for HTML safety
    escaped_text = escape(text)
    
    # Split query into tokens and highlight each
    tokens = [t.strip() for t in query.split() if t.strip()]
    
    for token in tokens:
        # Case-insensitive highlighting
        escaped_token = escape(token)
        # Create a pattern that matches the token (case-insensitive)
        import re
        pattern = re.compile(re.escape(token), re.IGNORECASE)
        # Find all matches and replace with highlighted version
        def replace_match(match):
            return f"<mark>{escape(match.group(0))}</mark>"
        escaped_text = pattern.sub(replace_match, escaped_text)
    
    return escaped_text


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
