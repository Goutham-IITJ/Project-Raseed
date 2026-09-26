"""Bounded lexical/topic relevance; no provider, embeddings, or identity selectors."""

import re

STOP_WORDS = frozenset(
    "a an and are as at be can could did do does for from have how i in is it me my of on or "
    "please show tell that the their them these they this to was we what when where which who "
    "will with would you your remember stored saved memory memories".split()
)
TOPIC_WORDS = {
    "food": frozenset(
        "food grocery groceries diet dietary dinner lunch breakfast meal meals eat "
        "vegan vegetarian allergy allergies gluten cooking cook recipe recipes".split()
    ),
    "spending": frozenset(
        "spend spending spent expense expenses money finance financial cost "
        "costs payment payments purchase purchases".split()
    ),
    "inventory": frozenset(
        "inventory stock pantry expiry expires expired remaining consume "
        "consumption household".split()
    ),
    "shopping": frozenset("shopping shop buy buying bought store merchant merchants".split()),
    "goals": frozenset("goal goals saving savings save target targets".split()),
}


def relevance(query: str) -> tuple[list[str], list[str]]:
    tokens = set(re.findall(r"[^\W_]+", query.casefold(), re.UNICODE)) - STOP_WORDS
    terms = sorted(token for token in tokens if 1 < len(token) <= 60)[:32]
    topics = sorted(topic for topic, words in TOPIC_WORDS.items() if tokens & words)
    return terms, topics
