"""Tests for the FlyThrough pipeline.

These cover the three things that would silently cost money or ship a bad video:
room mis-resolution, a discontinuous tour after trimming, and a cost quote that
drifts from the verified rate card.
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flythrough.assemble import concat, probe_duration, to_vertical
from flythrough.cost import RATE_CARD, quote
from flythrough.planner import build_plan
from flythrough.render import OpenArtAdapter, build_jobs
from flythrough.rooms import resolve

LABELS = {
    "01_street": "street", "02_front-elevation": "exterior", "03_foyer": "entry",
    "04_great-room": "living", "05_kitchen": "kitchen", "06_dining": "dining",
    "07_hallway": "hallway", "08_master-bedroom": "primary_bed",
    "09_master-bath": "primary_bath", "10_guest-bedroom": "bedroom",
    "11_deck": "patio", "12_backyard-pool": "pool", "13_drone-overhead": "aerial",
    "guest bath": "bathroom", "powder room": "bathroom", "pool house": "exterior",
    "owners suite": "primary_bed", "lake view": "view", "2 car garage": "garage",
    "IMG_4471 front elevation": "exterior", "bonus space": "other",
}


@pytest.mark.parametrize("label,expected", sorted(LABELS.items()))
def test_room_resolution(label, expected):
    assert resolve(label).key == expected


# The 13 files that make up the standard test shoot. Kept explicit rather than
# filtered out of LABELS, so adding a label case can never silently change the
# shape of every plan test.
SHOOT = [
    "01_street", "02_front-elevation", "03_foyer", "04_great-room", "05_kitchen",
    "06_dining", "07_hallway", "08_master-bedroom", "09_master-bath",
    "10_guest-bedroom", "11_deck", "12_backyard-pool", "13_drone-overhead",
]


@pytest.fixture(scope="module")
def photos(tmp_path_factory):
    d = tmp_path_factory.mktemp("photos")
    for name in SHOOT:
        subprocess.run(
            ["ffmpeg", "-f", "lavfi", "-i", "color=c=gray:s=160x120:d=1",
             "-frames:v", "1", str(d / f"{name}.jpg"), "-y", "-loglevel", "error"],
            check=True,
        )
    return d


def test_plan_is_ordered_and_complete(photos):
    plan = build_plan(photos, listing="Test House")
    assert len(plan.shots) == 12
    assert plan.shots[0].from_room == "street"
    assert plan.shots[-1].to_room == "aerial"
    # Coverage is complete: no missing anchors, no thin shoot, no unreadable
    # labels. The one warning this shoot legitimately raises is the ground-to-
    # aerial viewpoint risk, which is a property of the shoot, not a defect.
    coverage = [w for w in plan.warnings
                if "Missing tour anchor" in w or "photo(s)" in w
                or "establishing shot" in w]
    assert coverage == [], coverage


@pytest.mark.parametrize("cap", [None, 50, 40, 30, 20, 12])
def test_trim_never_breaks_continuity(photos, cap):
    """Every shot must start in the room the previous shot ended in."""
    plan = build_plan(photos, listing="Test House", max_seconds=cap)
    for i in range(1, len(plan.shots)):
        assert plan.shots[i].from_room == plan.shots[i - 1].to_room, (
            f"discontinuity at shot {i} with cap={cap}"
        )


@pytest.mark.parametrize("cap", [50, 40, 30])
def test_trim_preserves_anchors_and_bookends(photos, cap):
    plan = build_plan(photos, listing="Test House", max_seconds=cap)
    rooms = {plan.shots[0].from_room} | {s.to_room for s in plan.shots}
    assert plan.total_seconds <= cap
    assert plan.shots[0].from_room == "street"
    assert plan.shots[-1].to_room == "aerial"
    for anchor in ("exterior", "living", "kitchen"):
        assert anchor in rooms, f"{anchor} dropped at cap={cap}"


def test_plan_is_deterministic(photos):
    a = build_plan(photos, listing="X", max_seconds=40).to_dict()
    b = build_plan(photos, listing="X", max_seconds=40).to_dict()
    assert a == b


def test_short_shoot_warns(tmp_path):
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "color=c=gray:s=64x64:d=1", "-frames:v", "1",
         str(tmp_path / "01_kitchen.jpg"), "-y", "-loglevel", "error"], check=True)
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "color=c=gray:s=64x64:d=1", "-frames:v", "1",
         str(tmp_path / "02_hallway.jpg"), "-y", "-loglevel", "error"], check=True)
    plan = build_plan(tmp_path, listing="Tiny")
    joined = " ".join(plan.warnings)
    assert "Missing tour anchor" in joined
    assert "establishing shot" in joined


def test_cost_matches_verified_rate_card():
    """A 60s 1080p Wan job must price at the rate read from the provider."""
    q = quote(seconds=60, shots=12, model="wan2-7", tier="1080p")
    assert q.credits_per_second == RATE_CARD[("wan2-7", "1080p")] == 35
    assert q.base_credits == 2100
    assert q.worst_case_credits == 4200
    assert q.expected_credits == 2625      # 2100 * 1.25


def test_single_anchor_model_is_refused():
    with pytest.raises(ValueError, match="start\\+end frame"):
        quote(seconds=30, shots=6, model="grok-imagine-1-5", tier="720p")


def test_openart_payload_matches_schema(photos):
    """Payload must carry every field wan2-7 image2video declares required."""
    plan = build_plan(photos, listing="Test House", max_seconds=30)
    jobs = build_jobs(plan, OpenArtAdapter(model="wan2-7", tier="1080p"))
    required = {"videoCount", "startFrame", "resolution", "duration",
                "negativePrompt", "enablePromptExpansion"}
    for j in jobs:
        assert required <= set(j.params)
        assert j.params["startFrame"]["type"] == "image"
        assert j.params["endFrame"]["type"] == "image"
        # Server-side prompt expansion would undo the negative bank.
        assert j.params["enablePromptExpansion"] is False
        assert "people" in j.params["negativePrompt"]


def test_assembly_normalises_mixed_inputs(tmp_path):
    """Clips of differing size and fps must join into one clean master."""
    specs = [("red", "640x360", 12), ("green", "1920x1080", 30), ("blue", "1280x720", 24)]
    clips = []
    for i, (c, size, fps) in enumerate(specs):
        p = tmp_path / f"c{i}.mp4"
        subprocess.run(
            ["ffmpeg", "-f", "lavfi", "-i", f"color=c={c}:s={size}:d=4:r={fps}",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(p), "-y", "-loglevel", "error"],
            check=True)
        clips.append(p)

    master = concat(clips, tmp_path / "m.mp4", crossfade=0.4)
    # 3 clips x 4s, minus 2 crossfades x 0.4s
    assert probe_duration(master) == pytest.approx(12 - 0.8, abs=0.15)

    vert = to_vertical(master, tmp_path / "v.mp4")
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(vert)],
        capture_output=True, text=True, check=True).stdout.strip()
    assert out.startswith("1080,1920")


# --- compliance -------------------------------------------------------------

def test_disclosure_pack_is_complete(photos, tmp_path):
    from flythrough.compliance import build_pack
    plan = build_plan(photos, listing="1420 Cedar Ridge Rd", max_seconds=30)
    url = "https://flythrough.co/o/test"
    pack = build_pack(
        plan.listing,
        [{"path": p.path, "room_key": p.room_key} for p in plan.photos],
        tmp_path, url=url, slug="test",
    )
    assert pack.card.exists() and probe_duration(pack.card) > 1.5
    assert pack.qr.exists() and pack.qr.stat().st_size > 0
    assert pack.page.exists()

    page = pack.page.read_text()
    assert "AI-generated video" in page
    assert "not drone footage" in page
    assert "10140.8" in page          # the statute the page exists to satisfy
    assert "Article 12" in page

    # The link to the originals is the operative AB 723 requirement; it must
    # appear in every channel the video reaches.
    for text in (pack.caption, pack.caption_short):
        assert url in text
        assert "AI" in text
    assert "not drone" in pack.caption


def test_disclosure_page_lists_every_source_photo(photos, tmp_path):
    from flythrough.compliance import build_pack
    plan = build_plan(photos, listing="X")
    pack = build_pack(
        plan.listing,
        [{"path": p.path, "room_key": p.room_key} for p in plan.photos],
        tmp_path, url="https://x.co/o/x", slug="x",
    )
    page = pack.page.read_text()
    for p in plan.photos:
        assert Path(p.path).name in page, f"{p.path} missing from disclosure page"


def test_drawtext_escaping_survives_hostile_input(tmp_path):
    """A URL with a colon must not break the ffmpeg filter graph."""
    from flythrough.compliance import make_card
    card = make_card("https://flythrough.co/o/100%-off_it's-here", tmp_path / "c.mp4",
                     seconds=1.0)
    assert card.exists() and probe_duration(card) == pytest.approx(1.0, abs=0.2)


# --- contact sheet ----------------------------------------------------------

def test_contact_sheet_economics_match_verified_pricing():
    from flythrough.contactsheet import plan_sheet
    p = plan_sheet("4K", 2, 2)
    assert (p.tile_w, p.tile_h) == (2752, 1536)   # identical to a 2K render
    assert p.sheet_credits == 80
    assert p.separate_credits == 160
    assert p.saving == 80 and p.saving_pct == 0.5


def test_uneven_slice_is_refused():
    from flythrough.contactsheet import plan_sheet
    with pytest.raises(ValueError, match="does not divide evenly"):
        plan_sheet("4K", 3, 3)


def test_slice_produces_named_tiles_the_planner_can_read(tmp_path):
    """Tiles must come out named so build_plan resolves their rooms directly."""
    from flythrough.contactsheet import slice_sheet, probe_size
    sheet = tmp_path / "sheet.png"
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "color=c=gray:s=5504x3072", "-frames:v", "1",
         str(sheet), "-y", "-loglevel", "error"], check=True)

    names = ["living", "kitchen", "primary-bedroom", "patio"]
    tiles = slice_sheet(sheet, tmp_path / "tiles", rows=2, cols=2, names=names)
    assert len(tiles) == 4
    for t in tiles:
        assert probe_size(t) == (2752, 1536)

    plan = build_plan(tmp_path / "tiles", listing="Sheet House")
    assert [p.room_key for p in plan.photos] == ["living", "kitchen", "primary_bed", "patio"]


# --- inventory gate ---------------------------------------------------------

SHEET_RECORD = {
    "id": "sheet1",
    "prompt": ("A 2x2 grid contact sheet of four real estate photographs of the same "
               "modern farmhouse, white board-and-batten walls, black window frames. "
               "TOP LEFT: the living room, shiplap walls. TOP RIGHT: the kitchen, "
               "shaker cabinets. BOTTOM LEFT: the primary bedroom, oak bed. "
               "BOTTOM RIGHT: the rear covered patio, cedar ceiling."),
    "metadata": {"width": 5504, "height": 3072},
}
EXTERIOR_RECORD = {
    "id": "ext1",
    "prompt": "Real estate listing photograph of the front elevation of a modern farmhouse.",
    "metadata": {"width": 2752, "height": 1536},
}


def test_sheet_reports_exactly_its_cells():
    from flythrough.inventory import classify
    a = classify(SHEET_RECORD)
    assert a.is_sheet
    assert set(a.sheet_rooms) == {"living", "kitchen", "primary_bed", "patio"}


def test_sheet_never_claims_a_room_it_lacks():
    """A false positive suppresses a needed room and ships a tour with a hole.

    'rear covered patio' contains 'rear', which resolves to exterior on its own.
    The sheet must NOT therefore claim to cover the exterior.
    """
    from flythrough.inventory import classify
    assert "exterior" not in classify(SHEET_RECORD).sheet_rooms


def test_gate_blocks_the_duplicate_that_actually_happened():
    """Replays the real 120-credit waste: 3 of 4 rooms were already in a sheet."""
    from flythrough.inventory import check
    v = check(["living", "kitchen", "patio", "aerial"],
              provider_records=[SHEET_RECORD, EXTERIOR_RECORD])
    assert v.missing == ["aerial"]
    assert set(v.have) == {"living", "kitchen", "patio"}
    assert v.credits_saved == 120
    assert not v.is_clean


def test_gate_passes_rooms_nothing_covers():
    from flythrough.inventory import check
    v = check(["dining", "primary_bath"],
              provider_records=[SHEET_RECORD, EXTERIOR_RECORD])
    assert v.missing == ["dining", "primary_bath"]
    assert v.is_clean and v.credits_saved == 0


def test_local_registry_round_trips_and_dedupes(tmp_path):
    from flythrough.inventory import Asset, LocalRegistry
    reg = LocalRegistry(tmp_path / "registry.json")
    reg.add(Asset(asset_id="a1", url="u", room="kitchen"))
    reg.add(Asset(asset_id="a1", url="u", room="kitchen"))   # same id, ignored
    reg.add(Asset(asset_id="a2", url="u", room="living"))
    assert len(reg.assets) == 2
    assert LocalRegistry(tmp_path / "registry.json").rooms == {"kitchen", "living"}


def test_registry_and_provider_layers_combine(tmp_path):
    from flythrough.inventory import Asset, LocalRegistry, check
    reg = LocalRegistry(tmp_path / "r.json")
    reg.add(Asset(asset_id="local1", url="u", room="aerial"))
    v = check(["living", "aerial", "dining"],
              registry=reg, provider_records=[SHEET_RECORD])
    assert v.missing == ["dining"]
    assert v.have["aerial"] == "local1" and v.have["living"] == "sheet1"


# --- viewpoint continuity ---------------------------------------------------

@pytest.mark.parametrize("label,room,expected", [
    ("01_street", "street", "front"),
    ("02_front-elevation", "exterior", "front"),
    ("rear elevation", "exterior", "rear"),
    ("11_deck", "patio", "rear"),
    ("12_backyard-pool", "pool", "rear"),
    ("13_drone-overhead", "aerial", "above"),
    ("04_great-room", "living", "inside"),
])
def test_side_detection(label, room, expected):
    from flythrough.viewpoint import side_of
    assert side_of(label, room) == expected


def test_flags_the_ground_to_aerial_failure_that_actually_happened():
    """Patio (rear) -> aerial framed over the front produced a 'second house'."""
    from flythrough.viewpoint import assess
    risks = assess([("11_deck", "rear", "13_drone-overhead", "above")])
    assert len(risks) == 1
    assert risks[0].severity == "warn"
    assert "different house" in risks[0].reason
    assert "rear" in risks[0].fix


def test_blocks_opposite_elevations_joined_directly():
    from flythrough.viewpoint import assess
    risks = assess([("front", "front", "patio", "rear")])
    assert risks and risks[0].severity == "block"


def test_interior_transitions_are_never_flagged():
    from flythrough.viewpoint import assess
    assert assess([("kitchen", "inside", "dining", "inside")]) == []


def test_plan_surfaces_viewpoint_risk_before_spending(photos):
    """The warning must reach the plan, which is what gates the spend."""
    plan = build_plan(photos, listing="Test House")
    joined = " ".join(plan.warnings)
    assert "different house" in joined, plan.warnings


def test_subframe_crossfade_uses_hard_cut_and_keeps_full_length(tmp_path):
    """Regression: xfade with a sub-frame duration formats to 0.000 and silently
    DROPS a clip. Anything under one frame must take the concat path instead."""
    clips = []
    for i, c in enumerate(("red", "green", "blue")):
        p = tmp_path / f"c{i}.mp4"
        subprocess.run(
            ["ffmpeg", "-f", "lavfi", "-i", f"color=c={c}:s=1926x1076:d=3:r=30",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(p), "-y", "-loglevel", "error"],
            check=True)
        clips.append(p)

    for xf in (0.0, 0.001, 0.02):
        out = concat(clips, tmp_path / f"hard_{xf}.mp4", crossfade=xf, fps=30)
        assert probe_duration(out) == pytest.approx(9.0, abs=0.1), (
            f"crossfade={xf} lost footage -- the sub-frame xfade bug is back")

    # Above one frame the dissolve still applies and shortens the timeline.
    faded = concat(clips, tmp_path / "faded.mp4", crossfade=0.5, fps=30)
    assert probe_duration(faded) == pytest.approx(9.0 - 2 * 0.5, abs=0.1)


def test_hard_cut_seam_is_frame_identical(tmp_path):
    """Two clips sharing a boundary frame must join with no visible change.

    This is the property anchoring buys: shot N ends on the photo shot N+1
    starts on, so a plain cut is already seamless.
    """
    shared = tmp_path / "shared.mp4"
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "color=c=0xb5651d:s=1926x1076:d=2:r=30",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(shared), "-y", "-loglevel", "error"],
        check=True)

    def join(first, second, dest):
        subprocess.run(
            ["ffmpeg", "-i", str(first), "-i", str(second), "-filter_complex",
             "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]", "-c:v", "libx264",
             "-pix_fmt", "yuv420p", str(dest), "-y", "-loglevel", "error"], check=True)
        return dest

    body = tmp_path / "body.mp4"
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "color=c=0x2e6f4e:s=1926x1076:d=3:r=30",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(body), "-y", "-loglevel", "error"],
        check=True)

    a = join(body, shared, tmp_path / "a.mp4")      # ends on shared
    b = join(shared, body, tmp_path / "b.mp4")      # starts on shared
    master = concat([a, b], tmp_path / "m.mp4", crossfade=0.0, fps=30)
    assert probe_duration(master) == pytest.approx(10.0, abs=0.15)

    # Sample either side of the seam at t=5.0 and compare pixel content.
    frames = []
    for t in ("4.95", "5.05"):
        f = tmp_path / f"f{t}.png"
        subprocess.run(["ffmpeg", "-ss", t, "-i", str(master), "-frames:v", "1",
                        str(f), "-y", "-loglevel", "error"], check=True)
        frames.append(f.read_bytes())
    assert frames[0] == frames[1], "seam is visible: frames differ across the cut"


# --- client shot guide ------------------------------------------------------

# A shoot that follows docs/shot-guide-*.md exactly. If this ever raises a
# warning, the guide is telling clients something the validator rejects.
GUIDE_COMPLIANT_SHOOT = [
    "01_street", "02_front-elevation", "03_foyer", "04_great-room",
    "05_kitchen", "06_dining", "07_master-bedroom", "08_deck", "09_rear-aerial",
]


@pytest.fixture(scope="module")
def guide_photos(tmp_path_factory):
    d = tmp_path_factory.mktemp("guide")
    for name in GUIDE_COMPLIANT_SHOOT:
        subprocess.run(
            ["ffmpeg", "-f", "lavfi", "-i", "color=c=gray:s=160x120:d=1",
             "-frames:v", "1", str(d / f"{name}.jpg"), "-y", "-loglevel", "error"],
            check=True)
    return d


def test_a_guide_compliant_shoot_produces_zero_warnings(guide_photos):
    """THE acceptance criterion for the client shot guide.

    Following the published instructions must yield a clean plan. A guide that
    produces warnings is worse than no guide -- it teaches clients to ignore us.
    """
    plan = build_plan(guide_photos, listing="Guide Compliant")
    assert plan.warnings == [], plan.warnings
    assert len(plan.shots) == len(GUIDE_COMPLIANT_SHOOT) - 1


def test_guide_rules_are_the_ones_the_validator_enforces(guide_photos):
    """Breaking either published rule must actually trip the validator."""
    import shutil as _sh
    # Rule 1: aerial not framed over the side of the preceding ground shot.
    bad = guide_photos.parent / "bad_aerial"
    bad.mkdir(exist_ok=True)
    for f in guide_photos.iterdir():
        _sh.copy(f, bad / f.name.replace("09_rear-aerial", "09_front-aerial"))
    warns = " ".join(build_plan(bad, listing="Bad Aerial").warnings)
    assert "different house" in warns, "aerial-side rule is not enforced"


def test_guide_files_are_generated_not_handwritten():
    """Every guide must carry the generated-by banner naming its source."""
    for name in ("shot-guide-agent.md", "shot-guide-photographer.md",
                 "shot-guide-checklist.md"):
        text = (Path(__file__).resolve().parents[2] / "docs" / name).read_text()
        assert "GENERATED by docs/shot_guide.py" in text
        assert "do not edit by hand" in text


def test_guide_states_the_required_anchors_it_gets_from_code():
    """If REQUIRED_ANCHORS changes, the guide must change with it."""
    from flythrough.planner import REQUIRED_ANCHORS
    agent = (Path(__file__).resolve().parents[2] / "docs" / "shot-guide-agent.md").read_text()
    plain = {"exterior": "front of the house", "living": "living room", "kitchen": "kitchen"}
    for anchor in REQUIRED_ANCHORS:
        assert plain[anchor] in agent, f"{anchor} missing from the agent guide"


# --- vehicle taxonomy (auto-dealer vertical) --------------------------------

VEHICLE_LABELS = {
    "01_three-quarter-front": "hero", "02_driver-side-profile": "driver_side",
    "03_rear": "rear", "04_wheel-detail": "wheels", "05_engine-bay": "engine",
    "06_door-open": "door_open", "07_dashboard": "dash",
    "08_front-seats": "front_seats", "09_infotainment-screen": "infotainment",
    "10_trunk": "cargo", "11_odometer-miles": "odometer", "12_vin-sticker": "vin",
    "13_rear-seats": "rear_seats", "passenger side": "passenger_side",
    "grille closeup": "front", "random-thing": "other",
}


@pytest.mark.parametrize("label,expected", sorted(VEHICLE_LABELS.items()))
def test_vehicle_resolution(label, expected):
    from flythrough.vehicles import resolve as vresolve
    assert vresolve(label).key == expected


def test_vehicle_resolve_never_returns_none():
    """An odd dealer filename must not crash a job or lose a frame."""
    from flythrough.vehicles import resolve as vresolve
    for junk in ("", "   ", "!!!", "1234", "zzzz-qqqq"):
        p = vresolve(junk)
        assert p is not None and p.key == "other"


def test_vehicle_proof_shots_are_never_hero():
    from flythrough.vehicles import resolve as vresolve
    for label in ("odometer", "vin", "undercarriage", "wheels"):
        assert not vresolve(label).hero_eligible


def test_vehicle_taxonomy_matches_the_rooms_contract():
    """Same interface, so the planner cannot tell which vertical it was given."""
    from flythrough import rooms, vehicles
    for name in ("TOUR_ORDER", "ALIASES", "NON_HERO", "INTERIOR", "UNKNOWN", "resolve"):
        assert hasattr(vehicles, name), f"vehicles.{name} missing"
    a, b = rooms.resolve("kitchen"), vehicles.resolve("dash")
    for attr in ("key", "rank", "interior", "is_known", "hero_eligible"):
        assert hasattr(a, attr) and hasattr(b, attr)


def test_viewpoint_ports_to_vehicles_unchanged():
    """Left-to-right across a car is as impossible as front-to-back on a house."""
    from flythrough.viewpoint import assess
    risks = assess([("driver_side", "left", "passenger_side", "right")])
    assert risks and risks[0].severity == "block"
    assert assess([("dash", "inside", "front_seats", "inside")]) == []


# --- product taxonomy (product-motion ads) ----------------------------------

PRODUCT_LABELS = {
    "01_hero-three-quarter": "hero", "02_front": "front", "03_profile": "side",
    "04_back": "back", "05_flatlay": "top", "06_stitching-closeup": "detail",
    "07_leather-swatch": "material", "08_unzipped": "open", "09_lining": "interior",
    "10_in-hand": "scale", "11_lifestyle-styled": "in_use", "12_unboxing": "packaging",
    "13_size-chart": "size_chart", "14_care-label": "label", "junk": "other",
}


@pytest.mark.parametrize("label,expected", sorted(PRODUCT_LABELS.items()))
def test_product_resolution(label, expected):
    from flythrough.products import resolve as presolve
    assert presolve(label).key == expected


def test_every_underscored_key_is_reachable():
    """A canonical key with an underscore can never match a token, so each one
    needs a joined-form alias. Without this, size_chart silently became 'other'."""
    from flythrough import products, vehicles
    for mod in (products, vehicles):
        for key in mod.TOUR_ORDER:
            if "_" not in key:
                continue
            joined = key.replace("_", "")
            reachable = joined in mod.ALIASES or any(
                v == key for v in mod.ALIASES.values())
            assert reachable, f"{mod.__name__}.{key} is unreachable from any label"


@pytest.mark.parametrize("mod_name", ["rooms", "vehicles", "products"])
def test_all_taxonomies_share_one_contract(mod_name):
    """Three verticals, one interface. The planner never knows which it has."""
    import importlib
    mod = importlib.import_module(f"flythrough.{mod_name}")
    for name in ("TOUR_ORDER", "ALIASES", "NON_HERO", "INTERIOR", "UNKNOWN", "resolve"):
        assert hasattr(mod, name), f"{mod_name}.{name} missing"
    r = mod.resolve("!!!nonsense!!!")
    assert r is not None and r.key == mod.UNKNOWN
    for attr in ("key", "rank", "interior", "is_known", "hero_eligible"):
        assert hasattr(r, attr)


def test_no_taxonomy_contains_a_person():
    """Product ads must never generate a human -- FTC bans AI testimonials
    outright, and generated people in listing media invite fair-housing risk."""
    from flythrough import products, vehicles, rooms
    banned = {"person", "model", "presenter", "spokesperson", "creator",
              "testimonial", "customer", "influencer"}
    for mod in (products, vehicles, rooms):
        keys = set(mod.TOUR_ORDER) | set(mod.ALIASES)
        assert not (keys & banned), f"{mod.__name__} references a person"


# --- tempo ------------------------------------------------------------------

def test_ad_tempo_is_cheaper_and_denser_than_tour_tempo():
    """The lesson that cost real credits: slow tour pacing on a performance
    object is both blander AND more expensive than a proper ad cut."""
    from flythrough.moves import MOVES, at_tempo
    tour = [at_tempo(MOVES[k], "tour") for k in ("orbit_left", "orbit_left", "enter_from_light")]
    ad = [at_tempo(MOVES[k], "ad") for k in
          ("orbit_left", "detail_drift", "orbit_left", "enter_from_light",
           "detail_push", "glide_through")]
    assert sum(m.seconds for m in ad) < sum(m.seconds for m in tour)
    assert len(ad) > len(tour)


def test_tempo_never_goes_below_a_renderable_beat():
    """Under ~2s an anchored shot cannot travel between its frames without
    lurching, so every tempo floors there."""
    from flythrough.moves import MOVES, TEMPO, at_tempo
    for tempo in TEMPO:
        for move in MOVES.values():
            assert at_tempo(move, tempo).seconds >= 2


def test_tempo_rewrites_pacing_not_just_duration():
    from flythrough.moves import MOVES, at_tempo
    calm = at_tempo(MOVES["orbit_left"], "tour")
    fast = at_tempo(MOVES["orbit_left"], "ad")
    assert "slow" in calm.pacing
    assert "slow" not in fast.pacing and calm.pacing != fast.pacing
    assert calm.camera == fast.camera        # the move itself is unchanged


def test_unknown_tempo_is_refused():
    from flythrough.moves import MOVES, at_tempo
    with pytest.raises(KeyError, match="unknown tempo"):
        at_tempo(MOVES["orbit_left"], "cinematic")


# --- disclosure placement ---------------------------------------------------

def test_real_estate_cannot_opt_out_of_disclosure():
    """The duty is NAR Article 12 nationally plus AB 723 in California, and AB 723
    reaches the person acting on the broker's behalf -- the vendor. 'none' is not
    a house-style choice for listing media."""
    from flythrough.compliance import check_placement
    with pytest.raises(ValueError, match="may not use placement"):
        check_placement("rooms", "none")
    assert check_placement("rooms", "mark_end") == "mark_end"
    assert check_placement("rooms", "lead_card") == "lead_card"


@pytest.mark.parametrize("vertical", ["vehicles", "products"])
def test_ad_verticals_may_run_clean(vertical):
    """Vehicle and product advertising falls under FTC truth-in-advertising, which
    requires the ad not misrepresent the product -- not that the tooling be
    announced. No person in frame, so synthetic-performer rules do not bite."""
    from flythrough.compliance import check_placement
    assert check_placement(vertical, "none") == "none"


def test_unknown_placement_is_refused():
    from flythrough.compliance import check_placement
    with pytest.raises(ValueError, match="unknown placement"):
        check_placement("rooms", "subtle")


def test_corner_mark_is_a_filter_not_a_clip():
    """It must burn over the whole runtime, so it cannot be a clip to cut in."""
    from flythrough.compliance import make_corner_mark
    frag = make_corner_mark()
    assert isinstance(frag, list) and frag
    assert "drawtext" in frag[0] and "AI-generated" in frag[0]


def test_end_card_renders(tmp_path):
    from flythrough.compliance import make_end_card
    c = make_end_card("https://iflythroughit.com/o/x", tmp_path / "e.mp4", seconds=2.0)
    assert c.exists() and probe_duration(c) == pytest.approx(2.0, abs=0.2)


# --- stall trimming ---------------------------------------------------------

def test_trim_removes_only_the_frozen_edge(tmp_path):
    """Cut the held frame at an edge and NOTHING else.

    Measured across a real five-shot tour, genuine freeze totalled 2.1s of 26.3s
    -- runs of 0.27s to 0.70s touching an edge. Earlier versions gated on "where
    does sustained motion begin" and removed 9.2s, five times the freeze. That
    shortens every SHOT rather than the joins, and the result reads as sped up
    even though playback rate never changes. An operator caught it twice.
    """
    from flythrough.assemble import trim_stalls, _motion_profile

    moving = tmp_path / "m.mp4"
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "testsrc2=s=640x360:d=3:r=30",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(moving), "-y", "-loglevel", "error"],
        check=True)
    frozen = tmp_path / "f.mp4"
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "color=c=0x336699:s=640x360:d=1:r=30",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(frozen), "-y", "-loglevel", "error"],
        check=True)
    joined = tmp_path / "j.mp4"
    subprocess.run(
        ["ffmpeg", "-i", str(moving), "-i", str(frozen), "-filter_complex",
         "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]", "-c:v", "libx264",
         "-pix_fmt", "yuv420p", str(joined), "-y", "-loglevel", "error"], check=True)

    out = trim_stalls(joined, tmp_path / "o.mp4")
    removed = probe_duration(joined) - probe_duration(out)
    # The frozen second should go; the three moving seconds must survive.
    assert 0.6 < removed < 1.6, f"removed {removed:.2f}s, expected ~1s of freeze"
    assert probe_duration(out) > 2.5, "ate into the moving footage"


def test_trim_leaves_a_clip_with_no_frozen_edge_alone(tmp_path):
    """A clip that moves all the way to both edges must come back untouched."""
    from flythrough.assemble import trim_stalls
    src = tmp_path / "all_moving.mp4"
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "testsrc2=s=640x360:d=3:r=30",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src), "-y", "-loglevel", "error"],
        check=True)
    out = trim_stalls(src, tmp_path / "o.mp4")
    assert probe_duration(out) == pytest.approx(probe_duration(src), abs=0.2)


def test_trim_never_guts_a_short_clip(tmp_path):
    """A 2s ad beat must survive trimming with something renderable left."""
    from flythrough.assemble import trim_stalls
    src = tmp_path / "beat.mp4"
    subprocess.run(
        ["ffmpeg", "-f", "lavfi", "-i", "color=c=gray:s=640x360:d=2:r=30",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src), "-y", "-loglevel", "error"],
        check=True)
    out = trim_stalls(src, tmp_path / "out.mp4")
    assert probe_duration(out) >= 0.55


def test_trim_has_no_arbitrary_cap(tmp_path):
    """Two caps were tried -- a fixed 0.55s and a fraction of duration -- and both
    silently blocked correctly-identified cuts, leaving freeze in the output.
    There is no principled maximum: if 40% of a clip is held, 40% should go.
    keep_min is the only legitimate guard."""
    import inspect
    from flythrough.assemble import trim_stalls
    params = inspect.signature(trim_stalls).parameters
    assert "max_trim" not in params
    assert "max_trim_fraction" not in params
    assert "keep_min" in params
    assert "min_run" in params


# ---------------------------------------------------------------- site pricing


def _pricing_modules():
    """model/ is not a package and imports flythrough from pipeline/."""
    root = Path(__file__).resolve().parents[2]
    for extra in (root / "model", root / "pipeline"):
        if str(extra) not in sys.path:
            sys.path.insert(0, str(extra))
    import ad_pricing
    import export_pricing
    return ad_pricing, export_pricing


def test_site_pricing_json_matches_the_model():
    """The page reads site/pricing.json. If someone edits a price in the model
    and forgets to re-export, the site ships the old number -- to a customer.
    This test is the only thing standing between those two states."""
    _, export_pricing = _pricing_modules()
    on_disk = json.loads(export_pricing.OUT.read_text())
    assert on_disk == export_pricing.build(), (
        "site/pricing.json is stale -- run python3 model/export_pricing.py")


def test_every_priced_product_has_customer_copy():
    """Renaming a product in the model must fail loudly here rather than
    rendering an unlabelled card on a live page."""
    ad_pricing, export_pricing = _pricing_modules()
    for p in ad_pricing.PRODUCTS:
        assert p.name in export_pricing.VEHICLE_COPY, p.name
    from unit_economics import TIERS
    for t in TIERS:
        assert t.name in export_pricing.PROPERTY_COPY, t.name


def test_no_priced_offer_sells_below_cost():
    """Every vehicle offer and lot plan must clear its render and payment fees."""
    ad_pricing, _ = _pricing_modules()
    for p in ad_pricing.PRODUCTS:
        assert p.margin()["gp"] > 0, p.name
    for lp in ad_pricing.LOT_PLANS:
        m = lp.margin()
        assert m["gp"] > 0, lp.name
        assert lp.per_unit < ad_pricing.PRODUCTS[0].price, (
            f"{lp.name} is not a discount on the a la carte rate")


def test_lot_plans_get_cheaper_per_unit_as_volume_rises():
    ad_pricing, _ = _pricing_modules()
    rates = [lp.per_unit for lp in ad_pricing.LOT_PLANS]
    assert rates == sorted(rates, reverse=True), rates


def test_landing_page_hardcodes_no_prices():
    """Prices belong to the model. A dollar figure typed into the page template
    is a number that will one day disagree with the invoice."""
    import re
    root = Path(__file__).resolve().parents[2]
    src = (root / "site" / "build_landing.py").read_text()
    # Competitor anchors in the lede are ranges and deliberately not ours.
    allowed = {"$300–$500", "$150–$500", "$150–$400",  # competitor anchors
               "$500–$5,000"}                          # cited MLS penalty range
    found = set(re.findall(r"\$[\d,]+(?:–\$[\d,]+)?", src)) - allowed
    assert not found, f"hardcoded prices in the landing template: {sorted(found)}"


# ------------------------------------------------------------------- car films


def _car_manifest():
    root = Path(__file__).resolve().parents[2]
    return json.loads((root / "samples" / "cars" / "manifest.json").read_text())


def test_car_beats_form_an_unbroken_chain():
    """Anchoring is the whole product: beat N must end on the viewpoint beat
    N+1 opens on. A gap here is a cut to a different-looking car."""
    for slug, film in _car_manifest()["films"].items():
        beats = film["beats"]
        assert [b["n"] for b in beats] == list(range(1, len(beats) + 1)), slug
        for a, b in zip(beats, beats[1:]):
            assert a["to"] == b["from"], (
                f"{slug}: beat {a['n']} ends on {a['to']!r} but "
                f"beat {b['n']} opens on {b['from']!r}")


def test_car_beat_ids_are_unique_across_both_films():
    """The ingest matcher keys on these ids. A collision would silently place
    one clip in two films, or the wrong clip in one."""
    ids = [b["id"] for f in _car_manifest()["films"].values() for b in f["beats"]]
    assert len(ids) == len(set(ids)) == 15


def test_car_films_declare_a_legal_disclosure_placement():
    from flythrough.compliance import check_placement
    for slug, film in _car_manifest()["films"].items():
        check_placement("vehicles", film["disclosure"])   # raises if not


def test_car_beat_runtimes_match_their_tempo():
    """Ad and hype tempo floor at 2s. A beat under that means the tempo scaling
    was applied twice, which is how a film ends up unwatchably fast."""
    for slug, film in _car_manifest()["films"].items():
        for b in film["beats"]:
            assert b["seconds"] >= 2.0, f"{slug} beat {b['n']}: {b['seconds']}s"
        total = sum(b["seconds"] for b in film["beats"])
        assert 12 <= total <= 20, f"{slug} runs {total:.1f}s"


def test_car_ingest_matches_a_renamed_file_by_id_prefix(tmp_path):
    """OpenArt names are long, so people rename them and browsers append ' (1)'.
    Matching on the id prefix is what keeps an unsorted folder usable."""
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "samples" / "cars"))
    import importlib
    build = importlib.import_module("build")
    beat = build.MANIFEST["films"]["ferrari"]["beats"][0]
    (tmp_path / f"{beat['id']}-whatever the user renamed it (1).mp4").write_bytes(b"x")
    build.SEARCH = (tmp_path,)
    try:
        found = build.find_local(beat)
        assert found is not None and found.name.startswith(beat["id"] + "-")
    finally:
        build.SEARCH = (root / "samples" / "cars" / "raw", root / "samples" / "inbox")


def _moving_clip(path: Path, seconds: float = 2.0) -> Path:
    """Footage that decelerates hard: fast in the middle, slow at the edges.
    That shape is what broke relative-only gating."""
    subprocess.run(
        [FFMPEG_BIN, "-f", "lavfi", "-i",
         f"testsrc2=s=640x360:d={seconds}:r=30",
         "-vf", "zoompan=z='min(zoom+0.004,1.4)':d=1:s=640x360,"
                "scale=640:360",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
         str(path), "-y", "-loglevel", "error"], check=True)
    return path


def test_trim_gate_is_capped_in_absolute_terms(tmp_path):
    """A high-dynamic-range beat -- a 2s hype cut spiking to ~47 in the middle --
    puts its 70th percentile around 20, so a purely relative gate of 4% lands at
    0.82. Ordinary decelerating footage reads 0.10-0.35, well UNDER that, so
    every edge looked frozen and four clean Ferrari beats lost 1.8s between them.
    Genuinely held frames measure 0.0015-0.012. The cap must sit between."""
    from flythrough.assemble import STILL
    assert 0.012 < STILL < 0.10, (
        f"STILL={STILL} no longer separates held frames from slow real motion")


def test_trim_leaves_a_hype_beat_with_no_freeze_alone(tmp_path):
    """The regression itself: source with a genuine frozen tail must lose it,
    and the same source without one must come back byte-for-byte in duration."""
    from flythrough.assemble import probe_duration, trim_stalls
    clean = _moving_clip(tmp_path / "clean.mp4")
    out = trim_stalls(clean, tmp_path / "clean_out.mp4")
    assert probe_duration(out) == pytest.approx(probe_duration(clean), abs=0.05), (
        "trimmed a clip that has no frozen edge")

    held = tmp_path / "held.mp4"
    subprocess.run(
        [FFMPEG_BIN, "-i", str(clean), "-vf",
         "tpad=stop_mode=clone:stop_duration=0.5",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
         str(held), "-y", "-loglevel", "error"], check=True)
    trimmed = trim_stalls(held, tmp_path / "held_out.mp4")
    removed = probe_duration(held) - probe_duration(trimmed)
    assert 0.35 < removed < 0.75, f"removed {removed:.2f}s of a 0.5s clone"


# ------------------------------------------------------------------- the store


def _catalog():
    root = Path(__file__).resolve().parents[2]
    for extra in (root / "model", root / "pipeline"):
        if str(extra) not in sys.path:
            sys.path.insert(0, str(extra))
    import catalog
    return catalog


def test_no_sku_sells_below_cost():
    for s in _catalog().CATALOG:
        assert s.margin()["gp"] > 0, f"{s.id} loses money"


def test_every_sku_has_a_payment_link_slot():
    """config.payments.links is what the Buy button reads. A SKU missing from it
    can never be bought; a stale id in it is a link nobody will ever click."""
    root = Path(__file__).resolve().parents[2]
    cfg = json.loads((root / "site" / "config.json").read_text())
    links = cfg["payments"]["links"]
    ids = {s.id for s in _catalog().CATALOG}
    assert set(links) == ids, (
        f"missing slots: {sorted(ids - set(links))}; "
        f"stale slots: {sorted(set(links) - ids)}")


def test_every_sku_declares_intake_for_its_vertical():
    """No intake questions means a paid order with nothing to work from."""
    cat = _catalog()
    for s in cat.CATALOG:
        assert cat.INTAKE.get(s.vertical), s.id
        assert len(cat.INTAKE[s.vertical]) >= 3, s.vertical


def test_real_estate_skus_cannot_opt_out_of_disclosure():
    """A rooms SKU sold with placement 'none' would be an unlawful delivery.
    compliance refuses it in code; this pins that the catalogue agrees."""
    from flythrough.compliance import ALLOWED_PLACEMENT, check_placement
    cat = _catalog()
    assert "none" not in ALLOWED_PLACEMENT["rooms"]
    for s in cat.CATALOG:
        if s.vertical == "rooms":
            with pytest.raises(Exception):
                check_placement("rooms", "none")


def test_buy_button_never_renders_an_empty_href():
    """An unconfigured SKU must fall back to the email path, never a dead link."""
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "site"))
    import importlib
    bl = importlib.import_module("build_landing")
    html = bl.buy("a-sku-with-no-link-configured")
    assert 'href=""' not in html
    assert "mailto:" in html


def test_site_has_no_dead_internal_links():
    """The link checker that build_all runs, pinned as a test. A dead link on
    the page that just took someone's money is the expensive kind."""
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "site"))
    import importlib
    ba = importlib.import_module("build_all")
    if not (ba.DIST / "index.html").exists():
        pytest.skip("dist/ not built; run python3 site/build_all.py")
    assert ba.check_links() == []


