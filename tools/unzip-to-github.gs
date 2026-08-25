/**
 * Unzip the OpenArt archive in Google Drive and push the clips straight to
 * GitHub. Runs entirely inside Google's servers, so neither of the two walls
 * that stopped the transfer applies:
 *
 *   - the Drive connector caps downloads at 10 MB and the archive is 300 MB
 *   - drive.google.com is refused by the build environment's egress policy
 *
 * Nothing is downloaded to your device. The archive is expanded in place and
 * each video is committed to the branch one file at a time.
 *
 * WORTH KNOWING BEFORE YOU START: Apps Script caps how large a blob it will
 * hold in memory, and a 300 MB archive is close to that ceiling. This may
 * simply refuse to expand it. If it does, the script says so and tells you the
 * fallback -- it is not something to debug. Run dryRun() first: it expands the
 * archive and lists the contents without pushing anything, so you find out in
 * thirty seconds rather than after setting up a token.
 *
 * SETUP (about two minutes)
 *   1. script.google.com  ->  New project
 *   2. Paste this whole file over whatever is there
 *   3. Fill in GITHUB_TOKEN below
 *      github.com/settings/tokens  ->  Fine-grained token
 *      Repository access: only farmfitusa888-gif/Fly-Through
 *      Permissions: Contents = Read and write.  Nothing else.
 *   4. Run  ->  dryRun  first, to confirm the archive expands at all
 *   5. Run  ->  main.  Authorise when asked (it is your own Drive).
 *   6. Delete the token when the run finishes. It is one job, not a standing key.
 *
 * The token sits in a script only you can open. It is still a credential:
 * scope it to this one repository, and revoke it afterwards.
 */

var GITHUB_TOKEN = '';                       // <- paste, run, then revoke
var OWNER = 'farmfitusa888-gif';
var REPO = 'Fly-Through';
var BRANCH = 'claude/drone-pov-renderer-business-5usm0h';
var DEST = 'samples/inbox';                  // where the clips land in the repo
var ZIP_NAME = 'openart-download (3).zip';

// GitHub's API rejects a blob over 100 MB and gets unhappy well before that.
// Every clip here is 2-6 MB, so anything larger is a sign the archive holds
// something we did not expect -- report it rather than push it.
var MAX_BYTES = 50 * 1024 * 1024;

function main() {
  if (!GITHUB_TOKEN) {
    throw new Error('Set GITHUB_TOKEN first. See the SETUP notes at the top.');
  }
  var zip = findZip_();
  Logger.log('Archive: %s (%s MB)', zip.getName(),
             (zip.getSize() / 1048576).toFixed(0));

  // Apps Script has a ceiling on how large a blob it will hold in memory, and
  // a 300 MB archive is near or past it depending on the account. If this
  // throws, it is not a bug in the script and there is nothing to debug -- take
  // the fallback and move on rather than spending an hour here.
  var entries;
  try {
    entries = Utilities.unzip(zip.getBlob());
  } catch (err) {
    throw new Error(
      'Apps Script could not hold this archive in memory (' + err.message + ').\n' +
      'This is a platform limit, not a fault in the script.\n\n' +
      'Fallback, and it is quicker anyway:\n' +
      '  1. Download the zip to a computer and unzip it there\n' +
      '  2. github.com -> the repo -> branch ' + BRANCH + '\n' +
      '  3. ' + DEST + ' -> Add file -> Upload files -> drag every .mp4 in\n' +
      'Each clip is 2-6 MB, far inside GitHub\'s limits. Only the archive was\n' +
      'ever too big -- the files inside it never were.');
  }
  Logger.log('Entries inside: %s', entries.length);

  var pushed = 0, skipped = 0, failed = 0;
  for (var i = 0; i < entries.length; i++) {
    var blob = entries[i];
    // Zips carry directory paths; the repo wants a flat basename.
    var name = blob.getName().split('/').pop();
    if (!name || name.charAt(0) === '.') { continue; }
    if (!/\.(mp4|mov|m4v|webm)$/i.test(name)) { skipped++; continue; }

    var bytes = blob.getBytes();
    if (bytes.length > MAX_BYTES) {
      Logger.log('SKIP  %s is %s MB, larger than expected',
                 name, (bytes.length / 1048576).toFixed(0));
      failed++;
      continue;
    }
    // A .mov container from OpenArt is still H.264; name it .mp4 so the
    // pipeline's matcher and ffmpeg both see what they expect.
    var target = name.replace(/\.(mov|m4v|webm)$/i, '.mp4');
    try {
      var result = putFile_(DEST + '/' + target, bytes);
      Logger.log('%s  %s  (%s MB)', result, target,
                 (bytes.length / 1048576).toFixed(1));
      pushed++;
    } catch (err) {
      Logger.log('FAIL  %s  %s', target, err.message);
      failed++;
    }
  }
  Logger.log('---');
  Logger.log('pushed %s, non-video skipped %s, failed %s', pushed, skipped, failed);
  Logger.log('Now tell Claude to pull the branch.');
}

