import espn_photos as ep

ROSTER = {"athletes": [{"position": "offense", "items": [
    {"id": "3918298", "fullName": "Josh Allen"}, {"id": "4361", "displayName": "Dup Name"}]},
    {"id": "9", "fullName": "Flat Guy"}]}


def test_parse_and_match(monkeypatch):
    rows = ep.parse_roster(ROSTER, "BUF")
    assert len(rows) == 3
    m = {}
    for n, t, e in rows:
        ep._add(m, n, t, e)
    monkeypatch.setattr(ep, "_get_map", lambda: m)
    assert ep.espn_photo("Josh Allen", "BUF").endswith("/3918298.png")
    assert ep.espn_photo("Nobody", "BUF") is None


def test_never_raises(monkeypatch):
    monkeypatch.setattr(ep, "_get_map", lambda: (_ for _ in ()).throw(RuntimeError()))
    assert ep.espn_photo("x") is None
