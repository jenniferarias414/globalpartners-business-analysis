# Key and Relationship Validation

## Purpose

This step tested whether the source columns can uniquely identify records and whether related records connect correctly across the files.

## Checks Performed

- Tested single-column and composite candidate keys.
- Counted missing and repeated key values.
- Matched option records to orders and order items.
- Parsed source dates using their explicit formats.
- Compared order-date coverage with the supplied date dimension.
- Investigated the records that failed relationship checks.

## Key Lessons

A usable key must be both complete and unique. A column can be unique among its populated values and still fail as a key when values are missing.

The grain of a table also affects its key. An order item can have several options, so `order_id` and `lineitem_id` identify the parent item but not each option record.

Relationship checks identify child records without a corresponding parent. These records require an exception-handling rule before the pipeline is built.

Explicit date formats prevent valid dates from being misinterpreted during ingestion.

## Result

The date dimension has a complete and unique key but covers only 2023. The order-item identifier is unique when populated but has one missing value. The options source contains exact repeated rows and does not provide a unique natural key.