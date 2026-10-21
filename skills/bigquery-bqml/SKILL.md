---
name: bigquery-bqml
description: "Train, evaluate, explain and serve ML models inside BigQuery with BigQuery ML (GoogleSQL): classification and regression (logistic, boosted tree, random forest, DNN, AutoML), clustering (k-means), forecasting (ARIMA_PLUS, AI.FORECAST/TimesFM), recommendations (matrix factorization), anomaly detection, and Gemini/Vertex AI remote models for text generation, embeddings and vector search. Use when the user wants to predict, classify, forecast, segment, recommend, embed, or call an LLM on BigQuery data."
---

# BigQuery ML

Answer in the user's language. Use their real project, dataset, table and column names.

## Safety
- Dry-run before running anything that scans data: `bq query --dry_run --use_legacy_sql=false '...'`, and run with `--maximum_bytes_billed`.
- Never run or recommend as a first step: `CREATE OR REPLACE` on an existing table, `DROP`, `TRUNCATE`, unbounded `DELETE`/`UPDATE`, or IAM changes. Write to a new table, verify, then swap — and ask the user first.
- Use the user's real project/dataset/table names; ask for project and location if a command needs them.

`CREATE OR REPLACE MODEL` is fine for models (it does not touch tables), but say that it overwrites an existing model of the same name.

When the problem is project-wide → suggest the bq-audit skill.

## Before writing SQL, establish
1. **Task**: classify (label is BOOL/STRING/few values), regress (numeric label), cluster (no label), forecast (time series), recommend (user × item interactions), detect anomalies, or generate/embed text.
2. **Label and key columns**: the label name (often not `label`) and ID columns that must be excluded from features.
3. **Size and cost**: rows/bytes of the training query (dry run). Training is billed differently from queries — on-demand `CREATE MODEL` for built-in models costs a much higher per-TiB rate than normal queries, and DNN / boosted tree / random forest / AutoML training is billed through Vertex AI. Point the user to https://cloud.google.com/bigquery/pricing#bqml instead of quoting numbers from memory. For experiments, train on a sample (`TABLESAMPLE SYSTEM (10 PERCENT)` or a date range).
4. **Location**: the model lives in a dataset; training data and remote-model connections must be in the same location.

## Choosing a model_type
| Task | model_type | Notes |
|---|---|---|
| Binary/multiclass baseline | `LOGISTIC_REG` | Fast, cheap, interpretable. Start here. |
| Better accuracy on tabular data | `BOOSTED_TREE_CLASSIFIER` / `BOOSTED_TREE_REGRESSOR` | XGBoost. `BOOSTED_TREE` alone is **not** valid. |
| | `RANDOM_FOREST_CLASSIFIER` / `RANDOM_FOREST_REGRESSOR` | |
| | `DNN_CLASSIFIER` / `DNN_REGRESSOR`, `DNN_LINEAR_COMBINED_*` | Needs more data and tuning. |
| Hands-off best model | `AUTOML_CLASSIFIER` / `AUTOML_REGRESSOR` | Slow, most expensive; set `budget_hours`. |
| Numeric regression baseline | `LINEAR_REG` | |
| Segmentation | `KMEANS` | `num_clusters`, or omit to auto-pick; `ML.CENTROIDS`. |
| Dimensionality reduction | `PCA` | |
| Time series | `ARIMA_PLUS` (one or many series), `ARIMA_PLUS_XREG` (with covariates) | Or zero-training `AI.FORECAST` (TimesFM). |
| Recommendations | `MATRIX_FACTORIZATION` | Explicit ratings or `feedback_type='IMPLICIT'`. |
| Anomalies | `ARIMA_PLUS`, `KMEANS`, `AUTOENCODER`, `PCA` + `ML.DETECT_ANOMALIES` | |
| Text generation / embeddings | remote model over Vertex AI (Gemini, text-embedding) | See "Remote models". |

## Classification / regression