function findZip_() {
  var byName = DriveApp.getFilesByName(ZIP_NAME);
  if (byName.hasNext()) { return byName.next(); }
  // Fall back to any zip in a folder called FLY THROUGH, so a renamed
  // download still works.
  var folders = DriveApp.getFoldersByName('FLY THROUGH');
  while (folders.hasNext()) {
    var files = folders.next().getFiles();
    while (files.hasNext()) {
      var f = files.next();
      if (/\.zip$/i.test(f.getName())) { return f; }
    }
  }
  throw new Error('No zip found. Check ZIP_NAME matches the file in Drive.');
}

/**
 * Create or update one file on the branch.
 *
 * GitHub requires the existing blob sha to overwrite a file, so this reads
 * first. Without it a re-run fails on every file that already landed, which
 * turns a partial run into something you cannot simply repeat.
 */
function putFile_(path, bytes) {
  var api = 'https://api.github.com/repos/' + OWNER + '/' + REPO +
            '/contents/' + encodeURI(path);
  var headers = {
    Authorization: 'Bearer ' + GITHUB_TOKEN,
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28'
  };

  var existing = UrlFetchApp.fetch(api + '?ref=' + encodeURIComponent(BRANCH), {
    method: 'get', headers: headers, muteHttpExceptions: true
  });
  var sha = null;
  if (existing.getResponseCode() === 200) {
    sha = JSON.parse(existing.getContentText()).sha;
  }

  var payload = {
    message: 'Add ' + path.split('/').pop() + ' from the OpenArt archive',
    content: Utilities.base64Encode(bytes),
    branch: BRANCH
  };
  if (sha) { payload.sha = sha; }

  var res = UrlFetchApp.fetch(api, {
    method: 'put', headers: headers, contentType: 'application/json',
    payload: JSON.stringify(payload), muteHttpExceptions: true
  });
  var code = res.getResponseCode();
  if (code !== 200 && code !== 201) {
    // Trim the body: GitHub echoes a lot, and a token must never reach a log.
    throw new Error('HTTP ' + code + ' ' +
                    res.getContentText().substring(0, 200));
  }
  return sha ? 'UPDATED' : 'ADDED  ';
}

/** Optional: list what is in the archive without pushing anything. */
function dryRun() {
  var zip = findZip_();
  Logger.log('Archive: %s (%s MB)', zip.getName(),
             (zip.getSize() / 1048576).toFixed(0));
  var entries;
  try {
    entries = Utilities.unzip(zip.getBlob());
  } catch (err) {
    Logger.log('Could not expand the archive here: %s', err.message);
    Logger.log('That is the platform limit. Unzip on a computer and drag the');
    Logger.log('.mp4 files into %s on branch %s instead.', DEST, BRANCH);
    return;
  }
  Logger.log('%s entries', entries.length);
  for (var i = 0; i < entries.length; i++) {
    var b = entries[i];
    Logger.log('  %s  %s KB', b.getName(),
               (b.getBytes().length / 1024).toFixed(0));
  }
}
