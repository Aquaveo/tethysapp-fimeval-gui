# Reducing cold start

Measured cold start of a fimeval web pod (image already on the node):

| Phase | Time |
| --- | --- |
| Schedule + wait-for-db init | ~5s |
| Image pull | ~25s (656 MB, pulled every start) |
| App boot + readiness | ~15s |

Image pull dominates, and it happens on every pod start. This matters most for
scale-to-zero (KEDA), where a wake-up lands on a possibly fresh node.

## Already done (chart 0.1.3)

The `tethys-app` chart adds a `startupProbe` (3s period) and a fast `readinessProbe`,
so a pod is marked Ready as soon as it responds instead of on a 10s grid. This alone
took the ready time from ~34s to ~18s on a warm node.

## The image-pull fix (this is the big one)

The pod uses `pullPolicy: Always`, which forces a registry round trip on every start
even when the image is already on the node. Fix it with immutable tags plus a cached
pull policy, and pull from ECR in-region instead of Docker Hub.

1. Build and push to ECR with an immutable tag (git sha), not `latest`:

   ```bash
   REG=456531024327.dkr.ecr.us-east-1.amazonaws.com
   TAG=$(git rev-parse --short HEAD)
   aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $REG
   docker build -t $REG/tethysapp-fimeval-gui:$TAG .
   docker push $REG/tethysapp-fimeval-gui:$TAG
   ```

   Create the ECR repo once (admin): `aws ecr create-repository --repository-name tethysapp-fimeval-gui`.

2. Point the deploy at that image and switch the pull policy in the environment overlay:

   ```yaml
   tethys-app:
     image:
       repository: 456531024327.dkr.ecr.us-east-1.amazonaws.com/tethysapp-fimeval-gui
       tag: <git-sha>
       pullPolicy: IfNotPresent
   ```

   `IfNotPresent` is only safe with an immutable tag; with `latest` a node keeps a stale
   image. So the tag and the pull policy change together. A warm node then skips the pull
   entirely (~25s to ~0).

3. The EKS node role needs ECR pull permission (`AmazonEC2ContainerRegistryReadOnly` or
   equivalent). Usually already present on the Karpenter/MNG node role.

## Further gains (infra, optional)

- SOCI lazy pulling on the nodes: the container starts before the full image is pulled.
- A small warm node pool so a scale-from-zero wake-up lands on a node that already has
  the image.
- Fewer uvicorn workers and lazy-importing the heavy geo libs (gdal, rasterio, geemap)
  in the app so Django boot is faster.
