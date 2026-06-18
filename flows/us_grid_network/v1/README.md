# us_grid_network — v1

**Request:** Pull the US high-voltage transmission grid (>=230 kV) from the HIFLD authoritative ArcGIS feed, treat each line as an undirected edge between SUB_1 and SUB_2 substations, and run network analysis: degree / betweenness / eigenvector / pagerank / closeness centrality plus Fruchterman-Reingold layout coordinates seeded by geographic positions. Publish the enriched endpoint table to a new 'Energy Infrastructure' project on Tableau Server so analysts can visualize the network topology in Tableau with x/y coordinates and centrality-driven node attributes.

## Sources

- **REST API** (`arcgis_features`): https://services2.arcgis.com/LYMgRMwHfrWWEg3s/arcgis/rest/services/HIFLD_US_Electric_Power_Transmission_Lines/FeatureServer/0/query

## Transformations

- **graph_analysis**: Builds an undirected NetworkX graph from transmission lines keyed by SUB_1 -> SUB_2. Computes Fruchterman-Reingold spring layout (x/y coords) seeded from each substation's geographic mean across all incident edges. Adds node-level metrics: degree_centrality, betweenness_centrality, eigenvector_centrality, pagerank, closeness_centrality. Emits two rows per edge (one per endpoint) so Tableau can render lines via Detail/path-order on edge_id.

## Outputs

- `US Grid Network (Backbone)` (published data source on Tableau Server, project `Energy Infrastructure`)

## Refresh cadence

`monthly`

## Sample output

- `sample_output/US Grid Network (Backbone).hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/us_grid_network/v1/spec.json \
    --flow-name us_grid_network
```

