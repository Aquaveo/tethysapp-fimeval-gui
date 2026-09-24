# Deploying FIMeval GUI

`deploy/chart` is a self-contained Helm chart: it pulls the generic
[`tethys-app`](https://github.com/Aquaveo/tethysapp-helm-library) chart from GHCR
and adds FIMeval's Dask cluster. It carries no environment specifics; those come
from an overlay values file passed with `-f`.

## Prerequisites

- The Dask Kubernetes operator installed in the cluster.
- An IAM role for IRSA created from `deploy/iam/` (fill the `<...>` placeholders), if using AWS S3 via IRSA.
- A `fimeval-secrets` Secret with `TETHYS_SECRET_KEY`, `TETHYS_DB_PASSWORD` (and HydroShare OAuth keys).
- A Postgres reachable from the cluster, set in the overlay.
- DNS and TLS for the app host (see the overlay).

## Install

```bash
helm dependency build deploy/chart
helm install fimeval deploy/chart \
  -n fimeval --create-namespace \
  -f <overlay>/values.yaml
```

The chart installs the app, its service account, and the Dask cluster together;
the operator scales workers from zero on demand.

## Overlays

The generic `deploy/chart/values.yaml` leaves environment fields blank
(`externalDatabase.host`, `serviceAccount.roleArn`, `ingress.*`,
`dask.worker.nodeSelector`). Each environment supplies them in its own overlay.
The CIROH portal overlay lives in the `tethysportal-ciroh` repo at
`deploy/fimeval/values.yaml`. App values are nested under the `tethys-app:` key;
Dask values are top-level under `dask:`.

## Post-deploy Tethys settings

Set once (admin or provision hook), since these are app settings, not chart values:

- `s3_bucket` = the results bucket; leave `minio_access_key`/`minio_secret_key` blank to use IRSA.
- Keys are namespaced under `fimeval/` by default; override per environment with the `FIMEVAL_S3_KEY_PREFIX` env var (set it to empty for a dedicated bucket), and keep the IAM policy prefix in sync.
- Register a Dask scheduler, then assign it to the app's `dask_primary` scheduler setting:

```bash
tethys schedulers create dask -n fimeval_primary \
  --host fimeval-dask-scheduler.fimeval.svc.cluster.local --port 8786
```

The scheduler name (`fimeval_primary`) and the app setting (`dask_primary`) are different things. After creating the scheduler, open Tethys admin, go to the FIMeval app's settings, and set the `dask_primary` Dask scheduler setting to `fimeval_primary`. Jobs will not submit until this link is set.
