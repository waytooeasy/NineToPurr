"""9:16 layout choice (format research 2026-10-19). Pure: no OpenCV, no video."""
import layout as L


def test_no_faces_centres_the_crop():
    lay = L.choose_layout([], 1920, 1080)
    assert lay["mode"] == "crop" and lay["cx"] == 960


def test_big_face_left_of_centre_moves_the_crop_there():
    faces = [(600, 300, 260, 260)] * 5           # IRL / just chatting, face ~24 % of height
    lay = L.choose_layout(faces, 1920, 1080)
    assert lay["mode"] == "crop" and lay["cx"] == 730
    assert "crop=606:1080:426:0" in L.filtergraph(lay)


def test_crop_never_leaves_the_frame():
    lay = L.choose_layout([(1850, 300, 260, 260)], 1920, 1080)
    assert "crop=606:1080:1312:0" in L.filtergraph(lay)


def test_small_corner_face_means_facecam_stack():
    faces = [(90, 70, 110, 110)] * 6              # facecam top-left over gameplay
    lay = L.choose_layout(faces, 1920, 1080)
    assert lay["mode"] == "stack"
    x, y, w, h = lay["cam"]
    assert x <= 90 and y <= 70 and x + w >= 200 and y + h >= 180   # whole face inside the cam box
    g = L.filtergraph(lay)
    assert "vstack=inputs=2" in g and f"scale=1080:{L.CAM_H}" in g and f"scale=1080:{1920 - L.CAM_H}" in g


def test_unknown_size_uses_ffmpeg_expressions():
    assert "crop=w=min(iw\\,ih*1080/1920):h=ih" in L.filtergraph({"mode": "crop", "cx": None, "W": None, "H": None})


def test_caption_sits_on_the_seam_for_stack():
    assert L.caption_y({"mode": "stack"}) == L.CAM_H and L.caption_y(None) == 1080
