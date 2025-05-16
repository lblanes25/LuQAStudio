"""
Integration module for Excel Formula Converter

This module provides a bridge between the robust ExcelToPandasConverter
and the existing ExcelFormulaParser implementation, allowing for a
smooth transition to the new parser while maintaining backward compatibility.

Example usage:
    from excel_formula_converter_integration import parse_excel_formula, test_excel_formula

    # Parse a formula
    pandas_expr, fields_used = parse_excel_formula("Value > 100 AND Status = 'Active'")

    # Test a formula against sample data
    test_result = test_excel_formula("NOT ISBLANK(ThirdParty)", df)
"""

import logging
from typing import Tuple, Set, Optional, Dict, List, Any

# Configure logging
logger = logging.getLogger("qa_analytics")

# Try to import the new converter
try:
    from excel_formula_converter import ExcelToPandasConverter
    HAS_NEW_CONVERTER = True
except ImportError:
    logger.warning("ExcelToPandasConverter not available. Using legacy parser.")
    from excel_formula_parser import ExcelFormulaParser
    HAS_NEW_CONVERTER = False


class FormulaConverterFacade:
    """
    Facade that provides a unified interface to either the new ExcelToPandasConverter
    or the legacy ExcelFormulaParser.
    """

    def __init__(self, use_new_converter: bool = True):
        """
        Initialize the converter facade.

        Args:
            use_new_converter: Whether to use the new converter if available
        """
        self.use_new_converter = use_new_converter and HAS_NEW_CONVERTER

        # Initialize the appropriate converter
        if self.use_new_converter:
            self.converter = ExcelToPandasConverter()
            logger.info("Using ExcelToPandasConverter for formula parsing")
        else:
            self.parser = ExcelFormulaParser()
            logger.info("Using legacy ExcelFormulaParser for formula parsing")

    def parse(self, formula: str, df_columns: Optional[List[str]] = None) -> Tuple[str, Set[str]]:
        """
        Parse an Excel formula into a pandas expression.

        Args:
            formula: Excel formula to parse
            df_columns: Optional list of DataFrame column names

        Returns:
            Tuple containing:
            - Pandas expression string
            - Set of field names used in the formula
        """
        try:
            if self.use_new_converter:
                # Use the new converter
                return self.converter.convert(formula, df_columns)
            else:
                # Use the legacy parser
                parsed_formula, fields_used = self.parser.parse(formula)
                return parsed_formula, set(fields_used)
        except Exception as e:
            logger.error(f"Error parsing formula '{formula}': {e}")
            # Return a safe default that will always return False
            return "pd.Series(False, index=df.index)", set()

    def test_formula(self, formula: str, data: Any) -> Dict:
        """
        Test a formula against sample data.

        Args:
            formula: Excel formula to test
            data: DataFrame to test against

        Returns:
            Dictionary with test results
        """
        try:
            import pandas as pd
            import numpy as np

            # Register DataFrame columns if using new converter
            if self.use_new_converter and hasattr(data, 'columns'):
                self.converter.column_mapper.register_columns(list(data.columns))

            # Parse the formula
            try:
                parsed_formula, fields_used = self.parse(formula,
                                                         list(data.columns) if hasattr(data, 'columns') else None)
            except Exception as e:
                logger.error(f"Error parsing formula '{formula}': {e}")
                return {
                    'success': False,
                    'error': f"Error parsing formula: {str(e)}",
                    'parsed_formula': '',
                    'fields_used': []
                }

            # Debug
            logger.debug(f"Parsed formula: {parsed_formula}")
            logger.debug(f"Fields used: {fields_used}")

            # Check for missing fields
            if hasattr(data, 'columns'):
                missing_fields = [field for field in fields_used if field not in data.columns]
                if missing_fields:
                    return {
                        'success': False,
                        'error': f"Formula references fields not in the data: {', '.join(missing_fields)}",
                        'parsed_formula': parsed_formula,
                        'fields_used': list(fields_used)
                    }

            # Safely evaluate the formula
            restricted_globals = {"__builtins__": {}}
            safe_locals = {"df": data, "pd": pd, "np": np}

            # Add extra debug
            logger.debug(f"Evaluating formula: {parsed_formula}")

            try:
                result = eval(parsed_formula, restricted_globals, safe_locals)
            except Exception as e:
                logger.error(f"Error evaluating formula '{parsed_formula}': {e}")
                return {
                    'success': False,
                    'error': f"Error evaluating formula: {str(e)}",
                    'parsed_formula': parsed_formula,
                    'fields_used': list(fields_used)
                }

            # Ensure result is a boolean Series
            if not isinstance(result, pd.Series):
                result = pd.Series(result, index=data.index)

            if result.dtype != bool:
                try:
                    result = result.astype(bool)
                except:
                    return {
                        'success': False,
                        'error': "Formula result could not be converted to boolean values",
                        'parsed_formula': parsed_formula,
                        'fields_used': list(fields_used)
                    }

            # Calculate statistics
            total_records = len(data)
            passing_count = result.sum()
            failing_count = total_records - passing_count
            passing_pct = (passing_count / total_records * 100) if total_records > 0 else 0

            # Get example records
            max_examples = 3
            passing_examples = data[result].head(max_examples).to_dict('records') if passing_count > 0 else []
            failing_examples = data[~result].head(max_examples).to_dict('records') if failing_count > 0 else []

            return {
                'success': True,
                'parsed_formula': parsed_formula,
                'fields_used': list(fields_used),
                'total_records': total_records,
                'passing_count': int(passing_count),
                'failing_count': int(failing_count),
                'passing_percentage': f"{passing_pct:.1f}%",
                'passing_examples': passing_examples,
                'failing_examples': failing_examples
            }

        except Exception as e:
            logger.error(f"Error testing formula '{formula}': {e}")
            return {
                'success': False,
                'error': str(e),
                'parsed_formula': '',
                'fields_used': []
            }


def parse_excel_formula(formula: str, df_columns: Optional[List[str]] = None) -> Tuple[str, List[str]]:
    """
    Parse an Excel formula using the best available parser.

    This function provides a simple interface for other modules to use
    without worrying about which parser is being used underneath.

    Args:
        formula: Excel formula to parse
        df_columns: Optional list of DataFrame column names

    Returns:
        Tuple containing:
        - Pandas expression string
        - List of field names used in the formula
    """
    parsed_formula, fields = formula_converter.parse(formula, df_columns)
    return parsed_formula, list(fields)


def test_excel_formula(formula: str, data: Any) -> Dict:
    """
    Test an Excel formula against sample data.

    Args:
        formula: Excel formula to test
        data: DataFrame to test against

    Returns:
        Dictionary with test results
    """
    return formula_converter.test_formula(formula, data)

# Initialize the default converter when module is imported
formula_converter = FormulaConverterFacade()

# Configuration function to change parsers at runtime
def configure_formula_parser(use_new_converter: bool = True) -> None:
    """
    Configure which formula parser to use.

    Args:
        use_new_converter: Whether to use the new converter if available
    """
    global formula_converter
    formula_converter = FormulaConverterFacade(use_new_converter)
    logger.info(f"Formula parser configured to use {'new' if use_new_converter else 'legacy'} converter")