"""
Stacking albums and playlists on Playlists & Albums (Ben, 24 Nov 2026: "stack albums and playlists in the same way"
as Search's artists). The stack plays as one list: Play Ordered gives them back to back in the order added, each in
its own order, Shuffled mixes the lot; a track on two of them plays once. Embellish takes the stack as one playlist,
with the amounts only (an album's With Their Hits is for an album on its own). Each goes on the recent list, the
first added at the top, and Save offers the stack's names.
"""

from test_embellish_albums import abbey_road


def road_trip(app):
    found = next(x for x in app.jriver.playlists if x["ID"] == "202")
    return {"ID": "202", "Name": "Road Trip", "Folder": "Mixes", "Type": "Playlist"}, found["keys"]


def test_play_ordered_plays_them_back_to_back_each_in_its_own_order(app):
    import embellish
    import engine
    album = abbey_road(app)
    playlist, keys = road_trip(app)
    stack = embellish.make_stack([album, playlist])
    assert stack["Name"] == "Abbey Road and Road Trip"
    r = app.Lines()
    embellish.play(stack, "ordered", r)
    z = app.jriver.zone("Speakers").playlist
    want = album["keys"] + [k for k in keys if k not in album["keys"]]
    assert z == want, r.text()
    assert r.has(f"Play: Abbey Road and Road Trip, {len(want)} tracks, in order."), r.text()
    assert engine.SAVE_NAME == "Abbey Road and Road Trip", "Save offers the stack's names"
    assert [x.get("name") for x in embellish.recent()[:2]] == ["Abbey Road", "Road Trip"], "each on the recent list"


def test_shuffled_mixes_the_lot_and_a_track_twice_plays_once(app):
    import embellish
    album = abbey_road(app)
    playlist, keys = road_trip(app)
    twice = dict(album)   # the album added again in another guise: its tracks once
    stack = embellish.make_stack([album, playlist, twice])
    embellish.play(stack, "shuffled", app.Lines())
    z = app.jriver.zone("Speakers").playlist
    assert sorted(z) == sorted(set(album["keys"]) | set(keys)) and len(z) == len(set(z))


def test_embellish_takes_the_stack_as_one_playlist_and_never_their_hits(app):
    import embellish
    album = abbey_road(app)
    playlist, keys = road_trip(app)
    stack = embellish.make_stack([album, playlist])
    r = app.Lines()
    embellish.embellish(stack, "ordered", "with_hits", r)   # an album's own option asked of a stack: the default amount
    assert r.has("Embellish: Abbey Road and Road Trip,"), r.text()
    assert not r.has("With Their Hits"), r.text()
    z = app.jriver.zone("Speakers").playlist
    assert set(album["keys"]) | set(keys) <= set(z), "every track of both, with new ones woven in"


def test_all_albums_keeps_the_albums_order_choice(app):
    import embellish
    album = abbey_road(app)
    playlist, _keys = road_trip(app)
    assert embellish.all_albums(album) and embellish.all_albums(embellish.make_stack([album, dict(album, Name="Help!")]))
    assert not embellish.all_albums(embellish.make_stack([album, playlist])) and not embellish.all_albums(playlist)
    assert embellish.make_stack([album, playlist, album, playlist])["Name"] == "Abbey Road, Road Trip and 2 more"