```sql
CREATE OR REPLACE MODEL `proj.ml.churn_model`
OPTIONS (
  model_type = 'BOOSTED_TREE_CLASSIFIER',
  input_label_cols = ['churned'],          -- required unless the label column is named "label"
  auto_class_weights = TRUE,               -- imbalanced labels (churn is usually rare)
  data_split_method = 'AUTO_SPLIT',        -- or 'RANDOM' + data_split_eval_fraction, or 'SEQ' + data_split_col for time-based splits
  max_iterations = 50,
  early_stop = TRUE,
  enable_global_explain = TRUE             -- needed later for ML.GLOBAL_EXPLAIN
) AS
SELECT * EXCEPT (user_id, signup_ts)        -- drop IDs and leakage columns
FROM `proj.ml.users`
WHERE snapshot_date < '2026-09-01';
```

Guidance:
- BigQuery ML already splits train/eval (`AUTO_SPLIT`). Don't add a manual split unless you also set `data_split_method` accordingly; for time-dependent data use `SEQ` on a date column to avoid leakage.
- Remove leakage features (anything only known after the outcome, e.g. `cancel_date` for churn).
- STRING columns are one-hot encoded automatically; very high-cardinality IDs hurt — exclude or bucket them.

### Feature preprocessing with TRANSFORM
Put preprocessing in the model so prediction applies the same steps automatically:
```sql
CREATE OR REPLACE MODEL `proj.ml.churn_model`
TRANSFORM (
  ML.STANDARD_SCALER(sessions_30d) OVER () AS sessions_30d,
  ML.QUANTILE_BUCKETIZE(revenue, 10) OVER () AS revenue_bucket,
  EXTRACT(DAYOFWEEK FROM last_seen) AS last_seen_dow,
  plan, country,
  churned
)
OPTIONS (model_type = 'LOGISTIC_REG', input_label_cols = ['churned'], auto_class_weights = TRUE)
AS SELECT * EXCEPT (user_id) FROM `proj.ml.users`;
```

### Hyperparameter tuning
```sql
OPTIONS (
  model_type = 'BOOSTED_TREE_CLASSIFIER',
  input_label_cols = ['churned'],
  num_trials = 20, max_parallel_trials = 4,
  hparam_tuning_objectives = ['ROC_AUC'],
  learn_rate = HPARAM_RANGE(0.01, 0.3),
  max_tree_depth = HPARAM_CANDIDATES([4, 6, 8]),
  l2_reg = HPARAM_RANGE(0, 10)
)
```
Each trial is a training run — multiply cost accordingly. Inspect with `ML.TRIAL_INFO(MODEL ...)`.

### Evaluate
```sql
SELECT * FROM ML.EVALUATE(MODEL `proj.ml.churn_model`);                         -- precision, recall, roc_auc, log_loss…
SELECT * FROM ML.CONFUSION_MATRIX(MODEL `proj.ml.churn_model`, STRUCT(0.5 AS threshold));
SELECT * FROM ML.ROC_CURVE(MODEL `proj.ml.churn_model`);                        -- pick a threshold for the business cost
SELECT * FROM ML.TRAINING_INFO(MODEL `proj.ml.churn_model`);                    -- loss per iteration, overfitting check
```
Compare against a trivial baseline (always predicting the majority class) before celebrating accuracy.

### Predict
`ML.PREDICT` returns `predicted_<label>` and, for classifiers, `predicted_<label>_probs` (ARRAY<STRUCT<label, prob>>). Don't index the array by position — select the class explicitly:
```sql
SELECT
  user_id,
  predicted_churned,
  (SELECT p.prob FROM UNNEST(predicted_churned_probs) p WHERE p.label = TRUE) AS churn_probability
FROM ML.PREDICT(MODEL `proj.ml.churn_model`,
  (SELECT * FROM `proj.ml.users_current`),
  STRUCT(0.35 AS threshold));
```
Pass-through columns (like `user_id`) are returned even though they were excluded from training.

