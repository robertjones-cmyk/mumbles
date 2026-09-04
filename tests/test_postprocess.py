from mumbles import postprocess as pp


def test_strips_whisper_event_tags():
    assert "BLANK_AUDIO" not in pp.strip_artifacts("hello [BLANK_AUDIO] world")
    assert "MUSIC" not in pp.strip_artifacts("(MUSIC) hi")
    assert pp.clean("hello [BLANK_AUDIO] world") == "Hello world"


def test_removes_standalone_fillers_only():
    assert "um" not in pp.remove_fillers("um hello there")
    # "umbrella" starts with "um" and must survive.
    assert "umbrella" in pp.remove_fillers("the umbrella is uh blue")


def test_filler_removal_eats_its_surrounding_commas():
    assert pp.clean("i, uh, went home") == "I went home"


def test_collapses_function_word_stutters():
    assert pp.collapse_stutters("the the cat") == "the cat"
    assert pp.collapse_stutters("i i i think") == "i think"
    # Content words can legitimately repeat.
    assert pp.collapse_stutters("very very good") == "very very good"


def test_replacements_are_whole_phrase_and_case_aware():
    reps = {"get hub": "GitHub"}
    assert pp.apply_replacements("push to get hub", reps) == "push to GitHub"
    assert pp.apply_replacements("GET HUB", reps) == "GITHUB"
    # No partial-word matches.
    assert pp.apply_replacements("forget hubcaps", reps) == "forget hubcaps"


def test_longest_replacement_wins():
    reps = {"code": "Code", "vs code": "VS Code"}
    assert pp.apply_replacements("open vs code", reps) == "open VS Code"


def test_tidy_whitespace_fixes_punctuation_spacing():
    assert pp.tidy_whitespace("hello , world .") == "hello, world."
    assert pp.tidy_whitespace("a  \n\n\n  b") == "a\n\nb"


def test_capitalizes_sentences_and_pronoun_i():
    assert pp.clean("hello there. how are you") == "Hello there. How are you"
    assert pp.clean("i said i would") == "I said I would"
    # Contractions and words containing "i" are untouched.
    assert pp.clean("it is inside", drop_fillers=False) == "It is inside"


def test_clean_handles_empty_and_noise_only_input():
    assert pp.clean("") == ""
    assert pp.clean("[BLANK_AUDIO]") == ""
    assert not pp.is_meaningful("[BLANK_AUDIO]")
    assert not pp.is_meaningful("...")
    assert pp.is_meaningful("hi")


def test_full_pipeline():
    text = "um so i, uh, went to the the store [BLANK_AUDIO] and pushed to get hub ."
    assert pp.clean(text, {"get hub": "GitHub"}) == \
        "So I went to the store and pushed to GitHub."


def test_raw_mode_keeps_fillers():
    assert "um" in pp.clean("um hello", drop_fillers=False).lower()
