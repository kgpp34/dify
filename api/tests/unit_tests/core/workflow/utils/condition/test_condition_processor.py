"""
Tests for condition processor with in/not in operators
"""

import pytest

from core.workflow.utils.condition.processor import _evaluate_condition


class TestInOperator:
    """Test cases for 'in' operator"""

    def test_in_string_value_in_list(self):
        """Test string value exists in list"""
        assert _evaluate_condition(operator="in", value="apple", expected=["apple", "banana", "orange"]) is True

    def test_in_string_value_not_in_list(self):
        """Test string value does not exist in list"""
        assert _evaluate_condition(operator="in", value="grape", expected=["apple", "banana", "orange"]) is False

    def test_in_number_value_in_list(self):
        """Test number value exists in list"""
        assert _evaluate_condition(operator="in", value=42, expected=[1, 2, 42, 100]) is True

    def test_in_number_value_not_in_list(self):
        """Test number value does not exist in list"""
        assert _evaluate_condition(operator="in", value=99, expected=[1, 2, 42, 100]) is False

    def test_in_empty_list_returns_false(self):
        """Test in operator with empty list returns False"""
        assert _evaluate_condition(operator="in", value="apple", expected=[]) is False

    def test_in_value_none_returns_false(self):
        """Test in operator with None value returns False"""
        assert _evaluate_condition(operator="in", value=None, expected=["apple", "banana"]) is False

    def test_in_with_string_list(self):
        """Test in operator with string values"""
        assert _evaluate_condition(operator="in", value="test", expected=["test", "example", "sample"]) is True


class TestNotInOperator:
    """Test cases for 'not in' operator"""

    def test_not_in_string_value_not_in_list(self):
        """Test string value does not exist in list"""
        assert _evaluate_condition(operator="not in", value="grape", expected=["apple", "banana", "orange"]) is True

    def test_not_in_string_value_in_list(self):
        """Test string value exists in list"""
        assert _evaluate_condition(operator="not in", value="apple", expected=["apple", "banana", "orange"]) is False

    def test_not_in_number_value_not_in_list(self):
        """Test number value does not exist in list"""
        assert _evaluate_condition(operator="not in", value=99, expected=[1, 2, 42, 100]) is True

    def test_not_in_number_value_in_list(self):
        """Test number value exists in list"""
        assert _evaluate_condition(operator="not in", value=42, expected=[1, 2, 42, 100]) is False

    def test_not_in_empty_list_returns_true(self):
        """Test not in operator with empty list returns True"""
        assert _evaluate_condition(operator="not in", value="apple", expected=[]) is True

    def test_not_in_value_none_returns_true(self):
        """Test not in operator with None value returns True"""
        assert _evaluate_condition(operator="not in", value=None, expected=["apple", "banana"]) is True

    def test_not_in_with_string_list(self):
        """Test not in operator with string values"""
        assert _evaluate_condition(operator="not in", value="other", expected=["test", "example", "sample"]) is True


class TestInOperatorEdgeCases:
    """Test edge cases for in/not in operators"""

    def test_in_with_single_element_list(self):
        """Test in operator with single element list"""
        assert _evaluate_condition(operator="in", value="apple", expected=["apple"]) is True

        assert _evaluate_condition(operator="in", value="banana", expected=["apple"]) is False

    def test_not_in_with_single_element_list(self):
        """Test not in operator with single element list"""
        assert _evaluate_condition(operator="not in", value="banana", expected=["apple"]) is True

        assert _evaluate_condition(operator="not in", value="apple", expected=["apple"]) is False

    def test_in_with_special_characters(self):
        """Test in operator with special characters in values"""
        assert _evaluate_condition(operator="in", value="hello world", expected=["hello world", "foo bar"]) is True

    def test_in_with_empty_string(self):
        """Test in operator with empty string

        Note: Current implementation treats empty string as falsy value,
        so it returns False even if empty string is in the expected list.
        This is a known limitation of the current implementation.
        """
        # Current behavior: empty string is treated as falsy, returns False
        assert _evaluate_condition(operator="in", value="", expected=["", "apple", "banana"]) is False

        assert _evaluate_condition(operator="not in", value="", expected=["apple", "banana"]) is True

    def test_in_raises_error_with_non_list_expected(self):
        """Test in operator raises error when expected is not a list"""
        with pytest.raises(ValueError, match="Invalid expected value type"):
            _evaluate_condition(operator="in", value="apple", expected="not_a_list")

    def test_not_in_raises_error_with_non_list_expected(self):
        """Test not in operator raises error when expected is not a list"""
        with pytest.raises(ValueError, match="Invalid expected value type"):
            _evaluate_condition(operator="not in", value="apple", expected="not_a_list")
