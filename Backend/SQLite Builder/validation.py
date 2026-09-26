"""Validate the search page's query string before it reaches the database.

Usage in main.py:

    from validation import QueryError, process_search_query

    @app.route('/search')
    def search():
        try:
            params = process_search_query(request.args)
        except QueryError as exc:
            return jsonify({"error": {"code": "bad_request", "message": str(exc), "details": exc.errors}}), 400
        # params is e.g. {"sex": "F", "age": 67, "race": "black", "drug": "zolpidem"}; only the keys that were given.

Two checks, both driven by the PARSERS table at the bottom:
  1. every key must be one we query on ({"income": "$32"} is rejected, so is {"sex": "D", "colour": "red"});
  2. every value must be one we can put in a WHERE clause: sex is M, F or MF (the studies.sex values in the schema),
     age is a whole number of years, race is one of the harmonized study_races.category buckets,
     drug and condition are free text.
Values are canonicalized ("Female" -> "F", "Black or African American" -> "black", "67" -> 67). Blank values count
as "not given", so an HTML form with empty selects still validates. Every problem is reported, not just the first.

Accepts flask's request.args as-is, request.args.to_dict(), request.args.to_dict(flat=False) or any plain dict.
No dependencies beyond the standard library.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

# ----------------------------------------------------------------------------- vocabularies

SEX_VALUES = ("M", "F", "MF")                                        # canonical, as stored in studies.sex
_SEX_ALIASES = {
    "m": "M", "male": "M", "man": "M", "men": "M",
    "f": "F", "female": "F", "woman": "F", "women": "F",
    "mf": "MF", "fm": "MF", "both": "MF", "all": "MF", "any": "MF", "male and female": "MF", "female and male": "MF",
}

RACE_CATEGORIES = ("white", "black", "asian", "aian", "nhpi", "multiracial",
                   "hispanic", "not_hispanic", "other", "unknown")   # canonical, as stored in study_races.category
# Keys are spelled the way _normalize() spells them: lower case, one space between words, no punctuation.
# Covers the NIH/OMB labels, the CDC "White, non-Hispanic" style and the usual short forms.
_RACE_ALIASES = {
    "white": "white", "caucasian": "white", "european": "white", "white non hispanic": "white",
    "black": "black", "african american": "black", "black or african american": "black", "african": "black",
    "black non hispanic": "black",
    "asian": "asian", "asian non hispanic": "asian",
    "aian": "aian", "american indian": "aian", "alaska native": "aian", "american indian or alaska native": "aian",
    "native american": "aian", "indigenous": "aian", "american indian or alaska native non hispanic": "aian",
    "nhpi": "nhpi", "native hawaiian": "nhpi", "hawaiian": "nhpi", "pacific islander": "nhpi",
    "native hawaiian or pacific islander": "nhpi", "native hawaiian or other pacific islander": "nhpi",
    "native hawaiian or other pacific islander non hispanic": "nhpi",
    "multiracial": "multiracial", "multi": "multiracial", "mixed": "multiracial", "multiple": "multiracial",
    "two or more": "multiracial", "two or more races": "multiracial", "more than one race": "multiracial",
    "multiracial non hispanic": "multiracial",
    "hispanic": "hispanic", "latino": "hispanic", "latina": "hispanic", "latinx": "hispanic",
    "hispanic or latino": "hispanic", "hispanic latino": "hispanic",
    "not hispanic": "not_hispanic", "non hispanic": "not_hispanic", "not hispanic or latino": "not_hispanic",
    "not latino": "not_hispanic", "non latino": "not_hispanic",
    "other": "other", "other race": "other", "some other race": "other",
    "unknown": "unknown", "not reported": "unknown", "not stated": "unknown", "prefer not to say": "unknown",
    "declined": "unknown",
}

AGE_MIN, AGE_MAX = 0, 120                                            # years; the store caps study ranges at 100
TEXT_MAX_LENGTH = 200                                                # drug / condition


class QueryError(ValueError):
    """Raised by process_search_query. `errors` holds one message per problem; str(exc) joins them with "; "."""

    status_code = 400

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = list(errors)


# ----------------------------------------------------------------------------- one parser per parameter
# Each takes the stripped text the client sent and returns the canonical value, or raises ValueError with a
# message that reads well after the parameter name ("sex must be ...").


def _normalize(value: str) -> str:
    """'Not_Hispanic', 'not hispanic', 'Non-Hispanic/Latino' -> 'not hispanic', 'not hispanic', 'non hispanic latino'."""
    return re.sub(r"[\s,_/\-]+", " ", value.lower()).strip()


def _parse_sex(value: str) -> str:
    try:
        return _SEX_ALIASES[_normalize(value)]
    except KeyError:
        raise ValueError(f"must be one of {', '.join(SEX_VALUES)} (got '{value}')") from None


def _parse_age(value: str) -> int:
    try:
        age = int(value)
    except ValueError:
        raise ValueError(f"must be a whole number of years (got '{value}')") from None
    if not AGE_MIN <= age <= AGE_MAX:
        raise ValueError(f"must be between {AGE_MIN} and {AGE_MAX} (got {age})")
    return age


def _parse_race(value: str) -> str:
    try:
        return _RACE_ALIASES[_normalize(value)]
    except KeyError:
        raise ValueError(f"must be one of {', '.join(RACE_CATEGORIES)} (got '{value}')") from None


def _parse_text(value: str) -> str:
    text = " ".join(value.split())                                   # collapse inner whitespace
    if len(text) > TEXT_MAX_LENGTH:
        raise ValueError(f"must be at most {TEXT_MAX_LENGTH} characters (got {len(text)})")
    return text


PARSERS = {
    "sex": _parse_sex,
    "age": _parse_age,
    "race": _parse_race,
    "drug": _parse_text,
    "condition": _parse_text,
}
QUERY_PARAMS = tuple(PARSERS)                                        # the only keys a search may carry


# ----------------------------------------------------------------------------- entry points


def _as_lists(query) -> dict:
    """Whatever the caller had -> {key: [raw values]}. Handles flask's request.args (a MultiDict, where a repeated
    key has several values), the two shapes of its .to_dict(), and a plain dict."""
    if query is None:
        return {}
    if hasattr(query, "getlist"):                                    # werkzeug MultiDict
        return {key: query.getlist(key) for key in query}
    if not isinstance(query, Mapping):
        raise TypeError(f"query must be a mapping, not {type(query).__name__}")
    return {key: list(value) if isinstance(value, (list, tuple, set)) else [value] for key, value in query.items()}


def validate_search_query(query) -> tuple[dict, list[str]]:
    """The non-raising form: (canonical params, list of problems). Both are filled in; a caller that wants to
    ignore bad parameters instead of failing the request can use the first and log the second."""
    errors: list[str] = []
    given: dict[str, list[str]] = {}                                 # normalized key -> distinct non-blank texts
    for raw_key, raw_values in _as_lists(query).items():
        key = str(raw_key).strip().lower()
        if key not in PARSERS:
            errors.append(f"unknown parameter '{raw_key}' (allowed: {', '.join(QUERY_PARAMS)})")
            continue
        for raw in raw_values:
            text = "" if raw is None else str(raw).strip()
            if text:                                                 # blank means "not given"
                bucket = given.setdefault(key, [])
                if text not in bucket:
                    bucket.append(text)

    clean: dict = {}
    for key, parse in PARSERS.items():                               # table order, so the output is predictable
        canonical: list = []
        for text in given.get(key, ()):
            try:
                value = parse(text)
            except ValueError as exc:
                errors.append(f"{key} {exc}")
                continue
            if value not in canonical:                               # "F" and "female" are the same answer
                canonical.append(value)
        if len(canonical) > 1:
            errors.append(f"{key} was given {len(canonical)} different values "
                          f"({', '.join(str(v) for v in canonical)}); give it once")
        elif canonical:
            clean[key] = canonical[0]
    return clean, errors


def process_search_query(query) -> dict:
    """Canonical search parameters, or QueryError listing every problem.

    Only the parameters that were given come back, e.g. {"sex": "F", "age": 67, "race": "black"};
    None or an empty query is fine and returns {}.
    """
    clean, errors = validate_search_query(query)
    if errors:
        raise QueryError(errors)
    return clean
