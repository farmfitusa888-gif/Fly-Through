Drop the fifteen rendered car beats here (unzipped MP4s, NOT the zip).

Why here and not Google Drive: this build container's egress policy blocks both
drive.google.com and cdn.openart.ai, so nothing can be pulled down from either.
github.com is allowed, which makes the repo the only working transfer route.

Each clip is 2-3 seconds, roughly 2-5 MB -- far below GitHub's limits. The
300 MB zip is not; unzip it first and upload the MP4s themselves.

  GitHub -> branch claude/drone-pov-renderer-business-5usm0h
         -> samples/inbox -> Add file -> Upload files -> drag all 15 -> Commit

Keep whatever names OpenArt gave them. samples/cars/manifest.json keys on the
numeric id that prefixes every OpenArt filename, so the order is recovered
automatically -- do not try to rename them into order by hand.

Then:  python3 samples/cars/build.py

Expected: ferrari 8 beats / 16.5s, silverado 7 beats / 15.5s.
