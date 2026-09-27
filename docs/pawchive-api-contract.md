# Pawchive public API contract (verified 2026-09-27)

This records observed Pawchive behavior used by the HE Manager adapter. The
site's OpenAPI document is embedded in `https://pawchive.pw/api/swagger_schema`
and declares `https://pawchive.pw/api/v1` as its server. Public post and media
requests remain unauthenticated; a separate allowlisted client handles the
Pawchive account login and favorite-author endpoints.

## Metadata

| Operation | Public endpoint | Observed behavior |
| --- | --- | --- |
| Recent/search | `GET /posts?q={query}&o={offset}` | JSON array; `q` has minimum length 3; offset steps by 50. Both parameters can be omitted. |
| Creator posts | `GET /{service}/user/{creator_id}?q={query}&tag={tag}&o={offset}` | JSON array; 50 items observed at offset 0. `tag` is documented only for this scope. |
| Creator profile | `GET /{service}/user/{creator_id}/profile` | Creator display name and stable service/ID. |
| Post detail | `GET /{service}/user/{creator_id}/post/{post_id}` | JSON object with `file` (main file), ordered `attachments`, `tags`, and metadata. |

The global `/creators` endpoint returns the entire creator set and its own API
description warns against loading it in the Swagger browser. HE Manager does
not load that full set. Keyword author search groups public post-search results;
a creator profile URL or `service/ID` can also be entered directly.

## Pawchive account favorites

The account flow uses the Pawchive login page (`GET /account/login` followed by
`POST /account/login`) and the site's account-favorites API
(`GET /api/v1/account/favorites?type=artist`). Favorite changes use `POST` or
`DELETE /api/v1/favorites/creator/{service}/{creator_id}`. These routes were
verified in the site's login form and bundled client; an actual account login
requires the account owner.

HE Manager shows the signed-in account's favorite authors and lets the user
open each author's posts. Favorite buttons update that Pawchive account. The
password is used only for login and is not stored. Session cookies are kept in
backend process memory per HE Manager user and sent only to the fixed account
endpoints, never to media hosts. A backend restart or expired Pawchive session
requires logging in again.

The site does not expose a documented total or next cursor in these list
responses. HE Manager probes the next offset before reporting `has_more` and
wraps offsets in a scope-bound opaque cursor. As posts are inserted upstream,
offset pagination can still duplicate or omit entries; the browse session
deduplicates seen IDs but cannot provide a snapshot guarantee.

An example of the **shape** (synthetic IDs and paths):

```json
{
  "id": "post-123",
  "user": "creator-456",
  "service": "fanbox",
  "title": "Example post",
  "published": "2026-09-27T08:00:00",
  "file": {"name": "cover.jpg", "path": "/ab/cd/abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789.jpg"},
  "attachments": [{"name": "clip.mp4", "path": "/01/23/0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef.mp4"}]
}
```

The main `file` precedes `attachments` in the rendered post. The list may
describe zero attachments while `file` is present. Some list `file.name`
values describe a video while `file.path` is a `.jpg` preview, so the actual
path extension and response media type determine playability. Duplicate paths
are collapsed while preserving first occurrence.

## Media

Post HTML links files at `https://file.pawchive.pw/data{path}` and thumbnails
at `https://img.pawchive.pw/thumbnail/data{path}`. The adapter constructs these
fixed-host URLs from validated path components; upstream URLs are never passed
through from users or JSON. It rejects redirects.

Bounded byte-range probes of one public JPEG and one MP4 returned HTTP `206`,
`Content-Range: bytes 0-1023/{size}`, the matching image/video content type,
and 1024 bytes each. The MP4 probe contained an ISO media header. This proves
range delivery for the sampled objects, not universal codec support or
permanent availability. Browser playback and other formats require separate
acceptance checks.

The media host set `Set-Cookie` on responses; the HE Manager proxy must neither
forward that header to clients nor send HE Manager Authorization/Cookie headers
upstream. Requests are unauthenticated. HTTP 403 and 429 stop or pause work;
the adapter does not bypass access controls.

Configure the shared HTTP proxy under **偏好设置 → 外部收藏代理** when the
Pawchive hosts are not reachable directly. The same setting is used for
Pawchive API, account, thumbnail, and media requests as well as the other
external favorites integrations. Pawchive requests use HTTP CONNECT to fixed
hosts, and TLS still authenticates each upstream hostname. Windows development
can use a Windows-accessible HTTP proxy or leave the setting empty when direct
access works.

## Supported capability matrix

| Capability | Status |
| --- | --- |
| Recent posts, keyword search, creator posts, details | Verified public endpoints |
| Creator-scoped tag filtering | Documented; only enable in creator scope |
| Global tag filtering, global creator search, server media-type filter | Not available from verified contract |
| JPEG and MP4 range delivery | Verified on one public sample each |
| HLS/DASH, audio, archives, PDF, model files | Outside initial playback/download scope |

## Reproducible checks

Inspect the embedded `swagger_spec` in the Swagger HTML, then request the
metadata paths above with no cookies. For media, use `Range: bytes=0-1023`
and cap the received body. These checks deliberately avoid keeping source
content in the repository.

## Repository baseline before implementation

The local clone matched `da59c589fb37039700c22966ed0a1f8d3efd5449`
and the Linux deployment tree was clean at the same commit. The existing Web
build passed. The unmodified Web test command had two failing suites on the
local Node runtime: `auth.test.ts` and `e2e-workflow.test.ts` could not read
`localStorage`; the E2E flow also attempted an unavailable localhost:3000
server. Five other suites (16 tests) passed. These are baseline environment
failures, not Pawchive regressions. The existing backend suite had not yet
been run in an isolated environment at this checkpoint.
