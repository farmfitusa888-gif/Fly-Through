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

## The token

Fine-grained, this repository only, **Contents: Read and write**, nothing else.
Revoke it when the run finishes — it is one job, not a standing key.
