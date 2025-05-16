# xlcalculator_info.py
import sys
import importlib
import inspect

# Try to import xlcalculator
try:
    import xlcalculator

    print(f"xlcalculator module found at: {xlcalculator.__file__}")

    # Check if version is available in a different attribute
    for attr in dir(xlcalculator):
        if 'version' in attr.lower():
            print(f"Possible version attribute: {attr} = {getattr(xlcalculator, attr)}")

    # Inspect ModelCompiler
    from xlcalculator import ModelCompiler

    print("\nModelCompiler available methods:")
    methods = [method for method in dir(ModelCompiler) if not method.startswith('_')]
    for method in methods:
        print(f" - {method}")

    # Try to create a ModelCompiler instance and inspect it
    print("\nModelCompiler instance methods:")
    compiler = ModelCompiler()
    instance_methods = [method for method in dir(compiler) if not method.startswith('_')]
    for method in instance_methods:
        print(f" - {method}")
        # Get method signature if possible
        try:
            method_obj = getattr(compiler, method)
            if callable(method_obj):
                sig = inspect.signature(method_obj)
                print(f"   Signature: {method}({', '.join(str(p) for p in sig.parameters.values())})")
        except Exception as e:
            print(f"   Error getting signature: {e}")

    # Check for Model class
    from xlcalculator import Model

    print("\nModel class available methods:")
    model_methods = [method for method in dir(Model) if not method.startswith('_')]
    for method in model_methods:
        print(f" - {method}")

    # Create instance
    model = Model()
    print("\nModel instance attributes:")
    for attr in dir(model):
        if not attr.startswith('_'):
            try:
                val = getattr(model, attr)
                if not callable(val):
                    print(f" - {attr}: {type(val)}")
                else:
                    print(f" - {attr}: <method>")
            except Exception as e:
                print(f" - {attr}: Error: {e}")

except ImportError as e:
    print(f"Error importing xlcalculator: {e}")
except Exception as e:
    print(f"Error inspecting xlcalculator: {e}")