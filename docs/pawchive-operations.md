# Pawchive module operations

The Web entry is **外部下载 → Pawchive** (`/#/external/pawchive`). Browsing reads
public metadata on demand and does not write `Media` rows. A user must confirm
an attachment, post, or selected-post download before files are stored under
`HE_PAWCHIVE_DOWNLOAD_ROOT/pawchive/{service}/{creator_id}/{post_id}`.

## Linux Compose configuration

Set these values in `/opt/stacks/he-manager/.env` before restarting the stack:

```dotenv
HE_PAWCHIVE_ENABLED=1
HE_PAWCHIVE_PROXY=http://172.19.0.1:7897
HE_PAWCHIVE_DOWNLOAD_ROOT=/mnt/hdd/hhh
```

The proxy is the existing mihomo HTTP listener reachable from the HE Manager
Docker network on this host. Only `file.pawchive.pw` downloads/streams use it;
public metadata and thumbnail calls use direct TLS. Recheck the Docker gateway
address if Compose recreates the network. For Windows development, set a
Windows-accessible HTTP proxy if the file CDN needs it, or leave it empty when
direct access works. No source-platform credentials are needed.

The download directory must exist, be writable from the backend container,
and remain mounted. The storage guard refuses writes when it detects an
unavailable mount. Keep `/mnt/hdd` mounted before starting downloads.

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

Media URLs use short-lived signed references and the same HE Manager access
token as other binary routes. Do not place the token or source media URL in
logs. The nginx media location disables access logs and response buffering.

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
