---
type: regex
pattern: 'model_type\\s*=\\s*.BOOSTED_TREE.(?!_)'
flags: i
match: not_contains
---
BOOSTED_TREE is not a valid model_type
