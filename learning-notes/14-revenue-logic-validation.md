# Revenue Logic Validation

## Objective

Determine whether `item_price` represents a single-unit price or the full amount for the quantity recorded on an order-item row.

## Method

The analysis compared higher-quantity rows with quantity-one rows for the same item. For each comparison, the higher-quantity price was divided by quantity and compared with the item's quantity-one median price.

The focused sample included item-and-quantity groups with at least 20 quantity-one records and at least five higher-quantity records.

## Results

| Measure | Result |
|---|---:|
| Order-item rows tested | 203,519 |
| Rows with quantity greater than one | 13,650 |
| Qualified comparison groups | 263 |
| Groups supporting an extended line amount | 209 |
| Pattern support | 79.47% |
| Negative option-price rows | 0 |
| Distinct option quantities | 1 |

Common items showed direct price scaling. For example, Bacon Egg & Cheese had a median price of $5.99 at quantity one, $11.98 at quantity two, and $17.97 at quantity three.

## Gold Revenue Rule

`item_price` will be treated as the extended order-line amount and will not be multiplied by `item_quantity` again. Accepted option prices will be added separately; all supplied option quantities equal one.

No negative option prices were found, so the supplied data does not support a comparison of discounted and non-discounted orders. Profitability also cannot be calculated because the source does not include product-cost data.
