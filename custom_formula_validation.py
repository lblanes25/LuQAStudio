"""
Custom Formula Validation Module Documentation

This module provides functions for validating and testing Excel-style formulas
in the QA Analytics Framework, using the integrated Excel Formula Converter.
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Optional, Any, Tuple, Set, Union

# Configure logging
logger = logging.getLogger("qa_analytics")

# Try to import the formula converters - prioritize the new integrated converter
try:
    from excel_formula_converter_integration import parse_excel_formula, test_excel_formula
    HAS_CONVERTER = True
except ImportError:
    # Fall back to legacy parser if needed
    try:
        from excel_formula_parser import ExcelFormulaParser
        HAS_LEGACY_PARSER = True
    except ImportError:
        HAS_LEGACY_PARSER = False
        logger.warning("No formula parser available - formula validation disabled")
    HAS_CONVERTER = False


def validate_formula(formula: str, df_columns: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Validate an Excel-style formula without evaluating it.
    
    This function checks if the formula can be parsed correctly and
    identifies which DataFrame columns are referenced.
    
    Args:
        formula: Excel-style formula to validate
        df_columns: Optional list of DataFrame column names to check against
        
    Returns:
        Dictionary with validation results:
        - is_valid: Whether the formula is syntactically valid
        - error: Error message if not valid
        - parsed_formula: The formula translated to pandas expression
        - fields_used: List of field names referenced in the formula
        - missing_fields: List of fields referenced but not in df_columns
    """
    result = {
        'is_valid': False,
        'error': None,
        'parsed_formula': None,
        'fields_used': [],
        'missing_fields': []
    }
    
    if not formula:
        result['error'] = "Empty formula"
        return result
    
    try:
        # Parse the formula using the best available parser
        if HAS_CONVERTER:
            parsed_formula, fields_used = parse_excel_formula(formula, df_columns)
        elif HAS_LEGACY_PARSER:
            parser = ExcelFormulaParser()
            parsed_formula, fields_used = parser.parse(formula)
        else:
            result['error'] = "No formula parser available"
            return result
        
        # Update result with parsing information
        result['is_valid'] = True
        result['parsed_formula'] = parsed_formula
        result['fields_used'] = fields_used
        
        # Check if all referenced fields exist in the DataFrame columns
        if df_columns:
            missing = [field for field in fields_used if field not in df_columns]
            if missing:
                result['missing_fields'] = missing
                
        return result
        
    except Exception as e:
        # Handle parsing errors
        logger.error(f"Formula validation error: {e}")
        result['error'] = str(e)
        return result


