"""Pluggable data quality rules — each returns (valid_df, invalid_df) with __error_reason__."""

import logging
from abc import ABC, abstractmethod
from datetime import datetime

import pyspark.sql.functions as F
from pyspark.sql import DataFrame
from pyspark.sql.window import Window

logger = logging.getLogger(__name__)

_ERROR_COL = "__error_reason__"


class ValidationRule(ABC):
    """Base class for all data quality rules."""

    @property
    @abstractmethod
    def rule_name(self) -> str:
        """Short identifier used in RuleResult and quarantine metadata."""

    @abstractmethod
    def validate(self, df: DataFrame) -> tuple[DataFrame, DataFrame]:
        """Split df into (valid_df, invalid_df); invalid_df includes __error_reason__."""


class NotNullRule(ValidationRule):
    """Quarantines rows where the specified column contains null."""

    def __init__(self, column: str) -> None:
        self._column = column

    @property
    def rule_name(self) -> str:
        return f"not_null:{self._column}"

    def validate(self, df: DataFrame) -> tuple[DataFrame, DataFrame]:
        invalid = df.filter(F.col(self._column).isNull()).withColumn(
            _ERROR_COL,
            F.lit(f"null value in required column '{self._column}'"),
        )
        valid = df.filter(F.col(self._column).isNotNull())
        logger.debug(
            "NotNullRule applied",
            extra={"column": self._column, "invalid_count": invalid.count()},
        )
        return valid, invalid


class UniqueKeyRule(ValidationRule):
    """Quarantines duplicate rows keeping the first occurrence of each key combination."""

    def __init__(self, key_columns: list[str]) -> None:
        self._keys = key_columns

    @property
    def rule_name(self) -> str:
        return f"unique_key:{'|'.join(self._keys)}"

    def validate(self, df: DataFrame) -> tuple[DataFrame, DataFrame]:
        window = Window.partitionBy(*self._keys).orderBy(F.monotonically_increasing_id())
        ranked = df.withColumn("__row_rank__", F.row_number().over(window))
        valid = ranked.filter(F.col("__row_rank__") == 1).drop("__row_rank__")
        invalid = ranked.filter(F.col("__row_rank__") > 1).drop("__row_rank__").withColumn(
            _ERROR_COL,
            F.lit(f"duplicate key on columns: {self._keys}"),
        )
        logger.debug(
            "UniqueKeyRule applied",
            extra={"keys": self._keys, "invalid_count": invalid.count()},
        )
        return valid, invalid


class ReferentialIntegrityRule(ValidationRule):
    """Quarantines rows whose FK value has no matching row in the reference DataFrame."""

    def __init__(
        self,
        fk_column: str,
        reference_df: DataFrame,
        ref_column: str,
    ) -> None:
        self._fk = fk_column
        self._ref_df = reference_df.select(ref_column).distinct()
        self._ref_col = ref_column

    @property
    def rule_name(self) -> str:
        return f"referential_integrity:{self._fk}"

    def validate(self, df: DataFrame) -> tuple[DataFrame, DataFrame]:
        # Anti-join: keep rows in df that have no match in reference
        invalid = (
            df.join(
                self._ref_df.withColumnRenamed(self._ref_col, self._fk),
                on=self._fk,
                how="left_anti",
            )
            .withColumn(
                _ERROR_COL,
                F.lit(
                    f"referential_integrity_violation: '{self._fk}' "
                    f"not found in reference table column '{self._ref_col}'"
                ),
            )
        )
        valid = df.join(
            self._ref_df.withColumnRenamed(self._ref_col, self._fk),
            on=self._fk,
            how="inner",
        )
        logger.debug(
            "ReferentialIntegrityRule applied",
            extra={"fk_column": self._fk, "invalid_count": invalid.count()},
        )
        return valid, invalid


class TimestampRangeRule(ValidationRule):
    """Quarantines rows where a timestamp column falls outside [min_ts, max_ts]."""

    def __init__(self, column: str, min_ts: datetime, max_ts: datetime) -> None:
        self._column = column
        self._min = min_ts
        self._max = max_ts

    @property
    def rule_name(self) -> str:
        return f"timestamp_range:{self._column}"

    def validate(self, df: DataFrame) -> tuple[DataFrame, DataFrame]:
        in_range = (F.col(self._column) >= F.lit(self._min)) & (
            F.col(self._column) <= F.lit(self._max)
        )
        valid = df.filter(in_range)
        invalid = df.filter(~in_range | F.col(self._column).isNull()).withColumn(
            _ERROR_COL,
            F.lit(
                f"'{self._column}' out of range "
                f"[{self._min.isoformat()}, {self._max.isoformat()}]"
            ),
        )
        return valid, invalid


class PositiveAmountRule(ValidationRule):
    """Quarantines rows where a numeric column is not strictly greater than zero."""

    def __init__(self, column: str) -> None:
        self._column = column

    @property
    def rule_name(self) -> str:
        return f"positive_amount:{self._column}"

    def validate(self, df: DataFrame) -> tuple[DataFrame, DataFrame]:
        valid = df.filter(F.col(self._column) > 0)
        invalid = df.filter(
            (F.col(self._column) <= 0) | F.col(self._column).isNull()
        ).withColumn(
            _ERROR_COL,
            F.lit(f"'{self._column}' must be > 0"),
        )
        return valid, invalid


class BooleanFlagRule(ValidationRule):
    """Quarantines rows where an integer flag column is not 0 or 1."""

    def __init__(self, column: str) -> None:
        self._column = column

    @property
    def rule_name(self) -> str:
        return f"boolean_flag:{self._column}"

    def validate(self, df: DataFrame) -> tuple[DataFrame, DataFrame]:
        valid = df.filter(F.col(self._column).isin(0, 1))
        invalid = df.filter(
            ~F.col(self._column).isin(0, 1) | F.col(self._column).isNull()
        ).withColumn(
            _ERROR_COL,
            F.lit(f"'{self._column}' must be 0 or 1"),
        )
        return valid, invalid
