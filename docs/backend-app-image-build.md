# Building an application-only backend update

The Linux backend image contains large CPU machine-learning dependencies. A full
`docker compose build` can invalidate the dependency cache when the mutable
Python base tag changes, then download and rebuild those dependencies. On a
small host, unpacking those layers can also compete with the running services.

For changes limited to files under `backend/app`, use the existing local image
as a base and build a small application layer:

```sh
./scripts/build_backend_app_update.sh he-manager-backend:latest he-manager-backend:app-update
```

The script checks the current requirements against the base image and refuses
if they differ. It builds without network access and does not restart services
or retag the production image. Test the candidate, then tag it as
`he-manager-backend:latest` and run `docker compose up -d --no-build backend`
when appropriate. Keep the previous image under a separate rollback tag first.
The script intentionally uses Docker's deprecated legacy builder because the
current host's BuildKit/containerd snapshotter had to unpack large local image
layers; verify an alternative when Docker removes that builder. This shortcut
is not suitable for deleted application files (overlay COPY does not remove old
files), or for changes to dependencies, system packages, the Dockerfile,
`deploy/hermes`, or deployment scripts: use and validate a full build for those.
