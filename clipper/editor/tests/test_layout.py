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
    assert lay["cam_h"] == L.CAM_H


def test_unknown_size_uses_ffmpeg_expressions():
    assert "crop=w=min(iw\\,ih*1080/1920):h=ih" in L.filtergraph({"mode": "crop", "cx": None, "W": None, "H": None})


def test_caption_sits_on_the_seam_for_stack():
    assert L.caption_y({"mode": "stack"}) == L.CAM_H and L.caption_y(None) == 1080


def test_one_off_faces_are_ignored():
    cam = [(216, 87, 74, 104)] * 6                  # xQc facecam, every frame
    noise = [(605, 493, 23, 28)]                    # a face on a screen, once
    lay = L.choose_layout(cam + noise, 1920, 1080)
    assert lay["mode"] == "stack"


def test_dominant_picks_the_face_seen_most():
    faces = [(177, 459, 80, 104)] * 6 + [(903, 561, 99, 153)] * 2
    assert L.dominant(faces, 2560) == [(177, 459, 80, 104)] * 6


def test_missing_model_means_no_faces(tmp_path):
    assert L.sample_faces(tmp_path / "x.mp4", 0, 10, model=str(tmp_path / "none.onnx")) == []


def _profile(n, peaks):
    p = [1.0] * n
    for i in peaks:
        p[i] = 30.0
    return p


def test_cam_box_from_overlay_borders():
    # xQc (VM, 2026-10-19): facecam flush top-left, borders at x=405 and y=315
    face = (216, 87, 74, 104)
    box = L.cam_box_from_profiles(_profile(1920, [405]), _profile(1080, [315]), face, 1920, 1080)
    assert box == (0, 0, 405, 315)


def test_cam_box_none_without_any_border():
    assert L.cam_box_from_profiles([1.0] * 1920, [1.0] * 1080, (216, 87, 74, 104), 1920, 1080) is None


def test_tall_overlay_gets_a_taller_panel_and_face_centred_crop():
    # Valkyrae (VM): overlay 5..404 x 277..729 (portrait-ish) -> panel capped at 960 px tall
    lay = L.stack_from_box((5, 277, 404, 729), 217, 511, 2560, 1440)
    assert lay["cam_h"] == L.CAM_H_MAX
    x, y, w, h = lay["cam"]
    assert (x, w) == (5, 399) and 277 <= y and y + h <= 729 and abs(w / h - 1080 / 960) < 0.01
    g = L.filtergraph(lay)
    assert "scale=1080:960" in g and "scale=1080:960" in g and f"scale=1080:{1920 - 960}" in g
    assert L.caption_y(lay) == 960


def test_wide_overlay_keeps_its_shape():
    lay = L.stack_from_box((0, 0, 405, 315), 253, 139, 1920, 1080)
    assert lay["cam"] == [0, 0, 405, 315] and lay["cam_h"] == 840


def test_mini_corner_cam_over_a_broadcast_is_full_bleed_not_stack():
    # Adin Ross on Kick, 2026-10-19: two 33 px faces in a tiny corner cam over a boxing broadcast.
    # Stacking blew a 100x89 px crop up to 1080x960. Full-bleed the shot instead.
    faces = [(408, 948, 30, 35), (407, 948, 31, 36), (414, 954, 25, 30), (408, 959, 27, 33)] * 2
    lay = L.choose_layout(faces, 1920, 1080)
    assert lay["mode"] == "crop" and lay["cx"] == 960


def test_tiny_cam_panel_is_never_blown_up():
    # Lacy 2026-10-20: a 62 px face in a round cam bubble; the found box was 77x68 px -> 14x upscale, blurry.
    faces = [(80, 60, 50, 62)] * 7
    assert L.choose_layout(faces, 1920, 1080, cam_box=(71, 56, 148, 124))["mode"] == "crop"
    assert L.choose_layout(faces, 1920, 1080)["mode"] == "crop"                  # face-sized estimate too small too
    assert L.choose_layout([(216, 87, 74, 104)] * 6, 1920, 1080, cam_box=(0, 0, 405, 315))["mode"] == "stack"  # xQc


def test_two_people_who_fit_are_framed_together_else_the_biggest():
    cw = L.crop_w(1920, 1080)                                                   # ~607 px window
    assert L.target_cx([(700, 300, 150, 150), (950, 320, 140, 140)], cw) == (700 + 1090) / 2
    assert L.target_cx([(200, 300, 150, 150), (1500, 320, 220, 220)], cw) == 1610  # too far apart: biggest
    assert L.target_cx([(1500, 320, 220, 220), (300, 300, 60, 60)], cw) == 1610    # a small background face
    assert L.target_cx([], cw) is None


def test_camera_path_holds_small_moves_pans_at_limited_speed_and_stays_in_frame():
    W, cw = 1920, L.crop_w(1920, 1080)
    pts = [(t / 2, 600) for t in range(4)] + [(2.0 + t / 2, 1700) for t in range(8)] + [(6.0, None)]
    path = L.smooth_path(pts, W, cw)
    xs = [x for _, x in path]
    assert xs[0] == 600 and xs[-1] == xs[-2]                                     # no face: hold the last place
    steps = [b - a for a, b in zip(xs, xs[1:])]
    assert max(steps) <= L.PAN_MAX * W * 0.5 + 1e-6                              # <= 480 px/s at 2 samples/s
    assert xs[-1] <= W - cw / 2 + 1e-6                                           # never past the edge
    jitter = L.smooth_path([(t / 2, 900 + (30 if t % 2 else -30)) for t in range(10)], W, cw)
    assert len({round(x) for _, x in jitter}) == 1                               # inside the deadband: still


def test_moving_crop_is_one_flat_ffmpeg_expression_with_the_caption_band_cut():
    lay = {"mode": "crop", "cx": 960, "W": 1920, "H": 1080, "cut": L.OWN_CAPTION_CUT,
           "path": [[0, 400], [1, 400], [3, 1500], [6, 1500]]}
    fg = L.filtergraph(lay)
    assert fg.startswith("[0:v]crop=522:928:clip(") and "\\,0\\,1)" in fg       # band cut, commas escaped
    assert L.keyframes([(0, 100), (1, 200), (2, 300), (3, 300)]) == [(0, 100), (2, 300), (3, 300)]  # straight runs


def test_follow_adds_the_path_only_to_face_crops():
    track = lambda v, s, e: [(0.0, [(300, 300, 260, 260)]), (0.5, [(320, 300, 260, 260)])]  # noqa: E731
    crop = L.choose_layout([(300, 300, 260, 260)] * 4, 1920, 1080)              # IRL: a big face
    assert crop["mode"] == "crop" and L.follow(crop, "v", 0, 1, track)["path"][0] == [0.0, 440.0]
    assert "path" not in L.follow(L.choose_layout([], 1920, 1080), "v", 0, 1, track)   # no face: centre crop
    stack = L.choose_layout([(1700, 80, 90, 90)] * 5, 1920, 1080)
    assert L.follow(stack, "v", 0, 1, track) is stack
