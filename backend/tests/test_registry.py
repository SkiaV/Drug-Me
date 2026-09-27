import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import registry


def _trial(nct, mesh, interventions, n=100):
    return {"nct": nct, "mesh_drugs": mesh, "n_total": n,
            "interventions": [{"name": name, "arm_types": types, "other_names": other} for name, types, other in interventions]}


def test_double_dummy_comparator_is_excluded():
    # lemborexant vs zolpidem: the "zolpidem-matching placebo" sits in the EXPERIMENTAL arms. It is not zolpidem.
    t = _trial("NCT1", ["lemborexant", "zolpidem"],
               [("lemborexant", ["EXPERIMENTAL"], ["e2006"]),
                ("zolpidem tartrate", ["ACTIVE_COMPARATOR"], ["ambien cr"]),
                ("zolpidem-matching placebo", ["EXPERIMENTAL"], [])])
    used, comparator = registry.select_trials([t], "zolpidem")
    assert used == [] and [c["nct"] for c in comparator] == ["NCT1"] and comparator[0]["comparator_only"] is True
    used, comparator = registry.select_trials([t], "lemborexant")
    assert [u["nct"] for u in used] == ["NCT1"] and used[0]["comparator_only"] is False


def test_unknown_arm_types_keep_the_trial_until_an_alias_places_it():
    t = _trial("NCT2", ["zolpidem"], [("ambien", ["ACTIVE_COMPARATOR"], []), ("newdrug", ["EXPERIMENTAL"], [])])
    used, _ = registry.select_trials([t], "zolpidem")               # no intervention names zolpidem: unknown, kept
    assert len(used) == 1
    used, comparator = registry.select_trials([t], "zolpidem", aliases=["Ambien"])  # RxNorm brand resolves the arm
    assert used == [] and len(comparator) == 1


def test_registry_rows_require_the_mesh_term_but_typed_lookups_do_not():
    combo = _trial("NCT3", ["tramadol"], [("tramadol hcl/acetaminophen", ["EXPERIMENTAL"], [])])
    assert registry.select_trials([combo], "acetaminophen", require_mesh=True)[0] == []
    assert len(registry.select_trials([combo], "acetaminophen", require_mesh=False)[0]) == 1


def test_word_boundaries_and_case():
    t = _trial("NCT4", [], [("Environmental control", ["EXPERIMENTAL"], [])])
    assert registry.select_trials([t], "iron", require_mesh=False) == ([], [])
    t = _trial("NCT5", [], [("IRON sucrose 200 mg", ["EXPERIMENTAL"], [])])
    assert len(registry.select_trials([t], "iron", require_mesh=False)[0]) == 1


def test_duplicates_are_counted_once():
    t = _trial("NCT6", ["metformin"], [("metformin", ["EXPERIMENTAL"], [])])
    used, _ = registry.select_trials([t, dict(t)], "metformin")
    assert len(used) == 1


def test_slug_matches_dashboard_ids():
    assert registry.slug("F8 protein, human") == "f8-protein-human"
    assert registry.slug("Interleukin-2") == "interleukin-2"
