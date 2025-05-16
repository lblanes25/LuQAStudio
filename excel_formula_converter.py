"""
Excel Formula to Pandas Expression Converter

This module provides a robust converter for transforming Excel-style formulas
into pandas expressions that can be evaluated against a DataFrame.
It uses xlcalculator for parsing and implements a visitor pattern to traverse
the syntax tree.

Example:
    converter = ExcelToPandasConverter()
    pandas_expr = converter.convert("IF(AND(Status=\"Active\", Value>100), \"High\", \"Low\")")
"""

import re
import sys
import traceback
from typing import Dict, List, Set, Tuple, Any, Union, Optional
import ast
import pandas as pd
import numpy as np
import logging

# Configure extensive logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def debug_print(prefix, value, max_len=2000):
    """Helper function to print debug info with truncation for large values"""
    str_value = str(value)
    if len(str_value) > max_len:
        str_value = str_value[:max_len] + "... [truncated]"
    logger.debug(f"{prefix}: {str_value}")

# Import xlcalculator components
try:
    logger.debug("Attempting to import xlcalculator components")
    from xlcalculator import ModelCompiler, Model, Evaluator
    from xlcalculator.xlfunctions import xl
    import xlcalculator.xlfunctions as xlfunctions
    logger.debug("Successfully imported xlcalculator components")
except ImportError as e:
    error_msg = "xlcalculator is required for this module. Install it using: pip install xlcalculator"
    logger.error(f"Import Error: {error_msg} - {str(e)}")
    raise ImportError(error_msg)


class ColumnMapper:
    """
    Handles bidirectional mapping between DataFrame column names and
    Excel-compatible identifiers.

    This class is responsible for:
    1. Converting DataFrame column names to Excel-safe identifiers
    2. Maintaining a mapping to translate back to original column names
    3. Handling columns with spaces and special characters
    """

    def __init__(self):
        """Initialize the column mapper."""
        logger.debug("Initializing ColumnMapper")
        self.df_to_excel = {}  # Maps DataFrame column name to Excel identifier
        self.excel_to_df = {}  # Maps Excel identifier to DataFrame column name

    def register_columns(self, columns: List[str]) -> None:
        """
        Register DataFrame column names and create Excel-safe identifiers.

        Args:
            columns: List of DataFrame column names to register
        """
        logger.debug(f"Registering columns: {columns}")
        for col in columns:
            if col not in self.df_to_excel:
                # Create Excel-safe identifier
                excel_name = self._create_excel_name(col)
                logger.debug(f"Created excel name '{excel_name}' for column '{col}'")

                # Ensure uniqueness by adding a suffix if needed
                base_name = excel_name
                counter = 1
                while excel_name in self.excel_to_df:
                    excel_name = f"{base_name}_{counter}"
                    counter += 1
                    logger.debug(f"Collision detected, using '{excel_name}' instead")

                # Store the mapping both ways
                self.df_to_excel[col] = excel_name
                self.excel_to_df[excel_name] = col
                logger.debug(f"Registered mapping: '{col}' <-> '{excel_name}'")

        # Log the complete mappings for debugging
        logger.debug(f"Complete df_to_excel mapping: {self.df_to_excel}")
        logger.debug(f"Complete excel_to_df mapping: {self.excel_to_df}")

    def _create_excel_name(self, column_name: str) -> str:
        """
        Create an Excel-safe identifier from a DataFrame column name.

        Args:
            column_name: DataFrame column name

        Returns:
            Excel-safe identifier
        """
        logger.debug(f"Creating Excel-safe name for '{column_name}'")

        # Replace spaces and special characters
        safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', column_name)
        logger.debug(f"After replacing special chars: '{safe_name}'")

        # Ensure it starts with a letter
        if not safe_name[0].isalpha() and safe_name[0] != '_':
            safe_name = 'col_' + safe_name
            logger.debug(f"Added prefix for non-alpha start: '{safe_name}'")

        logger.debug(f"Final Excel-safe name: '{safe_name}'")
        return safe_name

    def to_excel_name(self, df_column: str) -> str:
        """
        Convert DataFrame column name to Excel identifier.

        Args:
            df_column: DataFrame column name

        Returns:
            Excel-safe identifier
        """
        logger.debug(f"Converting DF column '{df_column}' to Excel name")
        if df_column not in self.df_to_excel:
            error_msg = f"Column '{df_column}' not registered"
            logger.error(error_msg)
            raise ValueError(error_msg)

        excel_name = self.df_to_excel[df_column]
        logger.debug(f"Excel name for '{df_column}' is '{excel_name}'")
        return excel_name

    def to_df_name(self, excel_name: str) -> str:
        """
        Convert Excel identifier to DataFrame column name.

        Args:
            excel_name: Excel identifier

        Returns:
            Original DataFrame column name
        """
        logger.debug(f"Converting Excel name '{excel_name}' to DF column")
        if excel_name not in self.excel_to_df:
            # It might be a literal or non-column reference
            logger.debug(f"Excel name '{excel_name}' not found in mapping, treating as literal")
            return excel_name

        df_name = self.excel_to_df[excel_name]
        logger.debug(f"DF column for '{excel_name}' is '{df_name}'")
        return df_name