def evaluate_formula(formula: str, data: pd.DataFrame) -> Dict[str, Any]:
    """
    Evaluate an Excel-style formula against a DataFrame.
    
    Args:
        formula: Excel-style formula to evaluate
        data: DataFrame to evaluate against
        
    Returns:
        Dictionary with evaluation results:
        - success: Whether the evaluation succeeded
        - result: Pandas Series with the formula results (if successful)
        - error: Error message (if not successful)
        - is_boolean: Whether the result is boolean type
        - summary: Summary statistics (if boolean result)
    """
    result = {
        'success': False,
        'result': None,
        'error': None,
        'is_boolean': False,
        'summary': {}
    }
    
    if not formula:
        result['error'] = "Empty formula"
        return result
    
    try:
        # Parse and evaluate the formula
        if HAS_CONVERTER:
            # Use the integrated test function
            test_result = test_excel_formula(formula, data)
            
            if test_result.get('success', False):
                # Create a boolean mask representing the formula result
                mask = pd.Series(False, index=data.index)
                if 'passing_count' in test_result and test_result['passing_count'] > 0:
                    # Set True for indices that passed
                    pass_indices = [i for i, ex in enumerate(test_result.get('passing_examples', []))
                                   if i < test_result['passing_count']]
                    mask.iloc[pass_indices] = True
                
                result['success'] = True
                result['result'] = mask
                result['is_boolean'] = True
                
                # Summary statistics
                result['summary'] = {
                    'total_records': test_result.get('total_records', len(data)),
                    'passing_count': test_result.get('passing_count', 0),
                    'failing_count': test_result.get('failing_count', 0),
                    'passing_percentage': test_result.get('passing_percentage', '0.0%')
                }
            else:
                result['error'] = test_result.get('error', "Unknown evaluation error")
                
        elif HAS_LEGACY_PARSER:
            # Use the legacy parser and evaluate directly
            parser = ExcelFormulaParser()
            parsed_formula, _ = parser.parse(formula)
            
            # Safe evaluation
            restricted_globals = {"__builtins__": {}}
            safe_locals = {"df": data, "pd": pd, "np": np}
            
            # Evaluate the formula
            formula_result = eval(parsed_formula, restricted_globals, safe_locals)
            
            # Ensure result is a Series
            if not isinstance(formula_result, pd.Series):
                formula_result = pd.Series(formula_result, index=data.index)
            
            result['success'] = True
            result['result'] = formula_result
            
            # Check if result is boolean
            if formula_result.dtype == bool:
                result['is_boolean'] = True
                
                # Calculate summary statistics
                passing_count = formula_result.sum()
                total_records = len(formula_result)
                failing_count = total_records - passing_count
                passing_pct = (passing_count / total_records * 100) if total_records > 0 else 0
                
                result['summary'] = {
                    'total_records': total_records,
                    'passing_count': int(passing_count),
                    'failing_count': int(failing_count),
                    'passing_percentage': f"{passing_pct:.1f}%"
                }
        else:
            # No parser available
            result['error'] = "No formula parser available"
            
        return result
        
    except Exception as e:
        # Handle evaluation errors
        logger.error(f"Formula evaluation error: {e}")
        result['error'] = str(e)
        return result


def generate_sample_data(fields: List[str], record_count: int = 100) -> pd.DataFrame:
    """
    Generate sample data for testing formulas.
    
    Args:
        fields: List of field names to include
        record_count: Number of records to generate
        
    Returns:
        DataFrame with sample data
    """
    data = {}
    
    # Create random data for each field
    for field in fields:
        field_lower = field.lower()
        
        # Determine field type based on name
        if any(date_term in field_lower for date_term in ["date", "time", "when", "created", "modified"]):
            # Generate dates
            base_date = pd.Timestamp('2025-01-01')
            dates = [base_date + pd.Timedelta(days=i) for i in range(record_count)]
            data[field] = dates
            
        elif any(num_term in field_lower for num_term in ["amount", "value", "score", "count", "rating", "num", "qty"]):
            # Generate numeric values
            data[field] = np.random.uniform(1, 200, record_count).round(2)
            
        elif any(bool_term in field_lower for bool_term in ["flag", "is", "has", "complete", "active"]):
            # Generate boolean or status values
            if "status" in field_lower:
                statuses = ["Active", "Inactive", "Pending", "Completed"]
                data[field] = np.random.choice(statuses, record_count)
            else:
                data[field] = np.random.choice([True, False], record_count)
            
        elif any(risk_term in field_lower for risk_term in ["risk", "severity", "priority"]):
            # Generate risk levels
            levels = ["Critical", "High", "Medium", "Low", "N/A"]
            data[field] = np.random.choice(levels, record_count)
            
        elif any(person_term in field_lower for person_term in ["submitter", "approver", "reviewer", "user", "name"]):
            # Generate person names
            names = ["John Smith", "Emma Johnson", "Michael Brown", "Sarah Davis", 
                     "David Wilson", "Jennifer Miller", "Robert Taylor", "Jessica Anderson", 
                     "William Thomas", "Lisa Jackson"]
            data[field] = np.random.choice(names, record_count)
            
        elif "third party" in field_lower or "vendor" in field_lower:
            # Generate third party data
            vendors = ["", "", "Vendor A", "Vendor B", "Vendor C", 
                      "Vendor A, Vendor B", "Vendor C, Vendor D", "Vendor E"]
            data[field] = np.random.choice(vendors, record_count)
            
        else:
            # Default to text field with generic values
            items = [f"Item {i}" for i in range(1, 11)]
            data[field] = np.random.choice(items, record_count)
    
    # Create DataFrame
    return pd.DataFrame(data)


