"""
Test script to verify the fixes to the Excel formula converter.

This script tests the converter with various formulas, focusing particularly
on the fixes for handling multiple conditions and multi-word column names.
"""

import pandas as pd
import numpy as np
import logging
from excel_formula_converter import ExcelToPandasConverter

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

def test_formula_converter():
    """Test the Excel formula converter with various formulas."""
    # Create sample DataFrame with test data
    data = {
        "Status": ["Active", "Inactive", "Active", "On Hold"],
        "Value": [120, 80, 200, 50],
        "Risk Level": ["High", "Low", "Medium", "Low"],
        "Start Date": pd.to_datetime(["2023-01-15", "2022-11-10", "2023-03-22", "2023-02-05"]),
        "Multi Word Column": ["Yes", "No", "Yes", "No"]
    }
    df = pd.DataFrame(data)
    
    # Create converter instance
    converter = ExcelToPandasConverter()
    
    # Register DataFrame columns
    converter.column_mapper.register_columns(df.columns)
    
    # List of test formulas to try, especially focusing on the problematic ones
    test_formulas = [
        # Basic formulas
        'IF(Status="Active", "Yes", "No")',
        
        # Problematic AND formula that was failing
        'AND(Status="Active", Value>100)',
        
        # Multi-word column tests
        'AND(Status="Active", `Risk Level`="High")',
        'IF(`Risk Level`="High", "Critical", "Normal")',
        
        # Multiple conditions tests
        'AND(Status="Active", Value>100, `Risk Level`="High")',
        'OR(Status="Inactive", Value<60, `Multi Word Column`="Yes")',
        
        # Nested function tests
        'IF(AND(Status="Active", Value>100), "High Value Active", "Other")',
        'IF(OR(Status="Inactive", Value<60), "Review", "Pass")',
        
        # Complex nested function
        'IF(AND(OR(Status="Active", `Risk Level`="High"), Value>100), "Priority", "Standard")'
    ]
    
    # Test each formula
    for formula in test_formulas:
        print(f"\n{'-'*60}")
        print(f"Testing formula: {formula}")
        
        try:
            # Convert the formula
            pandas_expr, fields = converter.convert(formula, df.columns)
            
            print(f"Pandas expression: {pandas_expr}")
            print(f"Fields used: {fields}")
            
            # Evaluate the expression
            result = eval(pandas_expr, {"__builtins__": {}}, {"df": df, "pd": pd, "np": np})
            
            # Print result
            print("Result type:", type(result))
            print("Result values:", result.values if hasattr(result, 'values') else result)
            print("SUCCESS!")
            
        except Exception as e:
            print(f"ERROR: {str(e)}")
            print("FAILED!")

if __name__ == "__main__":
    test_formula_converter()