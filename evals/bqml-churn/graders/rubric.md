---
type: llm
weight: 3
---
PASS if CREATE MODEL uses a valid classifier type (LOGISTIC_REG, BOOSTED_TREE_CLASSIFIER, RANDOM_FOREST_CLASSIFIER, DNN_CLASSIFIER, or AUTOML_CLASSIFIER), sets input_label_cols=['churned'], excludes user_id from features (SELECT * EXCEPT(user_id)), evaluates with ML.EVALUATE (optionally ML.ROC_CURVE / ML.CONFUSION_MATRIX), and mentions class imbalance (auto_class_weights) or training cost.
FAIL if it uses model_type='BOOSTED_TREE' (invalid) or omits input_label_cols while the label column is not named 'label'.