def create_test_scenarios(formula: str, fields_used: List[str]) -> List[Dict[str, Any]]:
    """
    Create test scenarios for formula validation.
    
    This function generates test cases that exercise different aspects
    of the formula to help identify potential issues.
    
    Args:
        formula: Excel-style formula to test
        fields_used: List of field names referenced in the formula
        
    Returns:
        List of test scenario dictionaries
    """
    scenarios = []
    
    # Create base test data
    base_data = generate_sample_data(fields_used, 100)
    
    # Create test scenarios
    scenarios.append({
        'name': "Standard Test",
        'description': "Standard test with 100 records",
        'data': base_data,
        'expected_outcome': "mix"  # Should have both passing and failing records
    })
    
    # Create a small test case
    small_data = generate_sample_data(fields_used, 10)
    scenarios.append({
        'name': "Small Dataset",
        'description': "Small test with 10 records",
        'data': small_data,
        'expected_outcome': "mix"
    })
    
    # Create edge cases for each field
    for field in fields_used:
        # Create null values test
        null_test = base_data.copy()
        null_test.loc[0:9, field] = np.nan
        
        scenarios.append({
            'name': f"Null {field}",
            'description': f"Test with null values in {field}",
            'data': null_test,
            'expected_outcome': "depends"  # Depends on formula
        })
        
        # Create extreme values test if field is numeric
        if pd.api.types.is_numeric_dtype(base_data[field]):
            extreme_test = base_data.copy()
            extreme_test.loc[0:4, field] = 9999999.99  # Very large values
            extreme_test.loc[5:9, field] = 0.0001      # Very small values
            
            scenarios.append({
                'name': f"Extreme {field}",
                'description': f"Test with extreme values in {field}",
                'data': extreme_test,
                'expected_outcome': "depends"
            })
    
    return scenarios


def run_test_scenarios(formula: str, scenarios: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Run test scenarios for a formula.
    
    Args:
        formula: Excel-style formula to test
        scenarios: List of test scenario dictionaries
        
    Returns:
        Dictionary with test results
    """
    results = {
        'formula': formula,
        'scenario_results': [],
        'summary': {
            'total_scenarios': len(scenarios),
            'passed': 0,
            'failed': 0,
            'errors': 0
        }
    }
    
    for scenario in scenarios:
        # Run the scenario
        scenario_result = {
            'name': scenario['name'],
            'description': scenario['description'],
            'success': False,
            'error': None,
            'evaluation': None
        }
        
        try:
            # Evaluate the formula against the scenario data
            eval_result = evaluate_formula(formula, scenario['data'])
            
            if eval_result['success']:
                scenario_result['success'] = True
                scenario_result['evaluation'] = eval_result
                results['summary']['passed'] += 1
            else:
                scenario_result['error'] = eval_result['error']
                results['summary']['failed'] += 1
                
        except Exception as e:
            scenario_result['error'] = str(e)
            results['summary']['errors'] += 1
        
        results['scenario_results'].append(scenario_result)
    
    return results


# Simple demonstration usage
if __name__ == "__main__":
    # Example formulas to test
    formulas = [
        "Value > 100 AND Status = \"Active\"",
        "Submitter <> Approver",
        "Submit Date <= TL Date",
        "IF(Risk = \"High\", Value > 150, Value > 50)",
        "NOT ISBLANK(Third Party)"
    ]
    
    print("Formula Validation Examples:")
    print("===========================")
    
    for formula in formulas:
        print(f"\nFormula: {formula}")
        
        # Validate the formula
        validation = validate_formula(formula)
        
        if validation['is_valid']:
            print(f"Parsed: {validation['parsed_formula']}")
            print(f"Fields: {', '.join(validation['fields_used'])}")
        else:
            print(f"Error: {validation['error']}")
