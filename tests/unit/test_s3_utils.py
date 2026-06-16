"""Unit tests for S3 utility functions using mocked boto3."""

from unittest.mock import MagicMock, call, patch

import pytest
from botocore.exceptions import ClientError

from src.lib.exceptions import S3ReadError, S3WriteError
from src.lib.s3_utils import check_s3_object_exists, list_s3_objects, move_s3_object


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "mocked"}}, "operation")


@patch("src.lib.s3_utils._s3")
class TestMoveS3Object:
    def test_copies_then_deletes(self, mock_s3):
        move_s3_object("src-bucket", "src/key.csv", "dst-bucket", "dst/key.csv")

        mock_s3.copy_object.assert_called_once_with(
            CopySource={"Bucket": "src-bucket", "Key": "src/key.csv"},
            Bucket="dst-bucket",
            Key="dst/key.csv",
        )
        mock_s3.delete_object.assert_called_once_with(
            Bucket="src-bucket", Key="src/key.csv"
        )

    def test_raises_s3_write_error_on_copy_failure(self, mock_s3):
        mock_s3.copy_object.side_effect = _client_error("AccessDenied")
        with pytest.raises(S3WriteError):
            move_s3_object("src", "key", "dst", "key")

    def test_raises_s3_write_error_on_delete_failure(self, mock_s3):
        mock_s3.copy_object.return_value = {}
        mock_s3.delete_object.side_effect = _client_error("AccessDenied")
        with pytest.raises(S3WriteError, match="source delete failed"):
            move_s3_object("src", "key", "dst", "key")

    def test_delete_not_called_when_copy_fails(self, mock_s3):
        mock_s3.copy_object.side_effect = _client_error("NoSuchBucket")
        with pytest.raises(S3WriteError):
            move_s3_object("src", "key", "dst", "key")
        mock_s3.delete_object.assert_not_called()


@patch("src.lib.s3_utils._s3")
class TestListS3Objects:
    def test_yields_all_keys_single_page(self, mock_s3):
        mock_s3.get_paginator.return_value.paginate.return_value = [
            {"Contents": [{"Key": "a/b.csv"}, {"Key": "a/c.csv"}]}
        ]
        result = list(list_s3_objects("bucket", "a/"))
        assert result == ["a/b.csv", "a/c.csv"]

    def test_yields_keys_across_multiple_pages(self, mock_s3):
        mock_s3.get_paginator.return_value.paginate.return_value = [
            {"Contents": [{"Key": "page1/key1"}]},
            {"Contents": [{"Key": "page2/key2"}]},
        ]
        result = list(list_s3_objects("bucket", ""))
        assert result == ["page1/key1", "page2/key2"]

    def test_returns_empty_when_no_objects(self, mock_s3):
        mock_s3.get_paginator.return_value.paginate.return_value = [{}]
        result = list(list_s3_objects("bucket", "empty/"))
        assert result == []

    def test_raises_s3_read_error_on_client_error(self, mock_s3):
        mock_s3.get_paginator.return_value.paginate.side_effect = _client_error(
            "NoSuchBucket"
        )
        with pytest.raises(S3ReadError):
            list(list_s3_objects("bucket", "prefix/"))


@patch("src.lib.s3_utils._s3")
class TestCheckS3ObjectExists:
    def test_returns_true_when_object_exists(self, mock_s3):
        mock_s3.head_object.return_value = {"ContentLength": 100}
        assert check_s3_object_exists("bucket", "key.csv") is True

    def test_returns_false_when_404(self, mock_s3):
        mock_s3.head_object.side_effect = _client_error("404")
        assert check_s3_object_exists("bucket", "missing.csv") is False

    def test_raises_s3_read_error_on_other_errors(self, mock_s3):
        mock_s3.head_object.side_effect = _client_error("AccessDenied")
        with pytest.raises(S3ReadError):
            check_s3_object_exists("bucket", "key.csv")
