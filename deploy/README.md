# Deploying FIMeval GUI

Single-app Tethys instance deployed with the generic
[`tethys-app`](https://github.com/Aquaveo/tethysapp-helm-library) chart.

## Prerequisites

- The Dask Kubernetes operator installed in the cluster.
- IAM role `fimeval-s3-irsa` created from `deploy/iam/` (trust + policy).
- A `fimeval-secrets` Secret with `TETHYS_SECRET_KEY`, `TETHYS_DB_PASSWORD` (and HydroShare OAuth keys).
- A wildcard DNS + TLS covering `fimeval.tethys.ciroh.org` on the shared ALB.

## Install

```bash
helm install fimeval \
  <path-to>/tethysapp-helm-library/charts/tethys-app \
  -n fimeval --create-namespace \
  -f deploy/values-fimeval.yaml
```

The `tethys-app` chart deploys only the app. FIMeval's compute runs on Dask, which this app owns: once the release is up, apply the cluster (it reuses the app's `fimeval-dask` service account for IRSA).

```bash
kubectl apply -f deploy/kubernetes/dask-cluster.yaml
```

Order matters: `helm install` must run first so the `fimeval-dask` service account exists. Applied before it, the Dask pods fail admission because their service account is missing.

The scheduler image in `deploy/kubernetes/dask-cluster.yaml` must match `image` in `deploy/values-fimeval.yaml`; workers need the same app code as the web pod. Bump both together when pinning a version.

## Post-deploy Tethys settings

Set once (admin or provision hook), since these are app settings, not chart values:

- `s3_bucket` = the results bucket; leave `minio_access_key`/`minio_secret_key` blank to use IRSA.
- Register a Dask scheduler, then assign it to the app's `dask_primary` scheduler setting:

```bash
tethys schedulers create dask -n fimeval_primary \
  --host fimeval-dask-scheduler.fimeval.svc.cluster.local --port 8786
```

The scheduler name (`fimeval_primary`) and the app setting (`dask_primary`) are different things. After creating the scheduler, open Tethys admin, go to the FIMeval app's settings, and set the `dask_primary` Dask scheduler setting to `fimeval_primary`. Jobs will not submit until this link is set.
