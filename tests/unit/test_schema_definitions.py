"""Unit tests for PySpark schema definitions — no SparkSession required."""

import pytest
from pyspark.sql.types import (
    DateType,
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    TimestampType,
)

from src.lib.schema_definitions import (
    ORDER_ITEMS_SCHEMA,
    ORDERS_SCHEMA,
    PARTITION_COLS,
    PRIMARY_KEYS,
    PRODUCTS_SCHEMA,
    SCHEMA_REGISTRY,
)


def _field(schema, name):
    """Return a StructField by name or raise if not found."""
    matches = [f for f in schema.fields if f.name == name]
    assert matches, f"Field '{name}' not found in schema. Fields: {[f.name for f in schema.fields]}"
    return matches[0]


class TestProductsSchema:
    def test_field_count(self):
        assert len(PRODUCTS_SCHEMA.fields) == 4

    def test_product_id_is_integer_not_null(self):
        f = _field(PRODUCTS_SCHEMA, "product_id")
        assert isinstance(f.dataType, IntegerType)
        assert f.nullable is False

    def test_department_id_is_integer_not_null(self):
        f = _field(PRODUCTS_SCHEMA, "department_id")
        assert isinstance(f.dataType, IntegerType)
        assert f.nullable is False

    def test_department_is_string_not_null(self):
        f = _field(PRODUCTS_SCHEMA, "department")
        assert isinstance(f.dataType, StringType)
        assert f.nullable is False

    def test_product_name_is_string_not_null(self):
        f = _field(PRODUCTS_SCHEMA, "product_name")
        assert isinstance(f.dataType, StringType)
        assert f.nullable is False


class TestOrdersSchema:
    def test_field_count(self):
        assert len(ORDERS_SCHEMA.fields) == 6

    def test_order_id_is_integer_not_null(self):
        f = _field(ORDERS_SCHEMA, "order_id")
        assert isinstance(f.dataType, IntegerType)
        assert f.nullable is False

    def test_order_num_is_long(self):
        f = _field(ORDERS_SCHEMA, "order_num")
        assert isinstance(f.dataType, LongType)

    def test_order_timestamp_is_timestamp_not_null(self):
        f = _field(ORDERS_SCHEMA, "order_timestamp")
        assert isinstance(f.dataType, TimestampType)
        assert f.nullable is False

    def test_total_amount_is_double_not_null(self):
        f = _field(ORDERS_SCHEMA, "total_amount")
        assert isinstance(f.dataType, DoubleType)
        assert f.nullable is False

    def test_date_is_date_not_null(self):
        f = _field(ORDERS_SCHEMA, "date")
        assert isinstance(f.dataType, DateType)
        assert f.nullable is False


class TestOrderItemsSchema:
    def test_field_count(self):
        assert len(ORDER_ITEMS_SCHEMA.fields) == 9

    def test_id_is_long_not_null(self):
        f = _field(ORDER_ITEMS_SCHEMA, "id")
        assert isinstance(f.dataType, LongType)
        assert f.nullable is False

    def test_order_id_not_null(self):
        f = _field(ORDER_ITEMS_SCHEMA, "order_id")
        assert f.nullable is False

    def test_days_since_prior_order_is_nullable(self):
        # Null for a customer's first-ever order — the only nullable int field
        f = _field(ORDER_ITEMS_SCHEMA, "days_since_prior_order")
        assert isinstance(f.dataType, IntegerType)
        assert f.nullable is True

    def test_reordered_is_integer_not_null(self):
        f = _field(ORDER_ITEMS_SCHEMA, "reordered")
        assert isinstance(f.dataType, IntegerType)
        assert f.nullable is False

    def test_order_timestamp_is_timestamp(self):
        f = _field(ORDER_ITEMS_SCHEMA, "order_timestamp")
        assert isinstance(f.dataType, TimestampType)


class TestSchemaRegistry:
    def test_all_three_tables_registered(self):
        assert set(SCHEMA_REGISTRY.keys()) == {"products", "orders", "order_items"}

    def test_registry_returns_correct_schema(self):
        assert SCHEMA_REGISTRY["products"] is PRODUCTS_SCHEMA
        assert SCHEMA_REGISTRY["orders"] is ORDERS_SCHEMA
        assert SCHEMA_REGISTRY["order_items"] is ORDER_ITEMS_SCHEMA


class TestPrimaryKeys:
    def test_products_pk(self):
        assert PRIMARY_KEYS["products"] == ["product_id"]

    def test_orders_pk(self):
        assert PRIMARY_KEYS["orders"] == ["order_id"]

    def test_order_items_pk(self):
        assert PRIMARY_KEYS["order_items"] == ["id"]


class TestPartitionCols:
    def test_products_has_no_partition(self):
        assert PARTITION_COLS["products"] == []

    def test_orders_partitioned_by_date(self):
        assert PARTITION_COLS["orders"] == ["date"]

    def test_order_items_partitioned_by_date(self):
        assert PARTITION_COLS["order_items"] == ["date"]