def test_buying_more_never_costs_more_per_unit():
    """A first pass priced the 3-pack at $99 -- $33 a vehicle -- which undercut
    the 25-vehicle plan at $34. Committing to more would have cost more each,
    which makes every plan on the page look like a worse deal than the sampler.
    The whole walkaround ladder must be monotonic."""
    _catalog()          # puts model/ on sys.path
    import ad_pricing
    three = next(p for p in ad_pricing.PRODUCTS if p.name == "Walkaround x3")
    rungs = ([(three.quantity, three.unit_price)]
             + [(l.units, l.per_unit) for l in ad_pricing.LOT_PLANS])
    assert [u for u, _ in rungs] == sorted(u for u, _ in rungs), "rungs out of order"
    for (ua, pa), (ub, pb) in zip(rungs, rungs[1:]):
        assert pa >= pb, f"{ub} units at ${pb} beats {ua} units at ${pa}"


def test_the_per_vin_rate_is_not_sellable_on_its_own():
    """$39 is a rate, not a checkout: the flat card fee plus the per-order
    handling makes a single-unit online order the thinnest thing we could sell.
    It must stay out of the catalogue and off the page."""
    import ad_pricing
    cat = _catalog()
    per_vin = next(p for p in ad_pricing.PRODUCTS
                   if p.name == "Walkaround (per VIN)")
    assert per_vin.channel == "in_plan"
    assert not [s for s in cat.CATALOG if s.quantity == 1 and s.vertical == "vehicles"
                and s.price < 100], "a sub-$100 single-unit vehicle SKU is buyable"
    root = Path(__file__).resolve().parents[2]
    shown = json.loads((root / "site" / "pricing.json").read_text())["vehicle"]
    assert per_vin.name not in [r["name"] for r in shown]


