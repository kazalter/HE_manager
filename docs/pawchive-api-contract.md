# Pawchive public API contract (verified 2026-09-27)

This records observed public behavior for the HE Manager adapter. The site's
OpenAPI document is embedded in `https://pawchive.pw/api/swagger_schema` and
declares `https://pawchive.pw/api/v1` as its server. Only public endpoints are
used. No Pawchive account cookie or source-platform credential is accepted.

## Metadata

| Operation | Public endpoint | Observed behavior |
| --- | --- | --- |
| Recent/search | `GET /posts?q={query}&o={offset}` | JSON array; `q` has minimum length 3; offset steps by 50. Both parameters can be omitted. |
| Creator posts | `GET /{service}/user/{creator_id}?q={query}&tag={tag}&o={offset}` | JSON array; 50 items observed at offset 0. `tag` is documented only for this scope. |
| Creator profile | `GET /{service}/user/{creator_id}/profile` | Creator display name and stable service/ID. |
| Post detail | `GET /{service}/user/{creator_id}/post/{post_id}` | JSON object with `file` (main file), ordered `attachments`, `tags`, and metadata. |

The global `/creators` endpoint returns the entire creator set and its own API
description warns against loading it in the Swagger browser. HE Manager does
not use it for global creator search. Creator scope is entered from a post card.

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

On the Linux host, direct TCP to `file.pawchive.pw:443` timed out while the
existing mihomo proxy on the HE Manager Docker network gateway
(`172.19.0.1:7897`) delivered a `206` byte range. Set
`HE_PAWCHIVE_PROXY=http://172.19.0.1:7897` in that host's Compose `.env`.
The adapter uses HTTP CONNECT only for the fixed file hostname and TLS still
authenticates that upstream hostname. The API and thumbnail CDN use direct
connections. This address is deployment-specific;
Windows development can leave the setting empty or supply its own local proxy.

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
