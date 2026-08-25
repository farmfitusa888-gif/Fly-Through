Drop the rendered car beats here.

THE CLIPS ARE IN THE ZIP. That was always true, and the archive is the only
thing that cannot move -- not the clips. Each one is 2-6 MB, comfortably inside
every limit involved. Two independent walls stop the 300 MB archive:

  Drive connector download    hard cap of 10 MB per file
  drive.google.com direct     CONNECT refused 403 by the egress policy

Neither applies to the files inside it.

TWO WAYS TO GET THEM HERE
-------------------------

1. tools/unzip-to-github.gs

   A Google Apps Script that expands the archive inside Drive and commits each
   video straight to this branch. Nothing downloads to your device, so neither
   wall applies. Run dryRun() first -- Apps Script caps how large a blob it will
   hold, and a 300 MB archive is near that ceiling. Thirty seconds tells you
   whether the route is open before you go and make a token.

2. Unzip on a computer, then drag them in

   GitHub -> branch claude/drone-pov-renderer-business-5usm0h
          -> samples/inbox -> Add file -> Upload files -> drag every .mp4

   This is the route that already carried the first eight files.

Keep whatever names OpenArt gave them. samples/cars/manifest.json keys on the
numeric id that prefixes every OpenArt filename, so cut order is recovered
automatically -- do not try to rename them into order by hand. A .mov is fine
too; the tool renames it, and OpenArt's container is H.264 either way.

Then:  python3 samples/cars/build.py status
       python3 samples/cars/build.py

Expected: ferrari 8 beats / 16.5s, silverado 7 beats / 15.5s.

STILL MISSING, AND NOT IN THE ARCHIVE
-------------------------------------

The six unedited house originals for 1420 Cedar Ridge. They belong in
samples/1420-cedar-ridge/delivery/originals/ and they must be the genuine files
as shot -- not frames pulled from the finished video. Without them the
disclosure page will not publish, and the build refuses rather than shipping a
page that claims to show originals and does not.
