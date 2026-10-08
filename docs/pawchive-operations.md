# Pawchive module operations

The Web entry is **外部下载 → Pawchive** (`/#/external/pawchive`). Browsing reads
public metadata on demand and does not write `Media` rows. A user must confirm
an attachment, post, or selected-post download before files are stored under
`HE_PAWCHIVE_DOWNLOAD_ROOT/pawchive/{service}/{creator_id}/{post_id}`.

On the Pawchive page, sign in to the Pawchive account to see its favorite
authors. Select an author to browse their posts; search results can also be
grouped by author, and an author page URL or `service/creator_id` opens that
author directly. Favorite buttons update the Pawchive account. The password is
used only for login. Session cookies stay in backend memory per HE Manager user
and are sent only to the fixed Pawchive account endpoints. After a backend
restart or expired session, sign in again.

## Linux Compose configuration

Set these values in `/opt/stacks/he-manager/.env` before restarting the stack:

```dotenv
HE_PAWCHIVE_ENABLED=1
HE_PAWCHIVE_DOWNLOAD_ROOT=/mnt/hdd/hhh
HE_PAWCHIVE_STORAGE_SENTINEL=.mounted
```

Configure an HTTP proxy through **偏好设置 → 外部收藏代理** if Pawchive is not
reachable directly. That setting is shared with WNACG and X, and covers all
Pawchive account, metadata, thumbnail, and media requests. Windows development
can use its own local HTTP proxy.

The download directory must exist, be writable from the backend container,
and remain mounted. Create `/mnt/hdd/.mounted` on the mounted disk once. The
Pawchive storage check requires that marker before download and again before
the final file move, so a missing mount cannot fall back to the system disk.
Keep `/mnt/hdd` mounted before starting downloads.

Media and pagination references are HMAC-signed and valid for 12 hours. The
signing key comes from `HE_PAWCHIVE_STREAM_SECRET` when set; otherwise the
backend generates `pawchive_stream.key` next to the database (`/data` in
Compose) on first start and reuses it, so restarts and redeploys do not break
media in pages that are already open. Deleting that file invalidates open
references once, like rotating the secret.

## Verification

After `docker compose up -d --build`, check:

1. Both containers report healthy; `/healthz` responds.
2. An authenticated `GET /external/pawchive/capabilities` returns the provider
   matrix and `GET /external/pawchive/posts` returns posts.
3. Open an image and seek within a video; the media route should preserve `206`
   and `Content-Range` when the upstream supports ranges.
4. Download one small image, then verify its task completes and the linked
   ordinary media item opens in the library. Repeating it should report an
   already downloaded attachment without a duplicate media row.
5. Sign in to Pawchive and confirm the account's favorite authors appear. Open
   an author, search for an author, and add or remove a favorite.

Media URLs use short-lived signed references and the same HE Manager access
token as other binary routes. A reference's expiry is rounded up to a 6-hour
boundary, so it stays valid for 12 to 18 hours and the same file keeps the
same URL across list refreshes. Image responses allow private browser caching
for one day because Pawchive file paths are content hashes. Video responses
keep a 60-second lifetime. Do not place the token or source media URL in
logs. The nginx media location disables access logs and response buffering.

## Temporary image cache

Pawchive full-resolution images and preview thumbnails are cached on the
server after a complete, authenticated 200 response. The cache key is the
validated source path and media kind, not the short-lived signed URL. Videos
and partial media responses are streamed without being cached. Cached images
still pass through HE Manager authentication and signed-reference validation.

Whole-image requests share one upstream download per file. The bytes are
written to the cache file and streamed to every waiting request as they
arrive. If every reader disconnects, the download continues for 15 seconds so
a viewer retry or a reopened post can pick it up; after that it stops and the
partial file is removed. The `X-Pawchive-Cache` response header reports `HIT`
(served from cache) or `SHARED` (joined or started a download).

Upstream image downloads run in two lanes: at most 4 originals
(`HE_PAWCHIVE_IMAGE_CONCURRENCY`) and 6 thumbnails
(`HE_PAWCHIVE_PREVIEW_CONCURRENCY`) at a time. Separate lanes keep a page of
covers from delaying the original open in the viewer. Media requests use their
own worker threads, so slow media cannot stall other API endpoints. API and
media requests reuse idle keep-alive connections, including proxy tunnels, for
up to 20 seconds instead of paying a new connection and TLS handshake per image.

The web viewer loads originals with a 20-second inactivity timeout rather than
a total time limit. A large image that is still arriving keeps loading, with
its progress shown, and only a 20-second pause in received data counts as a
stall.
Some originals are missing on the source file host even though their
thumbnails still exist. When an original returns 404, the viewer shows the
thumbnail with a notice instead of retrying.

The backend uses /mnt/hdd/.he-manager/pawchive-cache and requires
/mnt/hdd/.mounted. It removes only that cache directory when the backend
starts; a browser refresh does not clear it. If the mount or sentinel is
missing, the cache is disabled and media continues to stream from Pawchive.
The original-image limit defaults to 10 GiB and the thumbnail limit to
1 GiB. Least-recently-used files are removed when either limit is reached.
Set HE_PAWCHIVE_IMAGE_CACHE_BYTES or HE_PAWCHIVE_PREVIEW_CACHE_BYTES on the
backend service to change these limits. No cache files are stored on the
system disk.

## Failure and recovery

- `PROVIDER_DISABLED`: set `HE_PAWCHIVE_ENABLED=1` and recreate the backend.
- `STORAGE_UNAVAILABLE`: check the mount, free space, and configured directory.
- `UPSTREAM_UNAVAILABLE`: check the upstream and the mihomo route from inside
  the Docker network. Do not change the adapter to accept arbitrary URLs.
- `RATE_LIMITED` or `ACCESS_RESTRICTED`: the current attachment fails and
  subsequent attachments stop. Retry later if the public endpoint allows it.
- An interrupted task stays visible after a backend restart. Retry checks the
  current public post detail and reuses an existing verified file when safe.

The source identity tables are `pawchive_posts` and `pawchive_attachments`.
They are created idempotently at startup. The ordinary media library retains
`source_url`, `source_site=pawchive`, and artist metadata. Back up
`data/library.db` with SQLite's online backup before deployment; keep the
existing data volume and media mount in place during redeployments.

## 2026-09-27 deployment record

- The production database was backed up online before deployment; the backup
  and post-migration database both passed `PRAGMA integrity_check`.
- The backend and frontend containers were healthy. The production adapter
  returned 50 recent posts and three playable attachments on a public sample;
  image and video proxy samples each returned `206` with a 1024-byte range.
- A real image download in a disposable container completed, created one
  ordinary media row, and a repeated submission returned `already_downloaded`.
  This did not add sample media to the production library.
- The existing backend image `he-manager-backend:fixed-20260926` supplied the
  same pinned dependencies while the application layer was rebuilt. A full
  Dockerfile rebuild stalled on downloading the PyTorch wheel, so this deploy
  used the application-layer image and `docker compose up -d --no-build`.
- An isolated rollback rehearsal started the previous image with a current
  database snapshot and returned a healthy `/healthz`; production remained on
  the new image.
- Backend pytest: 148 passed. Frontend Vitest: 23 passed. Production build
  passed. Chrome layout and viewer close interaction passed at 320, 390, 768,
  and 1440 pixels using synthetic API responses; no horizontal page overflow
  was observed. [Final Linux and Windows CI](https://github.com/kazalter/HE_manager/actions/runs/36313940700)
  passed on the final application code.
