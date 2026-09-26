"""Unit tests for validation.py: the search page's query string -> canonical filters, or a list of problems."""
import pytest

from validation import QUERY_PARAMS, QueryError, process_search_query, validate_search_query


def test_none_blank_and_empty_are_valid():
    assert process_search_query(None) == {}
    assert process_search_query({}) == {}
    assert process_search_query({"sex": "", "age": None, "race": "   ", "drug": ["", " "]}) == {}   # empty form fields
    assert QUERY_PARAMS == ("sex", "age", "race", "drug", "condition")


def test_values_are_canonicalized():
    assert process_search_query({"sex": "F", "age": "67", "race": "black"}) == {"sex": "F", "age": 67, "race": "black"}
    assert process_search_query({"SEX": " Female ", "Age": 67, "race": "Black or African American"}) == \
        {"sex": "F", "age": 67, "race": "black"}
    assert process_search_query({"sex": "male"})["sex"] == "M"
    assert process_search_query({"sex": "both"})["sex"] == "MF"
    assert process_search_query({"race": "Not Hispanic or Latino"})["race"] == "not_hispanic"
    assert process_search_query({"race": "not_hispanic"})["race"] == "not_hispanic"
    assert process_search_query({"race": "White, non-Hispanic"})["race"] == "white"            # CDC spelling
    assert process_search_query({"race": "American Indian or Alaska Native"})["race"] == "aian"
    assert process_search_query({"race": "Native Hawaiian or Other Pacific Islander"})["race"] == "nhpi"
    assert process_search_query({"race": "Latino"})["race"] == "hispanic"
    assert process_search_query({"drug": "  Zolpidem   10 mg ", "condition": "insomnia"}) == \
        {"drug": "Zolpidem 10 mg", "condition": "insomnia"}
    assert list(process_search_query({"race": "asian", "drug": "x", "sex": "m"})) == ["sex", "race", "drug"]


def test_rejects_unknown_keys_and_bad_values():
    with pytest.raises(QueryError) as exc:
        process_search_query({"income": "$32", "sex": "D", "age": "old", "race": "martian"})
    assert exc.value.errors == [
        "unknown parameter 'income' (allowed: sex, age, race, drug, condition)",
        "sex must be one of M, F, MF (got 'D')",
        "age must be a whole number of years (got 'old')",
        "race must be one of white, black, asian, aian, nhpi, multiracial, hispanic, not_hispanic, other, unknown "
        "(got 'martian')",
    ]
    assert str(exc.value) == "; ".join(exc.value.errors) and exc.value.status_code == 400
    assert isinstance(exc.value, ValueError)
    assert validate_search_query({"age": "-1"})[1] == ["age must be between 0 and 120 (got -1)"]
    assert validate_search_query({"age": "121"})[1] == ["age must be between 0 and 120 (got 121)"]
    assert validate_search_query({"age": "67.5"})[1] == ["age must be a whole number of years (got '67.5')"]
    assert validate_search_query({"drug": "x" * 201})[1] == ["drug must be at most 200 characters (got 201)"]
    clean, errors = validate_search_query({"sex": "F", "colour": "red"})        # non-raising form keeps the good part
    assert clean == {"sex": "F"} and errors == ["unknown parameter 'colour' (allowed: sex, age, race, drug, condition)"]
    with pytest.raises(TypeError):
        process_search_query("sex=F")


def test_repeated_parameters():
    as_lists = {"sex": ["F", "female"], "race": ["black", "black"]}             # request.args.to_dict(flat=False)
    assert process_search_query(as_lists) == {"sex": "F", "race": "black"}     # same answer twice is fine
    assert validate_search_query({"sex": ["F", "M"]})[1] == ["sex was given 2 different values (F, M); give it once"]
    assert validate_search_query({"age": ("67", "68")})[1] == ["age was given 2 different values (67, 68); give it once"]
    assert validate_search_query({"sex": ["F", "D"]})[1] == ["sex must be one of M, F, MF (got 'D')"]


def test_flask_request_args():
    flask = pytest.importorskip("flask")
    app = flask.Flask(__name__)
    expected = {"sex": "F", "age": 67, "race": "black", "drug": "zolpidem"}
    with app.test_request_context("/search?sex=f&age=67&race=black&race=Black&drug=zolpidem&age="):
        assert process_search_query(flask.request.args) == expected
        assert process_search_query(flask.request.args.to_dict()) == expected
        assert process_search_query(flask.request.args.to_dict(flat=False)) == expected
    with app.test_request_context("/search?income=32&sex=D"):
        with pytest.raises(QueryError) as exc:
            process_search_query(flask.request.args)
        assert len(exc.value.errors) == 2