### Explain
- Per row: `ML.EXPLAIN_PREDICT(MODEL m, (SELECT ...), STRUCT(3 AS top_k_features))`.
- Global: `ML.GLOBAL_EXPLAIN(MODEL m)` (requires `enable_global_explain = TRUE` at training).
- Tree models: `ML.FEATURE_IMPORTANCE(MODEL m)`.
- Linear models: `ML.WEIGHTS(MODEL m)`.

## Clustering
```sql
CREATE OR REPLACE MODEL `proj.ml.customer_segments`
OPTIONS (model_type = 'KMEANS', num_clusters = 5, standardize_features = TRUE, kmeans_init_method = 'KMEANS++')
AS SELECT * EXCEPT (customer_id) FROM `proj.ml.customer_features`;

SELECT * FROM ML.EVALUATE(MODEL `proj.ml.customer_segments`);   -- davies_bouldin_index (lower is better)
SELECT * FROM ML.CENTROIDS(MODEL `proj.ml.customer_segments`);
SELECT customer_id, centroid_id FROM ML.PREDICT(MODEL `proj.ml.customer_segments`, TABLE `proj.ml.customer_features`);
```
Try several `num_clusters` values and compare Davies–Bouldin plus whether centroids are explainable to the business.

## Forecasting
**No training (TimesFM foundation model):**
```sql
SELECT *
FROM AI.FORECAST(
  TABLE `proj.sales.daily`,
  data_col => 'revenue',
  timestamp_col => 'day',
  id_cols => ['store_id'],
  horizon => 30,
  confidence_level => 0.9);
```
**Trained, one model for many series:**
```sql
CREATE OR REPLACE MODEL `proj.sales.revenue_arima`
OPTIONS (
  model_type = 'ARIMA_PLUS',
  time_series_timestamp_col = 'day',
  time_series_data_col = 'revenue',
  time_series_id_col = 'store_id',      -- one model per store, trained in one statement
  horizon = 90,
  holiday_region = 'US',
  auto_arima = TRUE
) AS SELECT day, store_id, revenue FROM `proj.sales.daily`;

SELECT * FROM ML.FORECAST(MODEL `proj.sales.revenue_arima`, STRUCT(30 AS horizon, 0.9 AS confidence_level));
SELECT * FROM ML.EXPLAIN_FORECAST(MODEL `proj.sales.revenue_arima`, STRUCT(30 AS horizon));   -- trend, seasonality, holidays
SELECT * FROM ML.DETECT_ANOMALIES(MODEL `proj.sales.revenue_arima`, STRUCT(0.99 AS anomaly_prob_threshold));
```
Use `ARIMA_PLUS_XREG` when known future covariates (price, promotions) drive the series. Forecasting is a time-series task — `LINEAR_REG` on a date column is not a forecast.

## Recommendations
```sql
CREATE OR REPLACE MODEL `proj.reco.mf_implicit`
OPTIONS (
  model_type = 'MATRIX_FACTORIZATION',
  feedback_type = 'IMPLICIT',      -- views/clicks/purchases, not star ratings
  user_col = 'user_id', item_col = 'item_id', rating_col = 'interactions',
  num_factors = 32, l2_reg = 10
) AS
SELECT user_id, item_id, COUNT(*) AS interactions
FROM `proj.reco.events` GROUP BY 1, 2;

SELECT * FROM ML.RECOMMEND(MODEL `proj.reco.mf_implicit`, (SELECT 'u_123' AS user_id));
```
- With implicit feedback the output column is `predicted_<rating_col>_confidence`; with explicit ratings it is `predicted_<rating_col>`.
- Matrix factorization training requires reserved slots (an editions reservation); it is not available on on-demand pricing. Check before proposing it.

