# Live2D viewer integration

This is the L2Dviewer frontend integrated with HE Manager. Model assets are stored separately at `/mnt/hdd/azurlane-l2dviewer/models` and served by the authenticated HE Manager backend.

To rebuild the viewer, run `npm ci` and `npm run build:manager` in this directory, then rebuild the HE Manager frontend. The generated viewer is copied to `frontend/public/l2d`; game models are not part of the frontend build.

The viewer source is MIT licensed; the Cubism runtime and game assets retain their respective owners’ rights.
