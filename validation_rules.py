import pandas as pd
import numpy as np
from typing import Dict, List
from logging_config import setup_logging

# Import our new converter integration
try:
    from excel_formula_converter_integration import parse_excel_formula
    HAS_NEW_CONVERTER = True
except ImportError:
    from excel_formula_parser import ExcelFormulaParser
    HAS_NEW_CONVERTER = False

logger = setup_logging()


class ValidationRules:
    """Validation logic based entirely on Excel-style formulas."""

    @staticmethod
    def custom_formula(df: pd.DataFrame, params: Dict) -> pd.Series:
        """
        Execute a user-defined Excel formula against the dataframe.

        Args:
            df: DataFrame containing the data to validate
            params: Dictionary with formula parameters:
                - formula: Pandas expression (parsed from original_formula)
                - original_formula: Original Excel-style formula

        Returns:
            Series with True for rows that conform, False for non-conforming
        """
        try:
            formula = params.get('formula')
            original = params.get('original_formula', 'Unknown formula')

            if not formula:
                if original and original != 'Unknown formula':
                    if HAS_NEW_CONVERTER:
                        formula, _ = parse_excel_formula(original, list(df.columns))
                    else:
                        parser = ExcelFormulaParser()
                        formula, _ = parser.parse(original)
                else:
                    logger.error("Missing formula parameter")
                    return pd.Series(False, index=df.index)

            restricted_globals = {"__builtins__": {}}
            safe_locals = {"df": df, "pd": pd, "np": np}

            result = eval(formula, restricted_globals, safe_locals)

            if not isinstance(result, pd.Series):
                logger.error(f"Formula did not return a Series: {original}")
                return pd.Series(False, index=df.index)

            if result.dtype != bool:
                try:
                    result = result.astype(bool)
                except (ValueError, TypeError) as e:
                    logger.error(f"Formula did not return boolean values: {original}. Error: {e}")
                    return pd.Series(False, index=df.index)

            return result

        except Exception as e:
            logger.error(f"Custom formula failed: {e}, Formula: {params.get('original_formula', 'Unknown')}")
            return pd.Series(False, index=df.index)
