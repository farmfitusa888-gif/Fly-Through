"""Tests for the FlyThrough pipeline.

These cover the three things that would silently cost money or ship a bad video:
room mis-resolution, a discontinuous tour after trimming, and a cost quote that
drifts from the verified rate card.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

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