## Remote models: Gemini, embeddings, vector search
Setup (once, needs an admin): a Cloud resource connection in the dataset's location, and the connection's service account granted `roles/aiplatform.user`.
```bash
bq mk --connection --location=US --connection_type=CLOUD_RESOURCE vertex_conn
bq show --connection proj.us.vertex_conn      # note serviceAccountId, grant it roles/aiplatform.user
```
```sql
CREATE OR REPLACE MODEL `proj.ai.gemini`
  REMOTE WITH CONNECTION `proj.us.vertex_conn`
  OPTIONS (ENDPOINT = 'gemini-2.5-flash');   -- use a current model name from the Vertex AI docs

SELECT ml_generate_text_llm_result AS summary, ticket_id
FROM ML.GENERATE_TEXT(
  MODEL `proj.ai.gemini`,
  (SELECT ticket_id, CONCAT('Summarize this support ticket in one sentence: ', body) AS prompt
   FROM `proj.support.tickets` WHERE created_date = CURRENT_DATE() - 1),
  STRUCT(0.2 AS temperature, 256 AS max_output_tokens, TRUE AS flatten_json_output));
```
- Row-level generative functions (`AI.GENERATE`, `AI.GENERATE_BOOL`, `AI.GENERATE_TABLE`, …) are also available; check the current signatures in the docs before using them.
- LLM calls are billed per token by Vertex AI on top of BigQuery — always test on `LIMIT 10` first and filter rows tightly.

**Embeddings + semantic search:**
```sql
CREATE OR REPLACE MODEL `proj.ai.embedder`
  REMOTE WITH CONNECTION `proj.us.vertex_conn`
  OPTIONS (ENDPOINT = 'text-embedding-005');

CREATE TABLE `proj.ai.doc_embeddings` AS
SELECT * FROM ML.GENERATE_EMBEDDING(
  MODEL `proj.ai.embedder`,
  (SELECT doc_id, body AS content FROM `proj.kb.docs`),
  STRUCT(TRUE AS flatten_json_output));

CREATE VECTOR INDEX doc_idx ON `proj.ai.doc_embeddings`(ml_generate_embedding_result)
OPTIONS (index_type = 'IVF', distance_type = 'COSINE');   -- worthwhile above ~5k rows

SELECT base.doc_id, distance
FROM VECTOR_SEARCH(
  TABLE `proj.ai.doc_embeddings`, 'ml_generate_embedding_result',
  (SELECT ml_generate_embedding_result FROM ML.GENERATE_EMBEDDING(
     MODEL `proj.ai.embedder`, (SELECT 'how do I reset my password' AS content))),
  top_k => 5, distance_type => 'COSINE');
```

## Deploy and operate
- Batch scoring: schedule an `ML.PREDICT` that writes to a dated table or partition (see the bigquery-scheduled-queries skill for idempotent writes).
- Online serving: register in Vertex AI (`model_registry = 'VERTEX_AI'`, `vertex_ai_model_id = '...'` in OPTIONS) and deploy to an endpoint, or export:
  `EXPORT MODEL \`proj.ml.churn_model\` OPTIONS (URI = 'gs://bucket/models/churn/');` — the URI is a folder, not a wildcard.
- Retrain on a schedule with fresh data; track `ML.EVALUATE` metrics over time and alert on drift (`ML.VALIDATE_DATA_DRIFT`, `ML.VALIDATE_DATA_SKEW`).
- Inventory and cost: `INFORMATION_SCHEMA.JOBS` with `statement_type = 'CREATE_MODEL'` shows each training run's bytes and slot time.

## Common mistakes to avoid
- `model_type = 'BOOSTED_TREE'` (invalid) or missing `input_label_cols` when the label is not called `label`.
- Feeding IDs, timestamps or post-outcome columns as features.
- Reading probabilities with `predicted_x_probs[OFFSET(1)]` — order is not guaranteed.
- Reporting accuracy on imbalanced data without precision/recall/ROC AUC.
- Training on the full table while iterating — sample first, train fully once.
