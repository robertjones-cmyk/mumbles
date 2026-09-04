from mumbles.modes import Mode, builtin_modes, load_modes


def test_builtins_cover_offline_and_llm_paths():
    modes = builtin_modes()
    assert modes["raw"].uses_llm is False
    assert modes["clean"].uses_llm is False
    assert modes["polish"].uses_llm is True
    assert modes["raw"].remove_fillers is False
    assert modes["clean"].remove_fillers is True


def test_round_trip_through_dict():
    mode = Mode(name="x", llm="ollama", prompt="p", temperature=0.7)
    assert Mode.from_dict(mode.to_dict()) == mode


def test_from_dict_ignores_unknown_fields():
    mode = Mode.from_dict({"name": "x", "future_field": 1})
    assert mode.name == "x"


def test_load_modes_merges_over_builtins():
    modes = load_modes({"notes": {"llm": "none"}, "mine": {"prompt": "hi"}})
    assert modes["notes"].uses_llm is False
    assert modes["mine"].name == "mine"
    assert len(modes) == len(builtin_modes()) + 1


def test_load_modes_tolerates_garbage():
    modes = load_modes({"bad": "not-a-dict", "ok": {"llm": "none"}})
    assert "bad" not in modes or modes["bad"].name == "bad"
    assert "ok" in modes
