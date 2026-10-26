"""Bounded Russian noun suggestions; never silently changes a player's move."""
from core.word_chain import BY_LETTER, COMMON_WORDS, SUGGESTION_LIMIT, WORD_RE, WORDS, normalize

ALPHABET = "абвгдежзийклмнопрстуфхцчшщъыьэюя"
MAX_DISTANCE = 2


def _distance(a: str, b: str) -> int:
    """Restricted Damerau distance with a two-edit bound and early exit."""
    if abs(len(a)-len(b)) > MAX_DISTANCE:
        return MAX_DISTANCE+1
    previous = list(range(len(b)+1))
    older = previous
    for i, left in enumerate(a, 1):
        current = [i]
        for j, right in enumerate(b, 1):
            cost = min(current[-1]+1, previous[j]+1, previous[j-1]+(left != right))
            if i > 1 and j > 1 and left == b[j-2] and a[i-2] == right:
                cost = min(cost, older[j-2]+1)
            current.append(cost)
        if min(current) > MAX_DISTANCE:
            return MAX_DISTANCE+1
        older, previous = previous, current
    return previous[-1]


def suggest(value: str, letter: str, used: set[str]) -> list[str]:
    word = normalize(value)
    if not WORD_RE.fullmatch(word) or word in WORDS:
        return []
    # A one-edit neighbourhood is cheap even for a large offline dictionary.
    splits = [(word[:i], word[i:]) for i in range(len(word)+1)]
    edits = {a+b[1:] for a,b in splits if b}
    edits |= {a+b[1]+b[0]+b[2:] for a,b in splits if len(b)>1}
    edits |= {a+c+b[1:] for a,b in splits if b for c in ALPHABET}
    edits |= {a+c+b for a,b in splits for c in ALPHABET}
    matches = {w:1 for w in edits if w.startswith(letter) and w in WORDS and w not in used}
    if len(matches) < SUGGESTION_LIMIT and len(word) >= 5:
        for candidate in BY_LETTER.get(letter, ()):
            if candidate in used or candidate in matches or abs(len(word)-len(candidate))>MAX_DISTANCE:
                continue
            distance = _distance(word, candidate)
            if distance <= MAX_DISTANCE:
                matches[candidate] = distance
    familiar = set(COMMON_WORDS)
    return sorted(matches, key=lambda w:(matches[w], w not in familiar, abs(len(w)-len(word)), w))[:SUGGESTION_LIMIT]
