# tools

## `unzip-to-github.gs` — get the OpenArt archive into the repo

The clips have always been *in* the zip. The zip is what cannot move:

| Route | Why it fails |
|---|---|
| Drive connector download | Hard cap of **10 MB per file**; the archive is **300 MB** |
| `drive.google.com` direct | CONNECT refused **403** by the build environment's egress policy |
| Individual clips from Drive | Would work — each is 2–6 MB — but only the archive is in Drive |

This Apps Script runs inside Google's own servers, where neither wall applies.
It expands the archive in place and commits each video to the branch through the
GitHub API. Nothing is downloaded to your device.

**Run `dryRun()` first.** Apps Script caps how much it will hold in memory and a
300 MB archive is near that ceiling. Thirty seconds tells you whether this route
is open before you go and make a token.

If it refuses, that is a platform limit and not something to debug. The fallback
is the route that already worked for the first eight files:

1. Unzip on a computer
2. GitHub → branch `claude/drone-pov-renderer-business-5usm0h`
3. `samples/inbox` → **Add file → Upload files** → drag every `.mp4` in

Names do not matter. `samples/cars/manifest.json` keys on the numeric OpenArt id
that prefixes each filename, so an unsorted folder still lands in cut order.

Then: `python3 samples/cars/build.py status`

## `fetchOriginals()` — the other half, and the easier one

The six source stills for 1420 Cedar Ridge live on OpenArt's CDN, which this
build environment cannot reach. **Google's servers can.** So the same script
pulls them and commits them to
`samples/1420-cedar-ridge/delivery/originals/`.

Run this **even if the unzip refuses**. It touches no archive, so the blob
ceiling does not apply — it is six small images over HTTP. On its own it
unblocks the disclosure page, which is the thing currently standing between the
property film and being deliverable at all.

These are the images the demo film was generated *from*. That is exactly what an
originals page must show: the unaltered source, never a frame lifted out of the
finished video. For a paying client the same slot holds their own photographs,
untouched.

If a link returns 403 or 404 the CDN URL has expired — re-download from your
OpenArt history and upload by hand.

## What is verified, and what is not

| Part | Status |
|---|---|
| Zip filtering, flattening, `.mov`→`.mp4`, junk skipping | **Verified** against a rebuilt archive with the real filenames, nested dirs and a `.DS_Store` |
| Manifest ids survive the rename | **Verified** — `36199589`, `98869283` recovered |
| GitHub read-sha then write-with-sha | **Verified** against this live branch and path |
| `Utilities.unzip` on a 300 MB blob | **Not verified.** Cannot be, from here. This is the platform ceiling `dryRun()` exists to test. |

## The token

Fine-grained, this repository only, **Contents: Read and write**, nothing else.
Revoke it when the run finishes — it is one job, not a standing key.
