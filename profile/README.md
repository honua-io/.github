# Honua

Honua is a cloud-native, AI-ready geospatial platform for teams modernizing GIS infrastructure without a
big-bang rewrite. Its flagship, [honua-server](https://github.com/honua-io/honua-server), connects existing
GIS clients and AI agents to the same PostGIS-backed data through GeoServices REST, OGC APIs, OData,
STAC, tiles, gRPC, and MCP. Supported ArcGIS Pro and Esri SDK workflows connect without application
rewrites, making migration and coexistence a first-class path. Import existing ArcGIS services into PostGIS,
migrate GeoServer catalogs, and move supported workflows service by service.

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
| [honua-sdk-js](https://github.com/honua-io/honua-sdk-js) | Typed multi-protocol clients with MapLibre, Cesium, and kepler.gl integrations, ArcGIS compatibility, and an MCP server |
| [honua-sdk-python](https://github.com/honua-io/honua-sdk-python) | Geoprocessing-focused SDK for ArcPy migration, GeoPandas/raster workflows, and typed data/admin access |
| [honua-sdk-dotnet](https://github.com/honua-io/honua-sdk-dotnet) | DI-ready protocol and admin clients with geometry and offline sync |
| [honua-mobile](https://github.com/honua-io/honua-mobile) | .NET MAUI SDK for offline field collection, GeoPackage storage, dynamic forms, and background sync |
| [honua-collect](https://github.com/honua-io/honua-collect) | Offline-first mobile field data collection app |

### Open standards & benchmarks (vendor-neutral)

| Repo | What it is |
|---|---|
| [geospatial-grpc](https://github.com/honua-io/geospatial-grpc) | Open gRPC protocol standard for geospatial services |
| [geospatial-mcp](https://github.com/honua-io/geospatial-mcp) | Open geospatial MCP standard |
| [geobench](https://github.com/honua-io/geobench) | Open benchmark suite for geospatial servers |

### Migration tools

| Tool | What it does |
|---|---|
| [honua-esri-assess](https://github.com/honua-io/honua-esri-assess) | Esri footprint assessment CLI for migration discovery |
| [honua-migrate for JavaScript](https://github.com/honua-io/honua-sdk-js/blob/trunk/docs/migration-honua-maplibre.md) | Scan ArcGIS JavaScript applications and apply safe Honua/MapLibre codemods |
| [honua-migrate for Python](https://github.com/honua-io/honua-sdk-python/blob/trunk/docs/honua-gp/codemod-translation-coverage.md) | Scan and translate ArcPy scripts; classify Python and ModelBuilder toolboxes |
| [ArcGIS service import](https://github.com/honua-io/honua-server/blob/trunk/docs/guides/publish/import-from-arcgis-services.md) | Discover ArcGIS Server or ArcGIS Online services, copy features into PostGIS, and publish Honua layers |
| [GeoServer migration](https://github.com/honua-io/honua-server/blob/trunk/docs/guides/migrate/from-geoserver.md) | Scan catalogs, dry-run and apply supported metadata and styles, then repoint WMS/WFS clients |

Licensing varies by repository: `honua-server` and `honua-collect` use the Elastic License 2.0 (ELv2);
all other repositories listed here use the Apache License 2.0.

## Security

We welcome security research. See our [Security Policy](https://github.com/honua-io/.github/blob/main/SECURITY.md)
and report vulnerabilities to **security@honua.io**.

Our security posture, standards work, and self-attestations are published on our
[security page](https://honua.io/security.html).
