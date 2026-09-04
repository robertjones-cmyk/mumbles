from mumbles.history import History


def test_records_and_reads_back(sandbox):
    history = History()
    history.add("first", raw_text="furst", mode="clean", engine="mlx",
                audio_secs=2.0, proc_secs=0.4)
    history.add("second", mode="email")
    entries = history.recent()
    assert [e.text for e in entries] == ["second", "first"]
    assert entries[1].raw_text == "furst"
    assert entries[1].engine == "mlx"
    assert entries[0].words == 1


def test_limit_evicts_the_oldest(sandbox):
    history = History(limit=3)
    for index in range(6):
        history.add(f"entry {index}")
    assert [e.text for e in history.recent()] == ["entry 5", "entry 4", "entry 3"]


def test_search_and_stats(sandbox):
    history = History()
    history.add("buy milk", audio_secs=1.0)
    history.add("call the bank", audio_secs=3.0)
    assert [e.text for e in history.search("milk")] == ["buy milk"]
    assert history.search("nothing here") == []
    stats = history.stats()
    assert stats == {"entries": 2, "audio_seconds": 4.0, "words": 5}


def test_clear(sandbox):
    history = History()
    history.add("a")
    history.add("b")
    assert history.clear() == 2
    assert history.recent() == []


def test_reopening_an_existing_database_is_safe(sandbox):
    History().add("kept")
    assert [e.text for e in History().recent()] == ["kept"]
