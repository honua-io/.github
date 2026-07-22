# Honua

Honua is a cloud-native, AI-ready geospatial platform. Its flagship, [honua-server](https://github.com/honua-io/honua-server),
exposes one shared geospatial capability set through many protocol adapters — GeoServices REST
(FeatureServer / MapServer / ImageServer / Geometry / GPServer), OGC API (Features / Maps / Tiles / Processes),
classic OGC WMS/WFS/WMTS/WCS, STAC, OData v4, vector tiles (MVT/TileJSON), Terrain-RGB, MCP, and
gRPC — backed by PostGIS. Because it speaks GeoServices natively, ArcGIS Pro and Esri SDK clients
connect unmodified, making Esri migration and coexistence a first-class path.

📖 [Documentation](https://honua.gitbook.io/honuaio/) · 🌐 [honua.io](https://honua.io)

Everything here is pre-1.0 and under active development.

## Repositories

### Platform

| Repo | What it is |
|---|---|
| [honua-server](https://github.com/honua-io/honua-server) | Flagship multi-protocol geospatial server (ELv2 open core) |
| [honua-console](https://github.com/honua-io/honua-console) | Unified web console — Studio, Catalog, Operate, Share |
| [honua-helm](https://github.com/honua-io/honua-helm) | Helm chart — the Kubernetes deploy path |

### SDKs & clients

| Repo | What it is |
|---|---|
| [honua-sdk-js](https://github.com/honua-io/honua-sdk-js) | JavaScript/TypeScript SDKs + MCP server (npm) |
| [honua-sdk-python](https://github.com/honua-io/honua-sdk-python) | Python SDK |
| [honua-sdk-dotnet](https://github.com/honua-io/honua-sdk-dotnet) | .NET SDKs |
| [honua-mobile](https://github.com/honua-io/honua-mobile) | .NET MAUI mobile SDK, GeoPackage offline foundation |
| [honua-collect](https://github.com/honua-io/honua-collect) | Offline-first mobile field data collection app |

### Open standards & benchmarks (vendor-neutral)

| Repo | What it is |
|---|---|
| [geospatial-grpc](https://github.com/honua-io/geospatial-grpc) | Open gRPC protocol standard for geospatial services |
| [geospatial-mcp](https://github.com/honua-io/geospatial-mcp) | Open geospatial MCP standard |
| [geobench](https://github.com/honua-io/geobench) | Open benchmark suite for geospatial servers |

### Tools & more

| Repo | What it is |
|---|---|
| [honua-esri-assess](https://github.com/honua-io/honua-esri-assess) | Esri footprint assessment CLI for migration discovery |

Licensing varies by repository: `honua-server` and `honua-collect` use the Elastic License 2.0 (ELv2);
all other repositories listed here use the Apache License 2.0.

## Security

We welcome security research. See our [Security Policy](https://github.com/honua-io/.github/blob/main/SECURITY.md)
and report vulnerabilities to **security@honua.io**.

Our security posture, certifications, and self-attestations are published on our
trust center (see [honua.io](https://honua.io)).
