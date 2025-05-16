"""
Excel Formula UI for Configuration Wizard

This module provides an enhanced UI component for inputting and testing Excel-style formulas,
allowing users to write validation logic using familiar Excel syntax rather than Python code.
"""

import os
import threading
import tkinter as tk
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Callable
from tkinter import ttk, messagebox, filedialog
from excel_formula_parser import ExcelFormulaParser

# Get logger
logger = logging.getLogger("qa_analytics")


class EnhancedExcelFormulaFrame(ttk.Frame):
    """
    An enhanced UI component for inputting and testing Excel-style formulas.

    This component can be integrated into the Configuration Wizard
    to add support for custom Excel formulas, allowing users to write
    validation logic using familiar Excel syntax.
    """

    def __init__(self, parent, config_manager=None, template_manager=None,
                 on_formula_change: Optional[Callable] = None):
        """
        Initialize the Excel Formula UI component.

        Args:
            parent: Parent tkinter frame
            config_manager: Optional ConfigManager instance
            template_manager: Optional TemplateManager instance
            on_formula_change: Optional callback for formula changes
        """
        super().__init__(parent)
        self.parent = parent
        self.config_manager = config_manager
        self.template_manager = template_manager
        self.on_formula_change = on_formula_change

        # Initialize parser
        self.parser = ExcelFormulaParser()

        # State variables
        self.formula_var = tk.StringVar()
        self.formula_valid = False
        self.formula_error = ""
        self.parsed_formula = ""
        self.fields_used = []
        self.sample_data = None

        # Configure frame to fill parent
        self.pack(fill=tk.BOTH, expand=True)

        # Set up UI components
        self._setup_ui()

        # Set up validation callback
        self.formula_var.trace_add("write", self._on_formula_changed)

    def _setup_ui(self):
        """Set up the UI components for the Excel Formula frame."""
        # Create a scrollable canvas to contain all elements
        canvas_container = ttk.Frame(self)
        canvas_container.pack(fill=tk.BOTH, expand=True)

        # Configure rows and columns to expand
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        # Create canvas and scrollbar
        self.canvas = tk.Canvas(canvas_container)
        scrollbar = ttk.Scrollbar(canvas_container, orient="vertical", command=self.canvas.yview)

        # Configure canvas
        self.canvas.configure(yscrollcommand=scrollbar.set)

        # Pack canvas and scrollbar
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Create a frame inside the canvas for all content
        self.scroll_frame = ttk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")

        # Update canvas window width when canvas is resized
        def update_window_width(event):
            self.canvas.itemconfig(self.canvas_window, width=event.width)
        self.canvas.bind("<Configure>", update_window_width)

        # Main container with padding (inside the scrollable frame)
        main_frame = ttk.Frame(self.scroll_frame, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Configure the main frame to expand
        for i in range(7):
            main_frame.rowconfigure(i, weight=0)
        main_frame.rowconfigure(6, weight=1)  # Make results row expandable
        main_frame.columnconfigure(0, weight=0)
        main_frame.columnconfigure(1, weight=1)  # Make column 1 expandable

        # Title and description
        title_label = ttk.Label(
            main_frame,
            text="Custom Excel Formula",
            font=("Arial", 12, "bold")
        )
        title_label.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 5))

        description_label = ttk.Label(
            main_frame,
            text="Enter your validation logic using familiar Excel syntax. "
                 "Reference field names exactly as they appear in your data.",
            wraplength=500,
            justify=tk.LEFT
        )
        description_label.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        # Formula input
        formula_label = ttk.Label(main_frame, text="Formula:")
        formula_label.grid(row=2, column=0, sticky=tk.W, pady=(0, 5))

        formula_frame = ttk.Frame(main_frame)
        formula_frame.grid(row=2, column=1, sticky=tk.EW, pady=(0, 5))
        formula_frame.columnconfigure(0, weight=1)  # Make formula entry expandable

        self.formula_entry = ttk.Entry(
            formula_frame,
            textvariable=self.formula_var,
            width=60
        )
        self.formula_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Formula examples button
        examples_btn = ttk.Button(
            formula_frame,
            text="Examples ▼",
            command=self._show_examples
        )
        examples_btn.pack(side=tk.LEFT, padx=(5, 0))

        # Parsed formula display
        ttk.Label(main_frame, text="Parsed Formula:").grid(row=3, column=0, sticky=tk.W, pady=(5, 5))

        self.parsed_display = tk.Text(main_frame, height=3, wrap=tk.WORD)
        self.parsed_display.grid(row=3, column=1, sticky=tk.EW, pady=(5, 5))
        self.parsed_display.config(state=tk.DISABLED)

        # Status message
        self.status_var = tk.StringVar(value="Enter a formula")
        self.status_label = ttk.Label(
            main_frame,
            textvariable=self.status_var,
            foreground="gray"
        )
        self.status_label.grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        # Test controls
        test_frame = ttk.LabelFrame(main_frame, text="Test Formula")
        test_frame.grid(row=5, column=0, columnspan=2, sticky=tk.NSEW, pady=(5, 5))
        test_frame.columnconfigure(0, weight=1)  # Make test frame expandable

        # Description for test section
        test_desc = ttk.Label(
            test_frame,
            text="Generate sample data or upload a file to test your formula.",
            wraplength=500,
            justify=tk.LEFT
        )
        test_desc.pack(fill=tk.X, padx=10, pady=(5, 10))

        # Test options
        test_options_frame = ttk.Frame(test_frame)
        test_options_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        # Sample data generation
        self.data_source_var = tk.StringVar(value="generate")
        ttk.Radiobutton(
            test_options_frame,
            text="Generate Sample Data",
            variable=self.data_source_var,
            value="generate",
            command=self._update_data_options
        ).pack(side=tk.LEFT)

        ttk.Radiobutton(
            test_options_frame,
            text="Use Existing Data",
            variable=self.data_source_var,
            value="existing",
            command=self._update_data_options
        ).pack(side=tk.LEFT, padx=(20, 0))

        # Sample data options frame (will show/hide based on selection)
        self.sample_frame = ttk.Frame(test_frame)
        self.sample_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        ttk.Label(self.sample_frame, text="Records:").pack(side=tk.LEFT)

        self.record_count_var = tk.StringVar(value="100")
        ttk.Entry(
            self.sample_frame,
            textvariable=self.record_count_var,
            width=8
        ).pack(side=tk.LEFT, padx=(5, 20))

        ttk.Label(self.sample_frame, text="Error %:").pack(side=tk.LEFT)

        self.error_pct_var = tk.StringVar(value="20")
        ttk.Entry(
            self.sample_frame,
            textvariable=self.error_pct_var,
            width=8
        ).pack(side=tk.LEFT, padx=(5, 0))

        # File selection frame
        self.file_frame = ttk.Frame(test_frame)
        self.file_frame.columnconfigure(1, weight=1)  # Make file entry expandable

        ttk.Label(self.file_frame, text="Data File:").grid(row=0, column=0, sticky=tk.W)

        self.file_var = tk.StringVar()
        ttk.Entry(
            self.file_frame,
            textvariable=self.file_var,
            width=40
        ).grid(row=0, column=1, sticky=tk.EW, padx=5)

        ttk.Button(
            self.file_frame,
            text="Browse...",
            command=self._browse_file
        ).grid(row=0, column=2, padx=5)

        # Update which frame is visible
        self._update_data_options()

        # Test button
        test_btn_frame = ttk.Frame(test_frame)
        test_btn_frame.pack(fill=tk.X, pady=(0, 10))

        self.test_btn = ttk.Button(
            test_btn_frame,
            text="Test Formula",
            command=self._test_formula
        )
        self.test_btn.pack(side=tk.RIGHT, padx=10)

        # Progress indicator
        self.progress = ttk.Progressbar(
            test_btn_frame,
            orient="horizontal",
            length=200,
            mode="indeterminate"
        )
        self.progress.pack(side=tk.RIGHT, padx=(0, 10))

        # Results frame
        self.results_frame = ttk.LabelFrame(main_frame, text="Test Results")
        self.results_frame.grid(row=6, column=0, columnspan=2, sticky=tk.NSEW, pady=(5, 5))
        self.results_frame.columnconfigure(0, weight=1)
        self.results_frame.rowconfigure(0, weight=1)

        # Initially hide results
        self.results_frame.grid_remove()

        # Update scroll region after all widgets are created
        self.scroll_frame.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_formula_changed(self, *args):
        """Handle formula changes and validate in real-time."""
        formula = self.formula_var.get()

        if not formula:
            self._update_status("Enter a formula", "gray")
            self.formula_valid = False
            self._update_parsed_display("")
            return

        try:
            # Parse the formula
            parsed_formula, fields_used = self.parser.parse(formula)

            # Update state
            self.formula_valid = True
            self.parsed_formula = parsed_formula
            self.fields_used = fields_used

            # Update UI
            self._update_status("Formula is valid", "green")
            self._update_parsed_display(parsed_formula)

            # Call callback if provided
            if callable(self.on_formula_change):
                self.on_formula_change(formula, parsed_formula, fields_used)

        except Exception as e:
            # Update state
            self.formula_valid = False
            self.formula_error = str(e)

            # Update UI
            self._update_status(f"Error: {str(e)}", "red")
            self._update_parsed_display("")

    def _update_status(self, message: str, color: str = "black"):
        """Update the status message with the given text and color."""
        self.status_var.set(message)
        self.status_label.config(foreground=color)

    def _update_parsed_display(self, parsed_formula: str):
        """Update the parsed formula display text."""
        self.parsed_display.config(state=tk.NORMAL)
        self.parsed_display.delete(1.0, tk.END)
        if parsed_formula:
            self.parsed_display.insert(tk.END, parsed_formula)
        self.parsed_display.config(state=tk.DISABLED)

    def _show_examples(self):
        """Show a popup with formula examples."""
        examples = [
            ("Segregation of Duties", "Submitter <> Approver"),
            ("Approval Sequence", "`Submit Date` <= `Approval Date`"),
            ("Required Fields", "NOT ISBLANK(FieldName)"),
            ("Value in List", "Risk IN (\"High\", \"Medium\", \"Low\")"),
            ("Date Comparison", "DueDate <= TODAY() + 30"),
            ("Conditional Logic", "IF(RiskLevel=\"High\", DaysOpen<=30, DaysOpen<=90)"),
        ]

        # Create popup window
        popup = tk.Toplevel(self)
        popup.title("Formula Examples")
        popup.geometry("600x400")
        popup.transient(self)  # Set to be on top of the parent window
        popup.grab_set()  # Modal window

        # Create content
        frame = ttk.Frame(popup, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        # Header
        ttk.Label(
            frame,
            text="Excel Formula Examples",
            font=("Arial", 12, "bold")
        ).pack(fill=tk.X, pady=(0, 10))

        # Examples
        for title, formula in examples:
            example_frame = ttk.Frame(frame)
            example_frame.pack(fill=tk.X, pady=(0, 10))
            example_frame.columnconfigure(0, weight=1)  # Make formula area expandable

            ttk.Label(
                example_frame,
                text=title,
                font=("Arial", 10, "bold")
            ).pack(anchor=tk.W)

            formula_frame = ttk.Frame(example_frame)
            formula_frame.pack(fill=tk.X, pady=(2, 0))
            formula_frame.columnconfigure(0, weight=1)  # Make text area expandable

            formula_text = tk.Text(
                formula_frame,
                height=1,
                wrap=tk.NONE,
                font=("Courier", 10)
            )
            formula_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
            formula_text.insert(tk.END, formula)
            formula_text.config(state=tk.DISABLED)

            ttk.Button(
                formula_frame,
                text="Use",
                width=5,
                command=lambda f=formula: self._use_example(f)
            ).pack(side=tk.RIGHT, padx=(5, 0))

        # Close button
        ttk.Button(
            frame,
            text="Close",
            command=popup.destroy
        ).pack(side=tk.RIGHT, pady=(10, 0))

    def _use_example(self, formula: str):
        """Use an example formula."""
        self.formula_var.set(formula)
        popup = self.winfo_toplevel()
        if isinstance(popup, tk.Toplevel):
            popup.destroy()

    def _update_data_options(self):
        """Update test options based on data source selection."""
        source = self.data_source_var.get()

        if source == "generate":
            self.sample_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
            self.file_frame.pack_forget()
        else:
            self.sample_frame.pack_forget()
            self.file_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

    def _browse_file(self):
        """Browse for a data file."""
        filename = filedialog.askopenfilename(
            filetypes=[("Excel Files", "*.xlsx *.xls"), ("CSV Files", "*.csv")],
            title="Select Data File"
        )

        if filename:
            self.file_var.set(filename)

    def _generate_sample_data(self):
        """Generate sample data for testing."""
        try:
            # Parse the parameters
            record_count = int(self.record_count_var.get())
            error_pct = float(self.error_pct_var.get()) / 100.0

            if not self.fields_used:
                messagebox.showerror("Error", "No fields detected in formula")
                return None

            # Generate sample data with the fields from the formula
            data = {}

            # Create random data for each field
            for field in self.fields_used:
                # Determine field type based on name
                if "date" in field.lower():
                    # Generate dates
                    base_date = pd.Timestamp('2025-01-01')
                    dates = [base_date + pd.Timedelta(days=i) for i in range(record_count)]
                    data[field] = dates

                elif any(keyword in field.lower() for keyword in ["amount", "value", "score", "rating"]):
                    # Generate numeric values
                    data[field] = np.random.uniform(1, 100, record_count).round(2)

                elif any(keyword in field.lower() for keyword in ["flag", "status", "complete"]):
                    # Generate boolean or status values
                    statuses = ["Complete", "Incomplete", "In Progress", "Pending"]
                    data[field] = np.random.choice(statuses, record_count)

                else:
                    # Default to text field with names
                    names = ["Alice", "Bob", "Charlie", "David", "Emma",
                             "Frank", "Grace", "Henry", "Isabel", "Jack"]
                    data[field] = np.random.choice(names, record_count)

            # Create DataFrame
            df = pd.DataFrame(data)

            # Return generated data
            return df

        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate sample data: {e}")
            return None

    def _load_data_file(self):
        """Load data from file for testing."""
        file_path = self.file_var.get()

        if not file_path or not os.path.exists(file_path):
            messagebox.showerror("Error", "Please select a valid file")
            return None

        try:
            # Determine file type
            if file_path.lower().endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file_path)
            elif file_path.lower().endswith('.csv'):
                df = pd.read_csv(file_path)
            else:
                messagebox.showerror("Error", "Unsupported file type")
                return None

            return df

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load file: {e}")
            return None

    def _test_formula(self):
        """Test the formula against sample data."""
        if not self.formula_valid:
            messagebox.showerror("Error", "Please enter a valid formula first")
            return

        # Start progress bar
        self.progress.start()
        self.test_btn.config(state=tk.DISABLED)

        # Run test in a separate thread
        threading.Thread(target=self._run_test, daemon=True).start()

    def _run_test(self):
        """Run formula test in a separate thread."""
        try:
            # Get sample data
            if self.data_source_var.get() == "generate":
                self.sample_data = self._generate_sample_data()
            else:
                self.sample_data = self._load_data_file()

            if self.sample_data is None:
                # Stop progress and reset button
                self.after(0, self._reset_test_progress)
                return

            # Test the formula
            formula = self.formula_var.get()

            # Use test_custom_formula or fallback to direct testing
            try:
                from custom_formula_validation import test_custom_formula
                test_result = test_custom_formula(formula, self.sample_data)
            except (ImportError, NameError):
                # Fallback to direct testing if module not available
                test_result = self._direct_formula_test(formula, self.sample_data)

            # Update UI with results
            self.after(0, lambda: self._show_test_results(test_result))

        except Exception as e:
            # Handle errors
            logger.error(f"Formula test error: {e}")
            self.after(0, lambda: messagebox.showerror("Error", f"Test failed: {str(e)}"))

        finally:
            # Reset progress
            self.after(0, self._reset_test_progress)

    def _direct_formula_test(self, formula, data):
        """
        Direct formula testing when custom_formula_validation module is not available.

        This is a simplified version of test_custom_formula.
        """
        try:
            # Parse the formula
            parsed_formula, fields_used = self.parser.parse(formula)

            # Execute the formula against the data
            import pandas as pd
            import numpy as np

            restricted_globals = {"__builtins__": {}}
            safe_locals = {"df": data, "pd": pd, "np": np}

            # Execute the formula
            formula_result = eval(parsed_formula, restricted_globals, safe_locals)

            # Convert result to boolean Series if needed
            if not isinstance(formula_result, pd.Series):
                formula_result = pd.Series(formula_result, index=data.index)

            if formula_result.dtype != bool:
                formula_result = formula_result.astype(bool)

            # Calculate statistics
            total_records = len(data)
            passing_count = formula_result.sum()
            failing_count = total_records - passing_count

            passing_percentage = f"{passing_count / total_records * 100:.1f}%" if total_records > 0 else "0.0%"

            # Get example records
            max_examples = 5
            passing_examples = []
            failing_examples = []

            if passing_count > 0:
                passing_indices = formula_result[formula_result].index[:max_examples]
                for idx in passing_indices:
                    passing_examples.append(data.loc[idx].to_dict())

            if failing_count > 0:
                failing_indices = formula_result[~formula_result].index[:max_examples]
                for idx in failing_indices:
                    failing_examples.append(data.loc[idx].to_dict())

            # Return results
            return {
                'success': True,
                'total_records': total_records,
                'passing_count': passing_count,
                'failing_count': failing_count,
                'passing_percentage': passing_percentage,
                'passing_examples': passing_examples,
                'failing_examples': failing_examples
            }

        except Exception as e:
            logger.error(f"Direct formula test error: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def _reset_test_progress(self):
        """Reset test progress indicators."""
        self.progress.stop()
        self.test_btn.config(state=tk.NORMAL)

    def _show_test_results(self, result: Dict):
        """Show test results in the UI."""
        # Clear previous results
        for widget in self.results_frame.winfo_children():
            widget.destroy()

        # Make sure the results frame is visible
        self.results_frame.grid()

        if not result.get('success', False):
            # Show error
            error_label = ttk.Label(
                self.results_frame,
                text=f"Error: {result.get('error', 'Unknown error')}",
                foreground="red",
                wraplength=500
            )
            error_label.pack(padx=10, pady=10, fill=tk.X)

            # Update UI to show results
            self._update_scroll_region()
            return

        # Create results content
        summary_frame = ttk.Frame(self.results_frame)
        summary_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        # Results summary
        ttk.Label(
            summary_frame,
            text=f"Records tested: {result['total_records']}",
            font=("Arial", 10)
        ).pack(side=tk.LEFT, padx=(0, 20))

        ttk.Label(
            summary_frame,
            text=f"Passing: {result['passing_count']} ({result['passing_percentage']})",
            foreground="green",
            font=("Arial", 10)
        ).pack(side=tk.LEFT, padx=(0, 20))

        ttk.Label(
            summary_frame,
            text=f"Failing: {result['failing_count']}",
            foreground="red" if result['failing_count'] > 0 else "black",
            font=("Arial", 10)
        ).pack(side=tk.LEFT)

        # Create notebook for example tabs
        examples_notebook = ttk.Notebook(self.results_frame)
        examples_notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))

        # Passing examples tab
        passing_tab = ttk.Frame(examples_notebook)
        examples_notebook.add(passing_tab, text="Passing Examples")
        passing_tab.columnconfigure(0, weight=1)
        passing_tab.rowconfigure(0, weight=1)

        # Failing examples tab
        failing_tab = ttk.Frame(examples_notebook)
        examples_notebook.add(failing_tab, text="Failing Examples")
        failing_tab.columnconfigure(0, weight=1)
        failing_tab.rowconfigure(0, weight=1)

        # Add examples to tabs
        self._add_examples_to_tab(passing_tab, result.get('passing_examples', []))
        self._add_examples_to_tab(failing_tab, result.get('failing_examples', []))

        # Select tab based on results
        if result.get('failing_count', 0) > 0:
            examples_notebook.select(1)  # Select failing tab

        # Update UI to show results
        self._update_scroll_region()

    def _update_scroll_region(self):
        """Update the scroll region to ensure all content is visible"""
        # Allow all widgets to update their sizes
        self.scroll_frame.update_idletasks()

        # Update the scroll region to encompass all content
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

        # Get width of the canvas
        canvas_width = self.canvas.winfo_width()

        # Configure the window width to match canvas width
        self.canvas.itemconfig(self.canvas_window, width=canvas_width)

        # Scroll to show the test results
        self.canvas.yview_moveto(0.7)  # Scroll down to show results, but not all the way

    def _add_examples_to_tab(self, tab, examples):
        """Add example records to a tab."""
        if not examples:
            ttk.Label(
                tab,
                text="No examples to display",
                font=("Arial", 10, "italic")
            ).pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
            return

        # Create frame for treeview and scrollbar
        tree_frame = ttk.Frame(tab)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        # Create treeview for examples
        columns = list(examples[0].keys())
        tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
        tree.grid(row=0, column=0, sticky=tk.NSEW)

        # Configure columns
        col_width = max(80, int(600 / max(len(columns), 1)))  # Distribute width evenly
        for col in columns:
            tree.column(col, width=col_width)
            tree.heading(col, text=col)

        # Add scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        vsb.grid(row=0, column=1, sticky=tk.NS)
        tree.configure(yscrollcommand=vsb.set)

        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree.xview)
        hsb.grid(row=1, column=0, sticky=tk.EW)
        tree.configure(xscrollcommand=hsb.set)

        # Add examples to tree
        for example in examples:
            values = [str(example.get(col, "")) for col in columns]
            tree.insert("", tk.END, values=values)

    def get_formula_data(self) -> Dict:
        """
        Get the current formula data.

        Returns:
            Dictionary with formula information
        """
        return {
            'original_formula': self.formula_var.get(),
            'parsed_formula': self.parsed_formula,
            'fields_used': self.fields_used,
            'is_valid': self.formula_valid
        }

    def set_formula(self, formula: str):
        """
        Set the formula in the UI.

        Args:
            formula: Excel-style formula
        """
        self.formula_var.set(formula)


# Backwards compatibility alias
ExcelFormulaFrame = EnhancedExcelFormulaFrame


# Main function for standalone testing
if __name__ == "__main__":
    import logging

    # Configure logging for standalone mode
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Create root window
    root = tk.Tk()
    root.title("Excel Formula UI Test")
    root.geometry("800x800")

    # Create frame
    frame = ttk.Frame(root, padding=10)
    frame.pack(fill=tk.BOTH, expand=True)

    # Create Excel Formula UI
    formula_ui = EnhancedExcelFormulaFrame(frame)
    formula_ui.pack(fill=tk.BOTH, expand=True)

    # Set example formula
    formula_ui.set_formula("Submitter <> Approver AND `Submit Date` <= `TL Date`")

    # Start main loop
    root.mainloop()