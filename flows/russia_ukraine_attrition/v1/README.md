# russia_ukraine_attrition — v1

**Request:** Build a Russia/Ukraine war attrition dashboard. Pull the daily Russian-loss series (personnel + equipment) and the Oryx per-model visual-confirmation register from the public PetroIvaniuk/2022-Ukraine-Russia-War-Dataset GitHub feed, join them on date, and emit one Hyper extract that supports trajectory analysis: cumulative-by-class, 30-day rolling, week-over-week %change, and recent-mix vs lifetime-mix.

## Sources

- **REST API** (`json`): https://raw.githubusercontent.com/PetroIvaniuk/2022-Ukraine-Russia-War-Dataset/main/data/russia_losses_personnel.json
- **REST API** (`json`): https://raw.githubusercontent.com/PetroIvaniuk/2022-Ukraine-Russia-War-Dataset/main/data/russia_losses_equipment.json
- **REST API** (`json`): https://raw.githubusercontent.com/PetroIvaniuk/2022-Ukraine-Russia-War-Dataset/main/data/russia_losses_equipment_oryx.json

## Transformations

- **join**: Personnel + Equipment by Date

## Outputs

- `russia_ukraine_losses_daily` (published data source on Tableau Server, project `11 - Russia Ukraine War Attrition`)
- `russia_ukraine_losses_oryx_register` (published data source on Tableau Server, project `11 - Russia Ukraine War Attrition`)

## Refresh cadence

`daily`

## Sample output

- `sample_output/russia_ukraine_losses_daily.hyper`
- `sample_output/russia_ukraine_losses_oryx_register.hyper`

Real output included because this flow's source is open-source / public.
## Reproduce

```bash
python3 -m skill.scripts.run_loop \
    --spec flows/russia_ukraine_attrition/v1/spec.json \
    --flow-name russia_ukraine_attrition
```

