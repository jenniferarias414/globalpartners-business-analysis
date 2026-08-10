# Silver Order Options Validation

## Objective

Validate option records against accepted Silver order items while preserving repeated source records that cannot be safely classified as duplicates.

## Processing

The AWS Glue PySpark job:

- read the Bronze `order_item_options` partition and accepted Silver order items;
- standardized option fields, prices, and quantities;
- checked required fields and valid numeric values;
- verified both the parent order and parent order-item relationship;
- quarantined orphan option records;
- retained repeated source occurrences with warning flags;
- reconciled all input records; and
- wrote a JSON control report for the run.

## Validation Results

| Measure | Result |
|---|---:|
| Bronze input rows | 193,017 |
| Silver accepted rows | 192,989 |
| Quarantined orphan rows | 28 |
| Distinct missing orders | 14 |
| Distinct missing order-item pairs | 15 |
| Repeated groups | 616 |
| Repeated occurrences after the first | 2,299 |
| Reconciliation passed | Yes |

All 28 quarantined options referenced orders that were absent from the accepted Silver order-item data. They were retained separately for review instead of being included in downstream business metrics.

The 2,299 repeated occurrences remained in Silver with warning flags. The source does not provide an option-level identifier or enough business context to determine whether the repetitions are accidental duplicates or intentional selections.
