# Honua

Honua is a cloud-native, AI-ready geospatial platform for teams modernizing GIS infrastructure without a
big-bang rewrite. Its flagship, [honua-server](https://github.com/honua-io/honua-server), connects existing
GIS clients and AI agents to the same PostGIS-backed data through GeoServices REST, OGC APIs, OData,
STAC, tiles, gRPC, and MCP. Supported ArcGIS Pro and Esri SDK workflows connect without application
rewrites, making migration and coexistence a first-class path.

🚀 [Quickstart](https://github.com/honua-io/honua-server#quick-start) · 📖 [Documentation](https://honua.gitbook.io/honuaio/) · ✅ [Proof](https://honua.io/claims.html) · 🌐 [honua.io](https://honua.io)

Honua Server is currently pre-1.0 and under active development.

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

### Migration tools

| Repo | What it is |
|---|---|
| [honua-esri-assess](https://github.com/honua-io/honua-esri-assess) | Esri footprint assessment CLI for migration discovery |

Licensing varies by repository: `honua-server` and `honua-collect` use the Elastic License 2.0 (ELv2);
all other repositories listed here use the Apache License 2.0.

## Security

We welcome security research. See our [Security Policy](https://github.com/honua-io/.github/blob/main/SECURITY.md)
and report vulnerabilities to **security@honua.io**.

Our security posture, standards work, and self-attestations are published on our
[security page](https://honua.io/security.html).
