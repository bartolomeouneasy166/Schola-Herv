# Sample Data

This folder contains sample data files used for testing and demonstration.

| File | Description |
|------|-------------|
| `hep_scimago.xlsx` | SCImago Journal Rank data filtered for High Energy Physics journals. Used by the `survey` command to enrich papers with journal quartiles and impact factors. |
| `hep_test.xlsx` | Small test dataset for HEP papers. |

## Using SCImago Data with the Survey Command

```bash
schola-herv survey \
  -k "high energy physics" \
  --max 100 \
  --excel-output hep_survey.xlsx \
  --pdf-folder ./pdfs \
  --scimago-csv data/hep_scimago.xlsx
```