def test_minimum_order_is_priced_at_the_full_rate():
    """The floor is on order SIZE. If the 3-pack ever carries a discount it
    stops being a minimum and starts competing with the plans."""
    import ad_pricing
    three = next(p for p in ad_pricing.PRODUCTS if p.name == "Walkaround x3")
    per_vin = next(p for p in ad_pricing.PRODUCTS
                   if p.name == "Walkaround (per VIN)")
    assert three.quantity == ad_pricing.WALKAROUND_MIN_UNITS
    assert three.unit_price == pytest.approx(per_vin.price)


def test_disclosure_page_is_not_published_without_its_originals():
    """/o/<slug>/ is the artefact AB 723 requires a link to. If the originals
    are not on disk the page must not exist -- a page claiming to show unaltered
    originals while showing broken images is a false statement, not a degraded
    one. Pinned because the failure mode is silent: the page looks fine to the
    person who built it and broken to the regulator who opens it."""
    root = Path(__file__).resolve().parents[2]
    dist_o = root / "site" / "dist" / "o"
    if not dist_o.is_dir():
        pytest.skip("dist/ not built")
    for page in dist_o.glob("*/index.html"):
        originals = page.parent / "originals"
        html = page.read_text()
        for ref in set(re.findall(r'src="(originals/[^"]+)"', html)):
            assert (page.parent / ref).is_file(), (
                f"{page.parent.name} published with a missing original: {ref}")
