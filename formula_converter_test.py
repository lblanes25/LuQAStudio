"""
Excel Formula Converter Test Script

This script tests the new Excel Formula Converter implementation against
various formula types to verify its accuracy and robustness.

Run this script to:
1. Compare the results of the new converter vs. the legacy parser
2. Test formula execution against sample data
3. Analyze performance differences between the implementations
"""

import pandas as pd
import numpy as np
import logging
import time
from typing import List, Dict, Any

# Set up logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("excel_converter_test")

# Try to import both parsers for comparison
try:
    from excel_formula_converter_integration import parse_excel_formula as new_parse
    from excel_formula_converter_integration import test_excel_formula
    HAS_NEW_CONVERTER = True
except ImportError:
    logger.warning("New Excel Formula Converter not available")
    HAS_NEW_CONVERTER = False

try:
    from excel_formula_parser import ExcelFormulaParser
    HAS_LEGACY_PARSER = True
except ImportError:
    logger.warning("Legacy Excel Formula Parser not available")
    HAS_LEGACY_PARSER = False


class FormulaTestSuite:
    """Test suite for Excel formula conversion and execution"""

    def __init__(self):
        """Initialize the test suite with sample data"""
        # Create sample DataFrame
        self.df = self._create_sample_data()

        # Set up test formulas
        self.test_formulas = self._get_test_formulas()

        # Set up parsers
        if HAS_LEGACY_PARSER:
            self.legacy_parser = ExcelFormulaParser()

    def _create_sample_data(self) -> pd.DataFrame:
        """Create a sample DataFrame for testing"""
        data = {
            "TW submitter": ["John Smith", "Emma Johnson", "Michael Brown", "Sarah Davis"],
            "TL approver": ["Alex Rodriguez", "John Smith", "Patricia Moore", "Sarah Davis"],
            "AL approver": ["Michelle Lee", "Richard White", "Michael Brown", "James Martin"],
            "Submit Date": pd.to_datetime(["2023-01-15", "2023-02-10", "2023-03-22", "2023-04-05"]),
            "TL Approval Date": pd.to_datetime(["2023-01-16", "2023-02-09", "2023-03-24", "2023-04-08"]),
            "AL Approval Date": pd.to_datetime(["2023-01-17", "2023-02-15", "2023-03-23", "2023-04-09"]),
            "Risk Level": ["High", "Low", "Medium", "High"],
            "Value": [120, 80, 200, 50],
            "Status": ["Active", "Inactive", "Active", "On Hold"],
            "Third Party": ["Vendor A, Vendor B", "", "Vendor C", ""],
            "Risk Rating": ["High", "N/A", "Medium", "N/A"]
        }
        return pd.DataFrame(data)

    def _get_test_formulas(self) -> List[Dict[str, Any]]:
        """Get a list of test formulas with expected results"""
        return [
            {
                "name": "Simple Equality",
                "formula": "TW submitter = \"John Smith\"",
                "expect_pass_indices": [0]
            },
            {
                "name": "Inequality",
                "formula": "TW submitter <> TL approver",
                "expect_pass_indices": [0, 2]
            },
            {
                "name": "Multiple Conditions (AND)",
                "formula": "AND(Status=\"Active\", Value>100)",
                "expect_pass_indices": [0, 2]
            },
            {
                "name": "Multiple Conditions (OR)",
                "formula": "OR(Risk Level=\"High\", Value>150)",
                "expect_pass_indices": [0, 2, 3]
            },
            {
                "name": "Negation (NOT)",
                "formula": "NOT(Risk Level=\"High\")",
                "expect_pass_indices": [1, 2]
            },
            {
                "name": "Date Comparison",
                "formula": "Submit Date <= TL Approval Date",
                "expect_pass_indices": [0, 2, 3]
            },
            {
                "name": "ISBLANK Function",
                "formula": "ISBLANK(Third Party)",
                "expect_pass_indices": [1, 3]
            },
            {
                "name": "Complex Condition",
                "formula": "IF(AND(Third Party<>\"\", Risk Rating<>\"N/A\"), \"GC\", \"DNC\") = \"GC\"",
                "expect_pass_indices": [0, 2]
            },
            {
                "name": "Multi-word Column Names",
                "formula": "`TW submitter` <> `AL approver`",
                "expect_pass_indices": [0, 1, 2, 3]
            }
        ]

    def run_all_tests(self, use_new_parser: bool = True) -> Dict[str, Any]:
        """
        Run all tests using the specified parser.

        Args:
            use_new_parser: Whether to use the new parser

        Returns:
            Dictionary with test results
        """
        results = {
            "tests": [],
            "summary": {
                "total": len(self.test_formulas),
                "passed": 0,
                "failed": 0,
                "errors": 0,
                "parser": "new" if use_new_parser else "legacy",
                "execution_time": 0
            }
        }

        start_time = time.time()

        for i, test in enumerate(self.test_formulas):
            logger.info(f"Running test {i+1}/{len(self.test_formulas)}: {test['name']}")

            # Run the test
            test_result = self.run_test(test, use_new_parser)
            results["tests"].append(test_result)

            # Update summary
            if test_result["status"] == "passed":
                results["summary"]["passed"] += 1
            elif test_result["status"] == "failed":
                results["summary"]["failed"] += 1
            else:
                results["summary"]["errors"] += 1

        end_time = time.time()
        results["summary"]["execution_time"] = end_time - start_time

        # Print summary
        self._print_summary(results["summary"])

        return results

    def run_test(self, test: Dict[str, Any], use_new_parser: bool = True) -> Dict[str, Any]:
        """
        Run a single test.

        Args:
            test: Test definition dictionary
            use_new_parser: Whether to use the new parser

        Returns:
            Dictionary with test results
        """
        result = {
            "name": test["name"],
            "formula": test["formula"],
            "expected_pass_indices": test["expect_pass_indices"],
            "status": "unknown",
            "parser_used": "new" if use_new_parser else "legacy",
            "error": None,
            "parsed_formula": None,
            "actual_pass_indices": [],
            "matches_expected": False
        }

        try:
            # Parse the formula
            if use_new_parser and HAS_NEW_CONVERTER:
                # Import here to avoid circular imports
                from excel_formula_converter_integration import parse_excel_formula
                parsed_formula, fields_used = parse_excel_formula(test["formula"], list(self.df.columns))
            elif HAS_LEGACY_PARSER:
                parsed_formula, fields_used = self.legacy_parser.parse(test["formula"])
            else:
                result["status"] = "error"
                result["error"] = "No parser available"
                return result

            result["parsed_formula"] = parsed_formula
            result["fields_used"] = fields_used

            if test["name"] == "Multiple Conditions (AND)":
                print("DEBUG - Final parsed formula for AND test:")
                print(parsed_formula)
                import ast
                try:
                    ast.parse(parsed_formula)
                except SyntaxError as e:
                    print("SYNTAX ERROR:", e)

            # Evaluate the formula
            restricted_globals = {"__builtins__": {}}
            safe_locals = {"df": self.df, "pd": pd, "np": np}

            formula_result = eval(parsed_formula, restricted_globals, safe_locals)

            # Ensure result is a boolean Series
            if not isinstance(formula_result, pd.Series):
                formula_result = pd.Series(formula_result, index=self.df.index)

            if formula_result.dtype != bool:
                formula_result = formula_result.astype(bool)

            # Get indices where the formula evaluates to True
            result["actual_pass_indices"] = list(formula_result[formula_result].index)

            # Compare with expected results
            expected_set = set(test["expect_pass_indices"])
            actual_set = set(result["actual_pass_indices"])

            result["matches_expected"] = expected_set == actual_set
            result["status"] = "passed" if result["matches_expected"] else "failed"

            if not result["matches_expected"]:
                result["missing"] = list(expected_set - actual_set)
                result["unexpected"] = list(actual_set - expected_set)

            return result

        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            logger.error(f"Error running test {test['name']}: {e}")
            return result

    def compare_parsers(self) -> Dict[str, Any]:
        """
        Run tests with both parsers and compare results.

        Returns:
            Dictionary with comparison results
        """
        if not (HAS_NEW_CONVERTER and HAS_LEGACY_PARSER):
            logger.error("Cannot compare parsers - both parsers must be available")
            return {"error": "Both parsers must be available for comparison"}

        # Run tests with both parsers
        new_results = self.run_all_tests(use_new_parser=True)
        legacy_results = self.run_all_tests(use_new_parser=False)

        # Compare results
        comparison = {
            "summary": {
                "new_parser": new_results["summary"],
                "legacy_parser": legacy_results["summary"],
                "same_outcomes": 0,
                "different_outcomes": 0,
                "tests": []
            }
        }

        for i, (new_test, legacy_test) in enumerate(zip(new_results["tests"], legacy_results["tests"])):
            test_comparison = {
                "name": new_test["name"],
                "formula": new_test["formula"],
                "new_status": new_test["status"],
                "legacy_status": legacy_test["status"],
                "same_outcome": new_test["status"] == legacy_test["status"] and
                               set(new_test.get("actual_pass_indices", [])) ==
                               set(legacy_test.get("actual_pass_indices", []))
            }

            if test_comparison["same_outcome"]:
                comparison["summary"]["same_outcomes"] += 1
            else:
                comparison["summary"]["different_outcomes"] += 1
                test_comparison["details"] = {
                    "new_parser": {
                        "parsed_formula": new_test["parsed_formula"],
                        "actual_pass_indices": new_test.get("actual_pass_indices", []),
                        "error": new_test.get("error")
                    },
                    "legacy_parser": {
                        "parsed_formula": legacy_test["parsed_formula"],
                        "actual_pass_indices": legacy_test.get("actual_pass_indices", []),
                        "error": legacy_test.get("error")
                    }
                }

            comparison["summary"]["tests"].append(test_comparison)

        # Print comparison summary
        self._print_comparison_summary(comparison["summary"])

        return comparison

    def _print_summary(self, summary: Dict[str, Any]) -> None:
        """Print a summary of test results"""
        print("\n" + "="*60)
        print(f"TEST SUMMARY ({summary['parser']} parser)")
        print("="*60)
        print(f"Total tests: {summary['total']}")
        print(f"Passed: {summary['passed']} ({summary['passed']/summary['total']*100:.1f}%)")
        print(f"Failed: {summary['failed']} ({summary['failed']/summary['total']*100:.1f}%)")
        print(f"Errors: {summary['errors']} ({summary['errors']/summary['total']*100:.1f}%)")
        print(f"Execution time: {summary['execution_time']:.3f} seconds")
        print("="*60)

    def _print_comparison_summary(self, summary: Dict[str, Any]) -> None:
        """Print a summary of parser comparison results"""
        print("\n" + "="*60)
        print("PARSER COMPARISON SUMMARY")
        print("="*60)
        print(f"Total tests: {len(summary['tests'])}")
        print(f"Same outcomes: {summary['same_outcomes']} ({summary['same_outcomes']/len(summary['tests'])*100:.1f}%)")
        print(f"Different outcomes: {summary['different_outcomes']} ({summary['different_outcomes']/len(summary['tests'])*100:.1f}%)")

        if summary['different_outcomes'] > 0:
            print("\nTests with different outcomes:")
            for i, test in enumerate(summary['tests']):
                if not test["same_outcome"]:
                    print(f"  {i+1}. {test['name']} - New: {test['new_status']}, Legacy: {test['legacy_status']}")

        print("\nExecution Time:")
        print(f"  New parser: {summary['new_parser']['execution_time']:.3f} seconds")
        print(f"  Legacy parser: {summary['legacy_parser']['execution_time']:.3f} seconds")

        # Calculate speedup or slowdown
        if summary['legacy_parser']['execution_time'] > 0:
            ratio = summary['new_parser']['execution_time'] / summary['legacy_parser']['execution_time']
            if ratio < 1:
                print(f"  Speedup: {1/ratio:.2f}x faster with new parser")
            else:
                print(f"  Slowdown: {ratio:.2f}x slower with new parser")

        print("="*60)


# Main function to run tests
def main():
    """Run all tests and compare parsers"""
    print("\n" + "="*60)
    print("EXCEL FORMULA CONVERTER TEST SUITE")
    print("="*60)

    if not (HAS_NEW_CONVERTER or HAS_LEGACY_PARSER):
        print("Error: No parsers available. Please install at least one parser.")
        return

    # Create test suite
    test_suite = FormulaTestSuite()

    # Choose which test to run based on available parsers
    if HAS_NEW_CONVERTER and HAS_LEGACY_PARSER:
        print("Both parsers available - running comparison")
        test_suite.compare_parsers()
    elif HAS_NEW_CONVERTER:
        print("Only new parser available - running tests with new parser")
        test_suite.run_all_tests(use_new_parser=True)
    elif HAS_LEGACY_PARSER:
        print("Only legacy parser available - running tests with legacy parser")
        test_suite.run_all_tests(use_new_parser=False)


if __name__ == "__main__":
    main()