class ExcelToPandasConverter:
    """
    Converts Excel formulas to pandas expressions using xlcalculator.

    This class parses Excel formulas and generates equivalent pandas code
    that can be evaluated against a DataFrame.
    """

    def __init__(self, debug_level=logging.DEBUG):
        """Initialize the converter."""
        logger.debug("Initializing ExcelToPandasConverter")
        self.column_mapper = ColumnMapper()
        self.fields_used = set()  # Set of DataFrame columns used in the formula

        # Configure logger for this class
        logging.getLogger(__name__).setLevel(debug_level)

        # Function mapping from Excel to pandas
        logger.debug("Setting up function mappings")
        self.function_map = {
            'IF': self._translate_if,
            'AND': self._translate_and,
            'OR': self._translate_or,
            'NOT': self._translate_not,
            'ISBLANK': self._translate_isblank,
            'ISERROR': self._translate_iserror,
            'ISNUMBER': self._translate_isnumber,
            'COUNT': self._translate_count,
            'COUNTIF': self._translate_countif,
            'SUM': self._translate_sum,
            'SUMIF': self._translate_sumif,
            'AVERAGE': self._translate_average,
            'MIN': self._translate_min,
            'MAX': self._translate_max,
            'LEFT': self._translate_left,
            'RIGHT': self._translate_right,
            'MID': self._translate_mid,
            'LEN': self._translate_len,
            'CONCATENATE': self._translate_concatenate,
            'TODAY': self._translate_today,
            'NOW': self._translate_now,
        }

        # Operator mapping from Excel to pandas
        logger.debug("Setting up operator mappings")
        self.operator_map = {
            '=': '==',
            '<>': '!=',
            '&': '+',  # String concatenation
        }
        logger.debug("Initialization complete")

    def convert(self, formula: str, df_columns: Optional[List[str]] = None) -> Tuple[str, Set[str]]:
        """
        Convert an Excel formula to a pandas expression.

        Args:
            formula: Excel formula to convert
            df_columns: Optional list of DataFrame column names

        Returns:
            Tuple containing:
            - Pandas expression string
            - Set of DataFrame column names used in the formula
        """
        logger.info(f"Converting formula: '{formula}'")
        logger.debug(f"DataFrame columns: {df_columns}")

        # Reset fields used
        self.fields_used = set()
        logger.debug("Reset fields_used set")

        # Register columns if provided
        if df_columns:
            logger.debug(f"Registering {len(df_columns)} DataFrame columns")
            self.column_mapper.register_columns(df_columns)

        try:
            # Create a mock workbook with the formula
            formula_cell = f'=({formula})'  # Wrap in parentheses for better parsing
            logger.debug(f"Wrapped formula: '{formula_cell}'")

            # Pre-process backtick-quoted field names
            processed_formula = formula_cell
            backtick_pattern = r'`([^`]+)`'
            backtick_matches = re.findall(backtick_pattern, formula_cell)
            logger.debug(f"Found backtick-quoted fields: {backtick_matches}")

            # Replace backtick-quoted names with placeholder names for parsing
            # and then track the replacements to restore them later
            placeholder_map = {}
            for i, field_name in enumerate(backtick_matches):
                placeholder = f"__PLACEHOLDER_{i}__"
                processed_formula = processed_formula.replace(f"`{field_name}`", placeholder)
                placeholder_map[placeholder] = field_name
                # Add to fields used
                self.fields_used.add(field_name)
                logger.debug(f"Replaced `{field_name}` with {placeholder}")

            logger.debug(f"Processed formula after backtick replacement: '{processed_formula}'")

            # Use the read_and_parse_dict method which is available in your API
            input_dict = {'Sheet1!A1': processed_formula}
            logger.debug(f"Creating input dictionary: {input_dict}")

            try:
                logger.debug("Initializing ModelCompiler")
                compiler = ModelCompiler()
                logger.debug("Calling read_and_parse_dict")
                model = compiler.read_and_parse_dict(input_dict, default_sheet='Sheet1')
                logger.debug("Successfully parsed formula with ModelCompiler")
            except Exception as e:
                logger.error(f"Error in ModelCompiler: {str(e)}")
                logger.debug(f"Exception details: {traceback.format_exc()}")
                raise ValueError(f"Failed to parse formula with ModelCompiler: {str(e)}")

            # Get the formula tokens - could be in either cells or formulae
            logger.debug("Attempting to retrieve formula tokens from model")
            formula_tokens = None

            # Try to retrieve tokens from different possible model structures
            if hasattr(model, 'cells') and 'Sheet1!A1' in model.cells:
                logger.debug("Found formula in model.cells")
                formula_tokens = model.cells['Sheet1!A1'].formula.tokens
            elif hasattr(model, 'formulae') and 'Sheet1!A1' in model.formulae:
                logger.debug("Found formula in model.formulae")
                formula_tokens = model.formulae['Sheet1!A1'].tokens
            else:
                logger.error("Could not locate formula in compiled model")
                raise ValueError("Could not locate formula in compiled model")

            logger.debug(f"Retrieved formula tokens: {formula_tokens}")

            # Debug token information
            token_details = []
            for t in formula_tokens:
                try:
                    token_info = f"{t.tvalue} (type:{t.ttype}, subtype:{t.tsubtype if hasattr(t, 'tsubtype') else 'N/A'})"
                    token_details.append(token_info)
                except Exception as e:
                    token_details.append(f"Error getting token info: {str(e)}")

            logger.debug(f"Token details: {token_details}")

            # Now use our token-based translator
            logger.debug("Starting token translation")
            pandas_expr = self._translate_tokens(formula_tokens)
            logger.debug(f"Initial translated expression: '{pandas_expr}'")

            # Log detailed conversion info
            logger.info(f"Original formula: {formula}")
            logger.info(f"Translated expression (before fixes): {pandas_expr}")

            # Fix common syntax issues before validation
            logger.debug("Applying syntax fixes")

            # 1. Fix missing operators between conditions in formulas like AND(Status="Active", Value>100)
            logger.debug("Fix 1: Adding operators between conditions")
            original_expr = pandas_expr
            pandas_expr = re.sub(r'(df\[[\'"][^\'"]+[\'"]\]\s*[=<>!]+\s*[^&|<>=!]+)(\s+df\[)',
                                r'\1 & \2', pandas_expr)
            if original_expr != pandas_expr:
                logger.debug(f"Fix 1 applied: '{original_expr}' -> '{pandas_expr}'")

            # Also catch multi-word column names in conditions
            original_expr = pandas_expr
            pandas_expr = re.sub(r'(df\[[\'"][^\'"]+[\'"]\]\s*[=<>!]+\s*[^&|<>=!]+)(\s+df\[[\'"]\w+\s+\w+)',
                                r'\1 & \2', pandas_expr)
            if original_expr != pandas_expr:
                logger.debug(f"Fix 1b applied: '{original_expr}' -> '{pandas_expr}'")

            # More aggressive pattern for missing operators
            original_expr = pandas_expr
            pandas_expr = re.sub(r'(df\[[\'"][^\'"\[\]]+[\'"]\]\s*[=<>!]+\s*[^&|<>=!\[\]]+)(\s+df\[[\'"])',
                                r'\1 & \2', pandas_expr)
            if original_expr != pandas_expr:
                logger.debug(f"Fix 1c applied: '{original_expr}' -> '{pandas_expr}'")

            # 2. Properly handle multi-word column names
            logger.debug("Fix 2: Handling multi-word column names")
            # Replace unquoted spaces in column names with quoted versions
            original_expr = pandas_expr
            pandas_expr = re.sub(r'df\[([^\'"].*?\s+.*?[^\'"]*)\]', r"df['\1']", pandas_expr)
            if original_expr != pandas_expr:
                logger.debug(f"Fix 2 applied: '{original_expr}' -> '{pandas_expr}'")

            # Restore backtick-quoted fields
            logger.debug("Restoring backtick-quoted fields")
            for placeholder, field_name in placeholder_map.items():
                original_expr = pandas_expr
                pandas_expr = pandas_expr.replace(f"df['{placeholder}']", f"df['{field_name}']")
                if original_expr != pandas_expr:
                    logger.debug(f"Replaced df['{placeholder}'] with df['{field_name}']")

                original_expr = pandas_expr
                pandas_expr = pandas_expr.replace(f"df[\"{placeholder}\"]", f"df['{field_name}']")
                if original_expr != pandas_expr:
                    logger.debug(f"Replaced df[\"{placeholder}\"] with df['{field_name}']")

                original_expr = pandas_expr
                pandas_expr = pandas_expr.replace(placeholder, field_name)
                if original_expr != pandas_expr:
                    logger.debug(f"Replaced {placeholder} with {field_name}")

            # 3. Add parentheses around conditions in AND/OR expressions to ensure proper precedence
            logger.debug("Fix 3: Adding parentheses around conditions for precedence")
            original_expr = pandas_expr
            pandas_expr = re.sub(r'([^(])(df\[[^\]]+\][^&|)]*[=<>!]+[^&|)]+)(\s+[&|]\s+)',
                                r'\1(\2)\3', pandas_expr)
            if original_expr != pandas_expr:
                logger.debug(f"Fix 3a applied: '{original_expr}' -> '{pandas_expr}'")

            original_expr = pandas_expr
            pandas_expr = re.sub(r'(\s+[&|]\s+)([^(][^&|)]*df\[[^\]]+\][^&|)]*[=<>!]+[^&|)]+)([^)]|$)',
                                r'\1(\2)\3', pandas_expr)
            if original_expr != pandas_expr:
                logger.debug(f"Fix 3b applied: '{original_expr}' -> '{pandas_expr}'")

            logger.debug(f"Expression after all fixes: '{pandas_expr}'")

            # Validate the expression by parsing it with ast (will catch syntax errors)
            try:
                logger.debug("Validating expression with ast.parse")
                ast.parse(pandas_expr)
                logger.debug("Expression parsed successfully")
            except SyntaxError as e:
                logger.error(f"Generated invalid Python syntax: {pandas_expr}")
                logger.debug(f"Syntax error details: {str(e)}")

                # Try extra emergency fixes
                logger.debug("Attempting emergency fixes for syntax errors")
                fixed = False

                try:
                    # First try: Check for missing operators
                    if " " in pandas_expr and "df[" in pandas_expr:
                        logger.debug("Emergency fix 1: Checking for missing operators")
                        # Find sequences of conditions without operators between them
                        condition_pattern = r'(df\[[^\]]+\]\s*[=<>!]+\s*[^&|<>=!]+)(\s+df\[)'
                        if re.search(condition_pattern, pandas_expr):
                            original_expr = pandas_expr
                            fixed_expr = re.sub(condition_pattern, r'\1 & \2', pandas_expr)
                            logger.debug(f"Emergency fix 1 applied: '{original_expr}' -> '{fixed_expr}'")
                            try:
                                ast.parse(fixed_expr)
                                pandas_expr = fixed_expr
                                fixed = True
                                logger.debug("Emergency fix 1 successful")
                            except SyntaxError as fix_e:
                                logger.debug(f"Emergency fix 1 failed: {str(fix_e)}")

                    # Second try: Check for unbalanced quotes in column names
                    if not fixed:
                        logger.debug("Emergency fix 2: Checking for unbalanced quotes")
                        quote_issue = re.search(r'df\[(\'|")[^\'"]+(\'|")\]', pandas_expr)
                        if quote_issue:
                            original_expr = pandas_expr
                            fixed_expr = re.sub(r'df\[(\'|")([^\'"+]+)(\'|")\]', r"df['\2']", pandas_expr)
                            logger.debug(f"Emergency fix 2 applied: '{original_expr}' -> '{fixed_expr}'")
                            try:
                                ast.parse(fixed_expr)
                                pandas_expr = fixed_expr
                                fixed = True
                                logger.debug("Emergency fix 2 successful")
                            except SyntaxError as fix_e:
                                logger.debug(f"Emergency fix 2 failed: {str(fix_e)}")

                    # Third try: Multi-word column issues with spaces
                    if not fixed and "df[" in pandas_expr and " " in pandas_expr:
                        logger.debug("Emergency fix 3: Fixing multi-word column issues")
                        # Replace df[column name] with df['column name']
                        original_expr = pandas_expr
                        fixed_expr = re.sub(r'df\[([^\'"][^\]]*\s+[^\]]*)\]', r"df['\1']", pandas_expr)
                        logger.debug(f"Emergency fix 3 applied: '{original_expr}' -> '{fixed_expr}'")
                        try:
                            ast.parse(fixed_expr)
                            pandas_expr = fixed_expr
                            fixed = True
                            logger.debug("Emergency fix 3 successful")
                        except SyntaxError as fix_e:
                            logger.debug(f"Emergency fix 3 failed: {str(fix_e)}")

                    # Last attempt: Fix spaces between df references
                    if not fixed and " df[" in pandas_expr:
                        logger.debug("Emergency fix 4: Fixing spaces between df references")
                        original_expr = pandas_expr
                        fixed_expr = re.sub(r'(\S)\s+df\[', r'\1 & df[', pandas_expr)
                        logger.debug(f"Emergency fix 4 applied: '{original_expr}' -> '{fixed_expr}'")
                        try:
                            ast.parse(fixed_expr)
                            pandas_expr = fixed_expr
                            fixed = True
                            logger.debug("Emergency fix 4 successful")
                        except SyntaxError as fix_e:
                            logger.debug(f"Emergency fix 4 failed: {str(fix_e)}")

                    # Final validation
                    try:
                        ast.parse(pandas_expr)
                        logger.debug("Final validation successful after emergency fixes")
                    except SyntaxError as final_e:
                        # If all fixes fail, raise the original error
                        logger.error(f"All emergency fixes failed. Final expression: '{pandas_expr}'")
                        raise ValueError(f"Generated invalid Python syntax after all emergency fixes: {final_e}")

                except Exception as fix_error:
                    # If something goes wrong in our fix attempts, raise the original error
                    logger.error(f"Error during emergency fixes: {str(fix_error)}")
                    raise ValueError(f"Generated invalid Python syntax: {e}")

            # If it's already wrapped in np.where or looks like a full Series, don't wrap again
            logger.debug("Checking if expression needs wrapping")
            if pandas_expr.startswith("np.where") or pandas_expr.startswith("pd.Series("):
                final_expr = pandas_expr
                logger.debug(f"No wrapping needed, expression starts with np.where or pd.Series")
            else:
                final_expr = f"pd.Series(({pandas_expr}), index=df.index)"
                logger.debug(f"Wrapped expression in pd.Series(): '{final_expr}'")

            logger.info(f"Final converted expression: '{final_expr}'")
            logger.info(f"Fields used in the formula: {self.fields_used}")
            return final_expr, self.fields_used

        except Exception as e:
            # Handle parsing errors
            error_msg = f"Error converting formula: {formula}. {str(e)}"
            logger.error(error_msg)
            logger.debug(f"Exception traceback: {traceback.format_exc()}")
            raise ValueError(error_msg)

    def _translate_tokens(self, tokens) -> str:
        """
        Translate Excel formula tokens to pandas code.

        Args:
            tokens: List of token objects from xlcalculator

        Returns:
            Pandas code as a string
        """
        # Log the tokens we're working with
        logger.debug("Starting token translation")
        token_info = []
        for t in tokens:
            try:
                token_info.append(f"{t.tvalue} ({t.ttype}, {t.tsubtype if hasattr(t, 'tsubtype') else 'N/A'})")
            except Exception as e:
                token_info.append(f"Error getting token info: {str(e)}")

        logger.debug(f"Processing tokens: {token_info}")

        # First, extract information from tokens
        formula_elements = []
        i = 0

        while i < len(tokens):
            token = tokens[i]

            # Debug current token
            try:
                t_value = token.tvalue if hasattr(token, 'tvalue') else str(token)
                t_type = token.ttype if hasattr(token, 'ttype') else "unknown"
                t_subtype = token.tsubtype if hasattr(token, 'tsubtype') else "N/A"
                logger.debug(f"Processing token at index {i}: {t_value} (type:{t_type}, subtype:{t_subtype})")
            except Exception as e:
                logger.debug(f"Error debugging token at index {i}: {str(e)}")

            # Skip subexpression markers
            if hasattr(token, 'tsubtype') and (token.tsubtype == 'start' or token.tsubtype == 'stop'):
                logger.debug(f"Skipping subexpression marker at index {i}")
                i += 1
                continue

            # Handle functions
            if hasattr(token, 'ttype') and token.ttype == 'function' and hasattr(token, 'tsubtype') and token.tsubtype == 'start':
                func_name = token.tvalue.upper()
                logger.debug(f"Processing function: {func_name} at index {i}")

                # Find the corresponding end token
                j = i + 1
                nesting = 1  # Track nested functions
                args = []
                current_arg = []

                logger.debug(f"Collecting arguments for function {func_name}")

                while j < len(tokens) and nesting > 0:
                    curr_token = tokens[j]
                    try:
                        curr_t_value = curr_token.tvalue if hasattr(curr_token, 'tvalue') else str(curr_token)
                        curr_t_type = curr_token.ttype if hasattr(curr_token, 'ttype') else "unknown"
                        curr_t_subtype = curr_token.tsubtype if hasattr(curr_token, 'tsubtype') else "N/A"
                        logger.debug(f"  Arg token at index {j}: {curr_t_value} (type:{curr_t_type}, subtype:{curr_t_subtype})")
                    except Exception as e:
                        logger.debug(f"  Error debugging arg token at index {j}: {str(e)}")

                    if hasattr(curr_token, 'ttype') and curr_token.ttype == 'function' and hasattr(curr_token, 'tsubtype') and curr_token.tsubtype == 'start':
                        nesting += 1
                        logger.debug(f"  Nested function start, nesting level: {nesting}")
                    elif hasattr(curr_token, 'ttype') and curr_token.ttype == 'function' and hasattr(curr_token, 'tsubtype') and curr_token.tsubtype == 'stop':
                        nesting -= 1
                        logger.debug(f"  Function end, nesting level: {nesting}")
                        if nesting == 0:  # End of this function
                            if current_arg:
                                processed_arg = self._process_argument(current_arg)
                                logger.debug(f"  Adding final argument: {processed_arg}")
                                args.append(processed_arg)
                            break
                    elif hasattr(curr_token, 'ttype') and curr_token.ttype == 'argument' and nesting == 1:
                        # Save the current argument and start a new one
                        processed_arg = self._process_argument(current_arg)
                        logger.debug(f"  Argument separator, adding argument: {processed_arg}")
                        args.append(processed_arg)
                        current_arg = []
                    else:
                        current_arg.append(curr_token)
                    j += 1

                # Process the function
                logger.debug(f"All arguments for {func_name}: {args}")
                if func_name in self.function_map:
                    result = self._translate_function(func_name, args)
                    logger.debug(f"Translated {func_name} function to: {result}")
                    formula_elements.append(result)
                else:
                    # Generic function handling
                    processed_args = [self._process_argument(arg) for arg in args]
                    result = f"{func_name.lower()}({', '.join(processed_args)})"
                    logger.debug(f"Generic function translation: {result}")
                    formula_elements.append(result)

                i = j + 1  # Skip to after the function
                logger.debug(f"Moving to token index {i} after function processing")

            # Handle operands (values, column references)
            elif hasattr(token, 'ttype') and token.ttype == 'operand':
                if hasattr(token, 'tsubtype') and token.tsubtype == 'range':
                    # Column name handling
                    column_name = token.tvalue
                    logger.debug(f"Processing range operand (column): '{column_name}' at index {i}")

                    # Check if it's part of a multi-word column
                    if i + 2 < len(tokens) and hasattr(tokens[i + 1], 'ttype') and (
                        (tokens[i + 1].ttype == 'operator-infix' and hasattr(tokens[i + 1], 'tsubtype') and tokens[i + 1].tsubtype == 'intersect') or
                        (tokens[i + 1].tvalue == ' ' or tokens[i + 1].tvalue == ' ')  # Also detect space tokens
                    ):
                        # Collect all parts of the column name
                        column_parts = [column_name]
                        j = i + 1

                        logger.debug(f"Detected potential multi-word column starting with '{column_name}'")

                        # Loop to collect all parts of a multi-word column
                        while j + 1 < len(tokens) and hasattr(tokens[j], 'ttype') and (
                            (tokens[j].ttype == 'operator-infix' and hasattr(tokens[j], 'tsubtype') and tokens[j].tsubtype == 'intersect') or
                            (tokens[j].tvalue == ' ' or tokens[j].tvalue == ' ')  # Space tokens
                        ):
                            next_token = tokens[j + 1]
                            next_value = next_token.tvalue if hasattr(next_token, 'tvalue') else str(next_token)
                            logger.debug(f"  Adding part to multi-word column: '{next_value}'")
                            column_parts.append(next_value)
                            j += 2

                        # Join the parts to form the full column name
                        full_column = " ".join(column_parts)

                        # Clean up any extra spaces
                        full_column = re.sub(r'\s+', ' ', full_column).strip()

                        logger.debug(f"Found multi-word column: '{full_column}'")

                        # Add to fields used
                        self.fields_used.add(full_column)
                        formula_elements.append(f"df['{full_column}']")
                        logger.debug(f"Added multi-word column reference: df['{full_column}']")

                        i = j  # Skip ahead
                        logger.debug(f"Moving to token index {i} after multi-word column")
                    else:
                        # Single word column
                        logger.debug(f"Single word column: '{column_name}'")
                        self.fields_used.add(column_name)
                        formula_elements.append(f"df['{column_name}']")
                        logger.debug(f"Added single-word column reference: df['{column_name}']")
                        i += 1

                elif hasattr(token, 'tsubtype') and token.tsubtype == 'text':
                    # String literal
                    logger.debug(f"Processing text operand: '{token.tvalue}' at index {i}")
                    formula_elements.append(f'"{token.tvalue}"')
                    logger.debug(f"Added string literal: \"{token.tvalue}\"")
                    i += 1

                elif hasattr(token, 'tsubtype') and token.tsubtype == 'number':
                    # Numeric literal
                    logger.debug(f"Processing number operand: {token.tvalue} at index {i}")
                    formula_elements.append(token.tvalue)
                    logger.debug(f"Added numeric literal: {token.tvalue}")
                    i += 1

                else:
                    # Other operand types
                    token_value = token.tvalue if hasattr(token, 'tvalue') else str(token)
                    logger.debug(f"Processing other operand: '{token_value}' at index {i}")
                    formula_elements.append(str(token_value))
                    logger.debug(f"Added operand as string: '{token_value}'")
                    i += 1

            # Handle operators
            elif hasattr(token, 'ttype') and token.ttype.startswith('operator'):
                op = token.tvalue
                logger.debug(f"Processing operator: '{op}' at index {i}")

                # Skip intersection operators as they're handled with column names
                if hasattr(token, 'tsubtype') and token.tsubtype == 'intersect':
                    logger.debug(f"Skipping intersection operator")
                    i += 1
                    continue

                # Map Excel operators to pandas operators
                if op in self.operator_map:
                    mapped_op = self.operator_map[op]
                    logger.debug(f"Mapped operator '{op}' to '{mapped_op}'")
                    op = mapped_op

                formula_elements.append(op)
                logger.debug(f"Added operator: '{op}'")
                i += 1

            else:
                # Skip other token types or append them as is
                token_desc = str(token)
                logger.debug(f"Skipping or default handling for token at index {i}: {token_desc}")
                i += 1

        # Combine elements into a single expression
        if not formula_elements:
            logger.warning("No formula elements found, defaulting to 'False'")
            return "False"  # Default expression if no elements

        final_expr = " ".join(formula_elements)
        logger.debug(f"Final expression from token translation: '{final_expr}'")
        return final_expr

    def _process_argument(self, tokens) -> str:
        """Process a single function argument"""
        logger.debug(f"Processing function argument with {len(tokens)} tokens")
        if not tokens:
            logger.debug("Empty argument, returning default empty string")
            return '""'  # Empty argument default

        # Debug token info before processing
        token_info = []
        for t in tokens:
            try:
                t_value = t.tvalue if hasattr(t, 'tvalue') else str(t)
                t_type = t.ttype if hasattr(t, 'ttype') else "unknown"
                t_subtype = t.tsubtype if hasattr(t, 'tsubtype') else "N/A"
                token_info.append(f"{t_value} ({t_type}, {t_subtype})")
            except Exception as e:
                token_info.append(f"Error: {str(e)}")

        logger.debug(f"Argument tokens: {token_info}")

        # Process the tokens into a pandas expression
        result = self._translate_tokens(tokens)
        logger.debug(f"Translated argument result: '{result}'")

        # Make sure arguments to logical functions are properly parenthesized
        # This helps in AND/OR functions to ensure each condition is treated as a separate boolean
        if result and any(op in result for op in ['==', '!=', '<', '>', '<=', '>=']) and not result.startswith('('):
            original = result
            result = f"({result})"
            logger.debug(f"Added parentheses to logical condition: '{original}' -> '{result}'")

        return result

    def _translate_function(self, func_name: str, args: List[str]) -> str:
        """Translate an Excel function to pandas code"""
        logger.debug(f"Translating function {func_name} with args: {args}")

        if func_name in self.function_map:
            logger.debug(f"Using specialized translator for function {func_name}")
            translator_method = self.function_map[func_name]

            try:
                # Here we'll convert from the old _translate_if(node) format
                # to an actual method call with args
                if func_name == 'IF':
                    if len(args) < 2:
                        logger.warning("IF function requires at least 2 arguments, using default")
                        return 'False'  # Default for malformed IF
                    condition = args[0]
                    true_value = args[1] if len(args) > 1 else 'True'
                    false_value = args[2] if len(args) > 2 else 'False'
                    result = f"np.where({condition}, {true_value}, {false_value})"
                    logger.debug(f"Translated IF function: {result}")
                    return result

                elif func_name == 'AND':
                    if not args:
                        logger.debug("Empty AND, returning True")
                        return 'True'  # Empty AND is True
                    conditions = [f"({arg})" for arg in args]
                    result = " & ".join(conditions)
                    logger.debug(f"Translated AND function: {result}")
                    return result

                elif func_name == 'OR':
                    if not args:
                        logger.debug("Empty OR, returning False")
                        return 'False'  # Empty OR is False
                    conditions = [f"({arg})" for arg in args]
                    result = " | ".join(conditions)
                    logger.debug(f"Translated OR function: {result}")
                    return result

                elif func_name == 'NOT':
                    if not args:
                        logger.debug("Empty NOT, returning True")
                        return 'True'  # Default for empty NOT
                    result = f"~({args[0]})"
                    logger.debug(f"Translated NOT function: {result}")
                    return result

                elif func_name == 'ISBLANK':
                    if not args:
                        logger.debug("Empty ISBLANK, returning False")
                        return 'False'
                    result = f"pd.isna({args[0]})"
                    logger.debug(f"Translated ISBLANK function: {result}")
                    return result

                # For other functions, try calling the actual method
                try:
                    logger.debug(f"Calling translator method for {func_name}")
                    # We're building a mock node structure for compatibility
                    mock_node = [func_name.lower()] + args
                    result = translator_method(mock_node)
                    logger.debug(f"Function translation result: {result}")
                    return result
                except Exception as e:
                    logger.error(f"Error in specialized translator for {func_name}: {str(e)}")
                    logger.debug(f"Function translator error details: {traceback.format_exc()}")

                    # Fall back to generic handling
                    logger.debug(f"Falling back to generic function handling for {func_name}")
                    return f"{func_name.lower()}({', '.join(args)})"

            except Exception as e:
                logger.error(f"Error translating function {func_name}: {str(e)}")
                logger.debug(f"Error details: {traceback.format_exc()}")
                return f"{func_name.lower()}({', '.join(args)})"  # Fallback
        else:
            # Generic function handling
            logger.debug(f"Using generic translator for function {func_name}")
            result = f"{func_name.lower()}({', '.join(args)})"
            logger.debug(f"Generic function translation: {result}")
            return result

    def _translate_node(self, node) -> str:
        """
        Recursively translate a node in the formula AST to pandas code.

        Args:
            node: AST node from xlcalculator

        Returns:
            Pandas code fragment as a string
        """
        logger.debug(f"Translating node: {node}")

        if isinstance(node, list):
            # Handle function calls or operations
            if len(node) > 0 and isinstance(node[0], str) and node[0].upper() in self.function_map:
                # Use the specific translator for this function
                function_name = node[0].upper()
                logger.debug(f"Translating function node: {function_name}")
                return self.function_map[function_name](node)

            # Handle binary operations
            elif len(node) == 3:
                logger.debug(f"Translating binary operation node: {node}")
                left = self._translate_node(node[0])
                operator = node[1]
                right = self._translate_node(node[2])

                # Map Excel operators to pandas operators
                if operator in self.operator_map:
                    operator = self.operator_map[operator]
                    logger.debug(f"Mapped operator '{node[1]}' to '{operator}'")

                result = f"({left} {operator} {right})"
                logger.debug(f"Binary operation result: {result}")
                return result

            # Handle other list structures - might be a complex expression
            elif len(node) > 0 and isinstance(node[0], str):
                # Try to handle as a function call
                logger.debug(f"Translating function-like node: {node}")
                function_name = node[0].upper()
                args = [self._translate_node(arg) for arg in node[1:]]
                result = f"{function_name.lower()}({', '.join(args)})"
                logger.debug(f"Function-like node result: {result}")
                return result
            else:
                # Unknown list structure
                logger.warning(f"Unknown list structure: {node}")
                return str(node)

        elif isinstance(node, (int, float)):
            # Handle numeric literals
            logger.debug(f"Translating numeric literal: {node}")
            return str(node)

        elif isinstance(node, str):
            # Handle string literals, column references, etc.
            logger.debug(f"Translating string node: '{node}'")

            if node.startswith('"') and node.endswith('"'):
                # String literal - already quoted
                logger.debug(f"Already quoted string literal: {node}")
                return node
            elif node.startswith("'") and node.endswith("'"):
                # String literal with single quotes - convert to double quotes
                result = f'"{node[1:-1]}"'
                logger.debug(f"Converted single-quoted string to double-quoted: {result}")
                return result
            else:
                # Check if it's a column reference
                column_name = node
                logger.debug(f"Processing potential column name: '{column_name}'")

                # Handle backtick-quoted column names
                if column_name.startswith('`') and column_name.endswith('`'):
                    column_name = column_name[1:-1]
                    logger.debug(f"Removed backticks from column name: '{column_name}'")

                # Try to find in column mapping
                if column_name in self.column_mapper.excel_to_df:
                    df_column = self.column_mapper.to_df_name(column_name)
                    self.fields_used.add(df_column)
                    result = f"df['{df_column}']"
                    logger.debug(f"Mapped column '{column_name}' to '{result}'")
                    return result

                # If it contains spaces, it's likely a column name not in our mapping
                if ' ' in column_name:
                    self.fields_used.add(column_name)
                    result = f"df['{column_name}']"
                    logger.debug(f"Multi-word column reference: {result}")
                    return result

                # Otherwise treat as a literal or full column name
                if column_name.isdigit() or (column_name[0] == '-' and column_name[1:].isdigit()):
                    logger.debug(f"Numeric literal as string: {column_name}")
                    return column_name  # Numeric literal
                else:
                    # Could be an unquoted column name
                    self.fields_used.add(column_name)
                    result = f"df['{column_name}']"
                    logger.debug(f"Unquoted column reference: {result}")
                    return result

        # Handle other types
        logger.debug(f"Translating other node type: {type(node)}")
        result = str(node)
        logger.debug(f"Converted to string: {result}")
        return result

    def _translate_if(self, node) -> str:
        """Translate IF function to numpy.where."""
        logger.debug(f"Translating IF function: {node}")

        if len(node) < 4:
            error_msg = "IF function requires at least 3 arguments"
            logger.error(error_msg)
            raise ValueError(error_msg)

        condition = self._translate_node(node[1])
        logger.debug(f"IF condition: {condition}")

        true_value = self._translate_node(node[2])
        logger.debug(f"IF true value: {true_value}")

        false_value = self._translate_node(node[3]) if len(node) > 3 else '"False"'
        logger.debug(f"IF false value: {false_value}")

        result = f"np.where({condition}, {true_value}, {false_value})"
        logger.debug(f"IF translation result: {result}")
        return result

    def _translate_and(self, node) -> str:
        """Translate AND function to bitwise &."""
        logger.debug(f"Translating AND function: {node}")

        if len(node) < 2:
            error_msg = "AND function requires at least 1 argument"
            logger.error(error_msg)
            raise ValueError(error_msg)

        conditions = [self._translate_node(arg) for arg in node[1:]]
        logger.debug(f"AND conditions: {conditions}")

        # We need each condition to be a boolean Series before combining
        processed_conditions = []
        for i, cond in enumerate(conditions):
            logger.debug(f"Processing AND condition {i}: {cond}")

            # Make sure each condition is properly parenthesized for precedence
            if not (cond.startswith('(') and cond.endswith(')')):
                processed_cond = f"({cond})"
                logger.debug(f"Added parentheses to AND condition: {cond} -> {processed_cond}")
                cond = processed_cond

            # Ensure it's a boolean Series
            processed_conditions.append(cond)
            logger.debug(f"Added processed condition: {cond}")

        # Convert scalar True/False to Series if needed
        for i, cond in enumerate(processed_conditions):
            if cond in ["(True)", "(False)"]:
                new_cond = f"pd.Series({cond}, index=df.index)"
                logger.debug(f"Converting scalar condition to Series: {cond} -> {new_cond}")
                processed_conditions[i] = new_cond

        # Join with & operator - this performs element-wise AND
        if len(processed_conditions) == 1:
            logger.debug(f"Single AND condition, returning as is: {processed_conditions[0]}")
            return processed_conditions[0]

        result = " & ".join(processed_conditions)
        logger.debug(f"AND result: {result}")
        return result

    def _translate_or(self, node) -> str:
        """Translate OR function to bitwise |."""
        logger.debug(f"Translating OR function: {node}")

        if len(node) < 2:
            error_msg = "OR function requires at least 1 argument"
            logger.error(error_msg)
            raise ValueError(error_msg)

        conditions = [self._translate_node(arg) for arg in node[1:]]
        logger.debug(f"OR conditions: {conditions}")

        # We need each condition to be a separate boolean Series before combining
        processed_conditions = []
        for i, cond in enumerate(conditions):
            logger.debug(f"Processing OR condition {i}: {cond}")

            # If it's a simple field name without a comparison, assume we want equality check with True
            if "df[" in cond and not any(op in cond for op in ["==", "!=", "<", ">", "<=", ">="]):
                # For field names by themselves in logical expressions, check if they equal "True"
                new_cond = f"({cond} == True)"
                logger.debug(f"Converting field to boolean comparison: {cond} -> {new_cond}")
                processed_conditions.append(new_cond)
            else:
                # For conditions with comparisons, wrap in parentheses for proper precedence
                new_cond = f"({cond})"
                logger.debug(f"Adding parentheses to OR condition: {cond} -> {new_cond}")
                processed_conditions.append(new_cond)

        # For a single condition, just return it
        if len(processed_conditions) == 1:
            logger.debug(f"Single OR condition, returning: {processed_conditions[0]}")
            return processed_conditions[0]

        # Join all conditions with | operator, ensure each is a boolean series
        joined_conditions = []
        for i, cond in enumerate(processed_conditions):
            if "pd.Series" not in cond:
                new_cond = f"pd.Series({cond}, index=df.index).astype(bool)"
                logger.debug(f"Converting to Series for OR condition: {cond} -> {new_cond}")
                joined_conditions.append(new_cond)
            else:
                logger.debug(f"Keeping Series condition as is: {cond}")
                joined_conditions.append(cond)

        # OR all conditions together
        result = " | ".join(joined_conditions)
        logger.debug(f"OR joined result: {result}")

        # Make sure the final result is properly wrapped
        final_result = f"({result})"
        logger.debug(f"Final OR result: {final_result}")
        return final_result

    def _translate_not(self, node) -> str:
        """Translate NOT function to unary ~."""
        logger.debug(f"Translating NOT function: {node}")

        if len(node) != 2:
            error_msg = "NOT function requires exactly 1 argument"
            logger.error(error_msg)
            raise ValueError(error_msg)

        condition = self._translate_node(node[1])
        logger.debug(f"NOT condition: {condition}")

        # Ensure the condition is wrapped as a Series for bitwise operation
        result = f"~pd.Series({condition}, index=df.index).astype(bool)"
        logger.debug(f"NOT result: {result}")
        return result

    def _translate_isblank(self, node) -> str:
        """Translate ISBLANK function to pd.isna."""
        logger.debug(f"Translating ISBLANK function: {node}")

        if len(node) != 2:
            error_msg = "ISBLANK function requires exactly 1 argument"
            logger.error(error_msg)
            raise ValueError(error_msg)

        value = self._translate_node(node[1])
        logger.debug(f"ISBLANK value: {value}")

        result = f"pd.isna({value})"
        logger.debug(f"ISBLANK result: {result}")
        return result

    def _translate_iserror(self, node) -> str:
        """Translate ISERROR function to custom error checking."""
        logger.debug(f"Translating ISERROR function: {node}")

        if len(node) != 2:
            error_msg = "ISERROR function requires exactly 1 argument"
            logger.error(error_msg)
            raise ValueError(error_msg)

        value = self._translate_node(node[1])
        logger.debug(f"ISERROR value: {value}")

        # This is a simplified version - a more complete version would handle more error types
        result = f"pd.Series([isinstance(x, (ValueError, TypeError, ZeroDivisionError)) for x in {value}], index=df.index)"
        logger.debug(f"ISERROR result: {result}")
        return result

    def _translate_isnumber(self, node) -> str:
        """Translate ISNUMBER function to pd.to_numeric with error handling."""
        logger.debug(f"Translating ISNUMBER function: {node}")

        if len(node) != 2:
            error_msg = "ISNUMBER function requires exactly 1 argument"
            logger.error(error_msg)
            raise ValueError(error_msg)

        value = self._translate_node(node[1])
        logger.debug(f"ISNUMBER value: {value}")

        result = f"pd.to_numeric({value}, errors='coerce').notna()"
        logger.debug(f"ISNUMBER result: {result}")
        return result

    def _translate_count(self, node) -> str:
        """Translate COUNT function."""
        logger.debug(f"Translating COUNT function: {node}")

        if len(node) < 2:
            error_msg = "COUNT function requires at least 1 argument"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Count non-NA values across multiple columns/ranges
        ranges = [self._translate_node(arg) for arg in node[1:]]
        logger.debug(f"COUNT ranges: {ranges}")

        counts = [f"{r}.count()" for r in ranges]
        logger.debug(f"COUNT count expressions: {counts}")

        result = " + ".join(counts)
        logger.debug(f"COUNT result: {result}")
        return result

    def _translate_countif(self, node) -> str:
        """Translate COUNTIF function."""
        logger.debug(f"Translating COUNTIF function: {node}")

        if len(node) != 3:
            error_msg = "COUNTIF function requires exactly 2 arguments"
            logger.error(error_msg)
            raise ValueError(error_msg)

        range_expr = self._translate_node(node[1])
        logger.debug(f"COUNTIF range: {range_expr}")

        criteria = self._translate_node(node[2])
        logger.debug(f"COUNTIF criteria: {criteria}")

        # Handle various criteria formats
        comparison = None
        logger.debug(f"Processing COUNTIF criteria: {criteria}")

        if criteria.startswith('"') and criteria.endswith('"'):
            # String criteria - remove quotes
            criteria_str = criteria.strip('"')
            logger.debug(f"COUNTIF string criteria: {criteria_str}")

            # Check if it's a comparison operator
            if criteria_str.startswith(('=', '>', '<', '>=', '<=', '<>')):
                operator = criteria_str[0]
                if criteria_str.startswith(('>=', '<=', '<>')):
                    operator = criteria_str[:2]
                    value = criteria_str[2:]
                else:
                    value = criteria_str[1:]

                logger.debug(f"COUNTIF operator: {operator}, value: {value}")

                # Map to Python operator
                if operator == '=':
                    comparison = f"{range_expr} == {value}"
                elif operator == '<>':
                    comparison = f"{range_expr} != {value}"
                else:
                    comparison = f"{range_expr} {operator} {value}"

                logger.debug(f"COUNTIF comparison: {comparison}")
            else:
                # Exact match
                comparison = f"{range_expr} == {criteria}"
                logger.debug(f"COUNTIF exact match: {comparison}")
        else:
            # Numeric or field criteria
            comparison = f"{range_expr} == {criteria}"
            logger.debug(f"COUNTIF numeric/field match: {comparison}")

        # Count True values
        result = f"({comparison}).sum()"
        logger.debug(f"COUNTIF result: {result}")
        return result

    def _translate_sum(self, node) -> str:
        """Translate SUM function."""
        logger.debug(f"Translating SUM function: {node}")

        if len(node) < 2:
            error_msg = "SUM function requires at least 1 argument"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Sum values across multiple columns/ranges
        ranges = [self._translate_node(arg) for arg in node[1:]]
        logger.debug(f"SUM ranges: {ranges}")

        sums = [f"{r}.sum()" for r in ranges]
        logger.debug(f"SUM expressions: {sums}")

        result = " + ".join(sums)
        logger.debug(f"SUM result: {result}")
        return result

    def _translate_sumif(self, node) -> str:
        """Translate SUMIF function."""
        logger.debug(f"Translating SUMIF function: {node}")

        if len(node) < 3 or len(node) > 4:
            error_msg = "SUMIF function requires 2 or 3 arguments"
            logger.error(error_msg)
            raise ValueError(error_msg)

        range_expr = self._translate_node(node[1])
        logger.debug(f"SUMIF range: {range_expr}")

        criteria = self._translate_node(node[2])
        logger.debug(f"SUMIF criteria: {criteria}")

        # If 3 arguments, use the third as sum_range, otherwise use range
        sum_range = self._translate_node(node[3]) if len(node) > 3 else range_expr
        logger.debug(f"SUMIF sum_range: {sum_range}")

        # Similar criteria handling as COUNTIF
        comparison = None
        logger.debug(f"Processing SUMIF criteria: {criteria}")

        if criteria.startswith('"') and criteria.endswith('"'):
            criteria_str = criteria.strip('"')
            logger.debug(f"SUMIF string criteria: {criteria_str}")

            if criteria_str.startswith(('=', '>', '<', '>=', '<=', '<>')):
                operator = criteria_str[0]
                if criteria_str.startswith(('>=', '<=', '<>')):
                    operator = criteria_str[:2]
                    value = criteria_str[2:]
                else:
                    value = criteria_str[1:]

                logger.debug(f"SUMIF operator: {operator}, value: {value}")

                if operator == '=':
                    comparison = f"{range_expr} == {value}"
                elif operator == '<>':
                    comparison = f"{range_expr} != {value}"
                else:
                    comparison = f"{range_expr} {operator} {value}"

                logger.debug(f"SUMIF comparison: {comparison}")
            else:
                comparison = f"{range_expr} == {criteria}"
                logger.debug(f"SUMIF exact match: {comparison}")
        else:
            comparison = f"{range_expr} == {criteria}"
            logger.debug(f"SUMIF numeric/field match: {comparison}")

        # Sum values where condition is True
        result = f"({sum_range}[{comparison}]).sum()"
        logger.debug(f"SUMIF result: {result}")
        return result

    def _translate_average(self, node) -> str:
        """Translate AVERAGE function."""
        logger.debug(f"Translating AVERAGE function: {node}")

        if len(node) < 2:
            error_msg = "AVERAGE function requires at least 1 argument"
            logger.error(error_msg)
            raise ValueError(error_msg)

        ranges = [self._translate_node(arg) for arg in node[1:]]
        logger.debug(f"AVERAGE ranges: {ranges}")

        # Concatenate Series for multi-range average
        if len(ranges) == 1:
            result = f"{ranges[0]}.mean()"
            logger.debug(f"AVERAGE single range result: {result}")
            return result
        else:
            result = f"pd.concat([{', '.join(ranges)}]).mean()"
            logger.debug(f"AVERAGE multi-range result: {result}")
            return result

    def _translate_min(self, node) -> str:
        """Translate MIN function."""
        logger.debug(f"Translating MIN function: {node}")

        if len(node) < 2:
            error_msg = "MIN function requires at least 1 argument"
            logger.error(error_msg)
            raise ValueError(error_msg)

        ranges = [self._translate_node(arg) for arg in node[1:]]
        logger.debug(f"MIN ranges: {ranges}")

        if len(ranges) == 1:
            result = f"{ranges[0]}.min()"
            logger.debug(f"MIN single range result: {result}")
            return result
        else:
            result = f"pd.concat([{', '.join(ranges)}]).min()"
            logger.debug(f"MIN multi-range result: {result}")
            return result

    def _translate_max(self, node) -> str:
        """Translate MAX function."""
        logger.debug(f"Translating MAX function: {node}")

        if len(node) < 2:
            error_msg = "MAX function requires at least 1 argument"
            logger.error(error_msg)
            raise ValueError(error_msg)

        ranges = [self._translate_node(arg) for arg in node[1:]]
        logger.debug(f"MAX ranges: {ranges}")

        if len(ranges) == 1:
            result = f"{ranges[0]}.max()"
            logger.debug(f"MAX single range result: {result}")
            return result
        else:
            result = f"pd.concat([{', '.join(ranges)}]).max()"
            logger.debug(f"MAX multi-range result: {result}")
            return result

    def _translate_left(self, node) -> str:
        """Translate LEFT function."""
        logger.debug(f"Translating LEFT function: {node}")

        if len(node) < 2 or len(node) > 3:
            error_msg = "LEFT function requires 1 or 2 arguments"
            logger.error(error_msg)
            raise ValueError(error_msg)

        text = self._translate_node(node[1])
        logger.debug(f"LEFT text: {text}")

        num_chars = self._translate_node(node[2]) if len(node) > 2 else "1"
        logger.debug(f"LEFT num_chars: {num_chars}")

        result = f"({text}.astype(str).str[:int({num_chars})])"
        logger.debug(f"LEFT result: {result}")
        return result

    def _translate_right(self, node) -> str:
        """Translate RIGHT function."""
        logger.debug(f"Translating RIGHT function: {node}")

        if len(node) < 2 or len(node) > 3:
            error_msg = "RIGHT function requires 1 or 2 arguments"
            logger.error(error_msg)
            raise ValueError(error_msg)

        text = self._translate_node(node[1])
        logger.debug(f"RIGHT text: {text}")

        num_chars = self._translate_node(node[2]) if len(node) > 2 else "1"
        logger.debug(f"RIGHT num_chars: {num_chars}")

        result = f"({text}.astype(str).str[-int({num_chars}):])"
        logger.debug(f"RIGHT result: {result}")
        return result

    def _translate_mid(self, node) -> str:
        """Translate MID function."""
        logger.debug(f"Translating MID function: {node}")

        if len(node) != 4:
            error_msg = "MID function requires exactly 3 arguments"
            logger.error(error_msg)
            raise ValueError(error_msg)

        text = self._translate_node(node[1])
        logger.debug(f"MID text: {text}")

        start_pos = self._translate_node(node[2])
        logger.debug(f"MID start_pos: {start_pos}")

        num_chars = self._translate_node(node[3])
        logger.debug(f"MID num_chars: {num_chars}")

        # Adjust for 1-based indexing in Excel
        adjusted_start = f"(int({start_pos}) - 1)"
        logger.debug(f"MID adjusted_start: {adjusted_start}")

        result = f"({text}.astype(str).str[{adjusted_start}:({adjusted_start} + int({num_chars}))])"
        logger.debug(f"MID result: {result}")
        return result

    def _translate_len(self, node) -> str:
        """Translate LEN function."""
        logger.debug(f"Translating LEN function: {node}")

        if len(node) != 2:
            error_msg = "LEN function requires exactly 1 argument"
            logger.error(error_msg)
            raise ValueError(error_msg)

        text = self._translate_node(node[1])
        logger.debug(f"LEN text: {text}")

        result = f"({text}.astype(str).str.len())"
        logger.debug(f"LEN result: {result}")
        return result

    def _translate_concatenate(self, node) -> str:
        """Translate CONCATENATE function."""
        logger.debug(f"Translating CONCATENATE function: {node}")

        if len(node) < 2:
            error_msg = "CONCATENATE function requires at least 1 argument"
            logger.error(error_msg)
            raise ValueError(error_msg)

        texts = [self._translate_node(arg) for arg in node[1:]]
        logger.debug(f"CONCATENATE texts: {texts}")

        # Convert all arguments to strings and concatenate
        texts = [f"({text}).astype(str)" for text in texts]
        logger.debug(f"CONCATENATE converted texts: {texts}")

        result = " + ".join(texts)
        logger.debug(f"CONCATENATE result: {result}")
        return result

    def _translate_today(self, node) -> str:
        """Translate TODAY function."""
        logger.debug(f"Translating TODAY function: {node}")
        result = "pd.Timestamp.today().normalize()"
        logger.debug(f"TODAY result: {result}")
        return result

    def _translate_now(self, node) -> str:
        """Translate NOW function."""
        logger.debug(f"Translating NOW function: {node}")
        result = "pd.Timestamp.now()"
        logger.debug(f"NOW result: {result}")
        return result