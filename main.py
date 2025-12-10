# main.py - Simplified and restructured
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import queue
import json
import traceback
from datetime import datetime
import numpy as np
import pickle
from collections import OrderedDict
from lxml import etree as xml
import matplotlib
matplotlib.use('TkAgg')
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import inspect # Use to get parameterized transformations

import process_model

class SyntaxHighlightingText(scrolledtext.ScrolledText):
    """Text widget with basic Python syntax highlighting"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tag_config('keyword', foreground='blue', font=('Consolas', 10, 'bold'))
        self.tag_config('string', foreground='green', font=('Consolas', 10))
        self.tag_config('comment', foreground='gray', font=('Consolas', 10, 'italic'))
        self.tag_config('number', foreground='purple', font=('Consolas', 10))
        self.tag_config('builtin', foreground='darkorange', font=('Consolas', 10))
        self.bind('<KeyRelease>', self._highlight)
    
    def _highlight(self, event=None):
        """Apply basic syntax highlighting"""
        for tag in ['keyword', 'string', 'comment', 'number', 'builtin']:
            self.tag_remove(tag, '1.0', tk.END)
        
        text = self.get('1.0', tk.END)
        lines = text.split('\n')
        line_num = 1
        
        for line in lines:
            # Comments
            if '#' in line:
                start = line.find('#')
                self.tag_add('comment', f'{line_num}.{start}', f'{line_num}.{len(line)}')
            
            # Strings
            for quote in ['"', "'"]:
                start = 0
                while True:
                    start = line.find(quote, start)
                    if start == -1: break
                    end = line.find(quote, start + 1)
                    if end == -1: break
                    self.tag_add('string', f'{line_num}.{start}', f'{line_num}.{end+1}')
                    start = end + 1
            line_num += 1

class UPPAALExperimentRunner:

    def __init__(self, root):
        self.root = root
        self.root.title("UPPAAL Experiment Runner")
        
        # Data storage
        self.model_file = None
        self.queries_file = None
        self.results = None
        self.experiment_thread = None
        self.stop_event = threading.Event()
        self.progress_queue = queue.Queue()
        
        # Variables
        self.variables = OrderedDict()
        self.declarations = {}
        self.user_variables = OrderedDict()
        self.default_variables = OrderedDict()
        
        # Plotting data
        self.raw_data = {}
        self.transformed_data = {}
        self.transformations = {}
        self.plot_configs = OrderedDict()
        
        # Settings
        self.seed_value = tk.StringVar(value="0")
        self.num_threads = tk.IntVar(value=1)
        
        # Setup UI
        self.setup_styles()
        self.create_widgets()
        self.check_progress()
        self.initialize_default_plot_config()
    
    def setup_styles(self):
        """Configure ttk styles"""
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Title.TLabel', font=('Segoe UI', 12, 'bold'))
        style.configure('Header.TLabel', font=('Segoe UI', 10, 'bold'))
    
    def initialize_default_plot_config(self):
        """Initialize default plot configuration"""
        self.plot_configs["default"] = {
            'data_source': 'raw',
            'plot_type': 'scatter',
            'series': [],
            'title': 'Plot',
            'x_label': 'X',
            'y_label': 'Y',
            'include_seed': False
        }
    
    # ==================== UI CREATION ====================
    
    def create_widgets(self):
        """Create the main tabbed interface"""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create tabs
        self.tabs = {}
        for name in ["Model", "Experiments", "Declarations", "Transform", "Plot"]:
            self.tabs[name] = ttk.Frame(self.notebook)
            self.notebook.add(self.tabs[name], text=name)
        
        # Setup each tab
        self.setup_model_tab()
        self.setup_experiments_tab()
        self.setup_declarations_tab()
        self.setup_transform_tab()
        self.setup_plot_tab()
        
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

    def on_tab_changed(self, _):
        """Handle tab change event"""
        current_tab = self.notebook.tab(self.notebook.select(), "text")
        if current_tab == "Transform":
            if hasattr(self, 'transform_code') and isinstance(self.transform_code, SyntaxHighlightingText):
                self.transform_code._highlight()
        elif current_tab == "Plot":
            self.auto_config_change()
    
    # ==================== MODEL TAB ====================
    
    def setup_model_tab(self):
        """Setup Model tab"""
        tab = self.tabs["Model"]
        main_container = ttk.Frame(tab, padding=10)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Left panel for file selection
        left_panel = ttk.LabelFrame(main_container, text="Model Configuration", padding=10)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        # Model file selection
        ttk.Label(left_panel, text="UPPAAL Model File (.xml):", style='Header.TLabel').pack(anchor=tk.W, pady=(0, 5))
        model_frame = ttk.Frame(left_panel)
        model_frame.pack(fill=tk.X, pady=(0, 10))
        self.model_entry = ttk.Entry(model_frame, width=50)
        self.model_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(model_frame, text="Browse...", command=self.select_model).pack(side=tk.LEFT)
        
        # Queries file selection
        ttk.Label(left_panel, text="Queries File (.q):", style='Header.TLabel').pack(anchor=tk.W, pady=(0, 5))
        queries_frame = ttk.Frame(left_panel)
        queries_frame.pack(fill=tk.X, pady=(0, 10))
        self.queries_entry = ttk.Entry(queries_frame, width=50)
        self.queries_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(queries_frame, text="Browse...", command=self.select_queries).pack(side=tk.LEFT)
        
        # Data import/export
        data_frame = ttk.Frame(left_panel)
        data_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(data_frame, text="Import Experiment", command=self.load_experiment_config, width=20).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(data_frame, text="Export Experiment", command=self.save_experiment_config, width=20).pack(side=tk.LEFT)
        
        # Seed configuration
        seed_frame = ttk.LabelFrame(left_panel, text="Random Seed", padding=10)
        seed_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(seed_frame, text="Seed value (0 = random):").pack(side=tk.LEFT)
        ttk.Entry(seed_frame, textvariable=self.seed_value, width=15).pack(side=tk.LEFT, padx=5)
        
        # Right panel for variables
        right_panel = ttk.LabelFrame(main_container, text="Model Variables", padding=10)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # Variables header with refresh button
        header_frame = ttk.Frame(right_panel)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header_frame, text="Variables from Declarations:", style='Header.TLabel').pack(side=tk.LEFT)
        ttk.Button(header_frame, text="Refresh", width=10, command=self.refresh_variables).pack(side=tk.RIGHT)
        
        # Variables treeview
        tree_frame = ttk.Frame(right_panel)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        self.var_tree = ttk.Treeview(tree_frame, columns=('name', 'value'), show='headings', height=12)
        self.var_tree.heading('name', text='Variable')
        self.var_tree.heading('value', text='Value')
        self.var_tree.column('name', width=250, anchor=tk.W)
        self.var_tree.column('value', width=150, anchor=tk.W)
        
        v_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.var_tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.var_tree.xview)
        self.var_tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        self.var_tree.grid(row=0, column=0, sticky='nsew')
        v_scrollbar.grid(row=0, column=1, sticky='ns')
        h_scrollbar.grid(row=1, column=0, sticky='ew', columnspan=2)
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        self.var_tree.bind('<Double-1>', self.on_variable_double_click)
        ttk.Label(right_panel, text="Double-click a variable to edit its value", font=('Segoe UI', 8)).pack(pady=(10, 0))
    
    # ==================== EXPERIMENTS TAB ====================
    
    def setup_experiments_tab(self):
        """Setup Experiments tab"""
        tab = self.tabs["Experiments"]
        main_container = ttk.Frame(tab, padding=10)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Control panel
        control_frame = ttk.LabelFrame(main_container, text="Experiment Controls", padding=10)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        thread_frame = ttk.Frame(control_frame)
        thread_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(thread_frame, text="Parallel Threads:").pack(side=tk.LEFT)
        ttk.Spinbox(thread_frame, from_=1, to=8, textvariable=self.num_threads, width=10).pack(side=tk.LEFT, padx=5)
        
        # Action buttons
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(fill=tk.X)
        self.start_btn = ttk.Button(button_frame, text="▶ Start Experiments", command=self.start_experiment)
        self.start_btn.pack(side=tk.LEFT, padx=2)
        self.stop_btn = ttk.Button(button_frame, text="■ Stop", command=self.stop_experiment, state='disabled')
        self.stop_btn.pack(side=tk.LEFT, padx=2)
        self.clear_btn = ttk.Button(button_frame, text="Clear Results", command=self.clear_results)
        self.clear_btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Export Data", command=self.export_experiment_data).pack(side=tk.LEFT, padx=2)
        
        # Progress panel
        progress_frame = ttk.LabelFrame(main_container, text="Progress", padding=10)
        progress_frame.pack(fill=tk.X, pady=(0, 10))
        self.progress_bar = ttk.Progressbar(progress_frame, mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))
        self.status_label = ttk.Label(progress_frame, text="Ready to start experiments")
        self.status_label.pack(anchor=tk.W)
        
        # Results panel
        results_frame = ttk.LabelFrame(main_container, text="Results", padding=10)
        results_frame.pack(fill=tk.BOTH, expand=True)
        self.results_text = scrolledtext.ScrolledText(results_frame, height=20, font=('Consolas', 9))
        self.results_text.pack(fill=tk.BOTH, expand=True)
        
        result_buttons = ttk.Frame(results_frame)
        result_buttons.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(result_buttons, text="View Raw Data", command=self.view_raw_data).pack(side=tk.LEFT, padx=2)
        ttk.Button(result_buttons, text="Copy Results", command=self.copy_results).pack(side=tk.LEFT, padx=2)
    
    # ==================== DECLARATIONS TAB ====================
    
    def setup_declarations_tab(self):
        """Setup Declarations tab"""
        tab = self.tabs["Declarations"]
        main_container = ttk.Frame(tab, padding=10)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Controls
        control_frame = ttk.LabelFrame(main_container, text="Declarations Editor", padding=10)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        select_frame = ttk.Frame(control_frame)
        select_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(select_frame, text="Select Declaration:").pack(side=tk.LEFT)
        self.declaration_var = tk.StringVar()
        self.declaration_combo = ttk.Combobox(select_frame, textvariable=self.declaration_var, state='readonly', width=40)
        self.declaration_combo.pack(side=tk.LEFT, padx=5)
        self.declaration_combo.bind('<<ComboboxSelected>>', self.on_declaration_selected)
        ttk.Button(select_frame, text="Load Declarations", command=self.load_declarations).pack(side=tk.LEFT, padx=5)
        ttk.Button(select_frame, text="Apply Changes", command=self.save_declaration).pack(side=tk.LEFT, padx=5)
        
        # Editor
        editor_frame = ttk.LabelFrame(main_container, text="Declaration Code", padding=10)
        editor_frame.pack(fill=tk.BOTH, expand=True)
        text_frame = ttk.Frame(editor_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)
        
        # Declaration editor
        self.declaration_editor = scrolledtext.ScrolledText(text_frame, height=20, font=('Consolas', 10))
        self.declaration_editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    
    # ==================== TRANSFORM TAB ====================
    
    def setup_transform_tab(self):
        """Setup Transformation tab"""
        tab = self.tabs["Transform"]
        main_container = ttk.Frame(tab, padding=10)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Split into left (list) and right (editor)
        paned = ttk.PanedWindow(main_container, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)
        
        # Left panel - Transformations list
        left_panel = ttk.LabelFrame(paned, text="Transformations", padding=10)
        paned.add(left_panel, weight=1)
        
        list_frame = ttk.Frame(left_panel)
        list_frame.pack(fill=tk.BOTH, expand=True)
        self.transform_listbox = tk.Listbox(list_frame, height=15, font=('Segoe UI', 10), selectbackground='#007acc', selectforeground='white')
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.transform_listbox.yview)
        self.transform_listbox.configure(yscrollcommand=scrollbar.set)
        self.transform_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.transform_listbox.bind('<<ListboxSelect>>', self.on_transform_list_select)
        
        # Transformation controls
        control_frame = ttk.Frame(left_panel)
        control_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(control_frame, text="New", command=self.new_transformation).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="Save", command=self.save_transformation).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="Remove", command=self.remove_transformation).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="Execute", command=self.execute_current_transformation).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="Run All", command=self.run_all_transformations).pack(side=tk.LEFT, padx=2)
        ttk.Button(control_frame, text="View Result", command=self.view_transform_result).pack(side=tk.LEFT, padx=2)
        
        # Right panel - Editor
        right_panel = ttk.LabelFrame(paned, text="Transformation Editor", padding=10)
        paned.add(right_panel, weight=2)
        
        # Transformation name and type
        name_frame = ttk.Frame(right_panel)
        name_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(name_frame, text="Name:").pack(side=tk.LEFT)
        self.transform_name_var = tk.StringVar(value="new_transformation")
        self.transform_name_entry = ttk.Entry(name_frame, textvariable=self.transform_name_var, width=30)
        self.transform_name_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Code editor with syntax highlighting
        editor_frame = ttk.LabelFrame(right_panel, text="Python Code", padding=10)
        editor_frame.pack(fill=tk.BOTH, expand=True)
        self.transform_code = SyntaxHighlightingText(editor_frame, height=20, font=('Consolas', 10))
        self.transform_code.pack(fill=tk.BOTH, expand=True)
        
        # Documentation
        doc_frame = ttk.LabelFrame(right_panel, text="Transformation Format", padding=10)
        doc_frame.pack(fill=tk.X, pady=(10, 0))
        doc_text = """Transformations set the variable result to a dict on the form:
• {'series_name': {'x': [1,2,3], 'y': [4,5,6], 'label': 'Series 1'}}"""
        ttk.Label(doc_frame, text=doc_text, justify=tk.LEFT, font=('Segoe UI', 9), foreground='gray').pack(fill=tk.X)
        
        # Status bar
        self.transform_status = ttk.Label(right_panel, text="Ready", relief=tk.SUNKEN, anchor=tk.W)
        self.transform_status.pack(fill=tk.X, pady=(10, 0))
    
    # ==================== PLOT TAB ====================
    
    def setup_plot_tab(self):
        """Setup Plot tab"""
        tab = self.tabs["Plot"]
        main_container = ttk.Frame(tab, padding=10)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Split into left (controls) and right (plot)
        paned = ttk.PanedWindow(main_container, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)
        
        # Left panel - Controls
        left_panel = ttk.Frame(paned)
        paned.add(left_panel, weight=1)
        
        # Plot configuration
        config_frame = ttk.LabelFrame(left_panel, text="Plot Configuration", padding=10)
        config_frame.pack(fill=tk.X, pady=(0, 10))
        
        config_select_frame = ttk.Frame(config_frame)
        config_select_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(config_select_frame, text="Configuration:").pack(side=tk.LEFT)
        self.plot_config_var = tk.StringVar(value="default")
        self.plot_config_combo = ttk.Combobox(config_select_frame, textvariable=self.plot_config_var, state='readonly', width=20)
        self.plot_config_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.plot_config_combo.bind('<<ComboboxSelected>>', self.on_plot_config_selected)
        ttk.Button(config_select_frame, text="New", command=self.create_plot_config).pack(side=tk.LEFT, padx=2)
        ttk.Button(config_select_frame, text="Delete", command=self.delete_plot_config).pack(side=tk.LEFT, padx=2)
        ttk.Button(config_select_frame, text="Rename", command=self.rename_plot_config).pack(side=tk.LEFT, padx=2)
        
        # Plot title
        title_frame = ttk.LabelFrame(config_frame, text="Plot Title", padding=10)
        title_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(title_frame, text="Title:").pack(anchor=tk.W)
        self.plot_title_var = tk.StringVar(value="Plot")
        ttk.Entry(title_frame, textvariable=self.plot_title_var, width=40).pack(fill=tk.X, pady=(2, 5))
        self.include_seed_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(title_frame, text="Include seed in title", variable=self.include_seed_var, command=self.auto_config_change).pack(anchor=tk.W)
        
        # Axis labels
        labels_frame = ttk.LabelFrame(config_frame, text="Axis Labels", padding=10)
        labels_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(labels_frame, text="X-axis Label:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.x_label_var = tk.StringVar(value="X")
        ttk.Entry(labels_frame, textvariable=self.x_label_var, validatecommand=self.auto_config_change, width=30).grid(row=0, column=1, padx=5, pady=2, sticky=tk.W)
        ttk.Label(labels_frame, text="Y-axis Label:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.y_label_var = tk.StringVar(value="Y")
        ttk.Entry(labels_frame, textvariable=self.y_label_var, validatecommand=self.auto_config_change, width=30).grid(row=1, column=1, padx=5, pady=2, sticky=tk.W)

        # Data source
        source_frame = ttk.LabelFrame(config_frame, text="Data Source", padding=10)
        source_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(source_frame, text="Source:").pack(side=tk.LEFT)
        self.data_source_var = tk.StringVar(value="raw")
        self.data_source_combo = ttk.Combobox(source_frame, textvariable=self.data_source_var, state='readonly', width=20)
        self.data_source_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(source_frame, text="Refresh", command=self.update_data_sources).pack(side=tk.LEFT, padx=5)
        
        # Plot type
        type_frame = ttk.LabelFrame(config_frame, text="Plot Type", padding=10)
        type_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(type_frame, text="Type:").pack(side=tk.LEFT)
        self.plot_type_var = tk.StringVar(value="scatter")
        self.plot_type_combo = ttk.Combobox(type_frame, textvariable=self.plot_type_var, values=["scatter", "line", "bar", "box", "histogram"], state='readonly', width=15)
        self.plot_type_combo.bind('<<ComboboxSelected>>', self.auto_config_change)
        self.plot_type_combo.pack(side=tk.LEFT, padx=5)
        
        # Series configuration
        series_frame = ttk.LabelFrame(config_frame, text="Data Series", padding=10)
        series_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        series_list_frame = ttk.Frame(series_frame)
        series_list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.series_listbox = tk.Listbox(series_list_frame, height=6)
        series_scrollbar = ttk.Scrollbar(series_list_frame, orient=tk.VERTICAL, command=self.series_listbox.yview)
        self.series_listbox.configure(yscrollcommand=series_scrollbar.set)
        self.series_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        series_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        series_controls = ttk.Frame(series_frame)
        series_controls.pack(fill=tk.X)
        ttk.Button(series_controls, text="Add Series", command=self.add_series_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(series_controls, text="Add All", command=self.add_all_series).pack(side=tk.LEFT, padx=2)
        ttk.Button(series_controls, text="Remove", command=self.remove_series).pack(side=tk.LEFT, padx=2)
        ttk.Button(series_controls, text="Remove All", command=self.remove_all_series).pack(side=tk.LEFT, padx=2)
        ttk.Button(series_controls, text="Edit", command=self.edit_series_dialog).pack(side=tk.LEFT, padx=2)
        
        # Right panel - Plot display
        right_panel = ttk.Frame(paned)
        paned.add(right_panel, weight=2)
        
        plot_container = ttk.LabelFrame(right_panel, text="Plot Display", padding=10)
        plot_container.pack(fill=tk.BOTH, expand=True)
        self.figure = Figure(figsize=(8, 6), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.figure, plot_container)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.toolbar = NavigationToolbar2Tk(self.canvas, plot_container)
        self.toolbar.update()
        
        self.plot_status = ttk.Label(right_panel, text="No plot data", relief=tk.SUNKEN, anchor=tk.W)
        self.plot_status.pack(fill=tk.X, pady=(10, 0))
    
    # ==================== FILE OPERATIONS ====================
    
    def select_model(self):
        """Select model file"""
        filename = filedialog.askopenfilename(title="Select UPPAAL Model", filetypes=[("XML files", "*.xml"), ("All files", "*.*")])
        if filename:
            self.model_file = filename
            self.model_entry.delete(0, tk.END)
            self.model_entry.insert(0, filename)
            self.load_model_declarations()
    
    def select_queries(self):
        """Select queries file"""
        filename = filedialog.askopenfilename(title="Select UPPAAL Queries", filetypes=[("Query files", "*.q"), ("All files", "*.*")])
        if filename:
            self.queries_file = filename
            self.queries_entry.delete(0, tk.END)
            self.queries_entry.insert(0, filename)
            with open(self.queries_file) as f:
                self.declarations["Queries File"] = f.read()
    
    def save_experiment_config(self):
        """Save experiment configuration (not data)"""
        filename = filedialog.asksaveasfilename(title="Save Experiment Configuration", filetypes=[("Config files", "*.cfg"), ("JSON files", "*.json"), ("All files", "*.*")], defaultextension=".cfg")
        if not filename: return
        
        try:
            config_data = {
                'model_file': self.model_file,
                'queries_file': self.queries_file,
                'user_variables': dict(self.user_variables),
                'seed': self.seed_value.get(),
                'num_threads': self.num_threads.get(),
                'transformations': self.transformations,
                'plot_configs': dict(self.plot_configs),
                'save_time': datetime.now().isoformat(),
                'config_version': '1.0'
            }
            
            with open(filename, 'w') as f:
                json.dump(config_data, f, indent=2, default=str)
            
            messagebox.showinfo("Success", f"Experiment configuration saved to {filename}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save configuration: {str(e)}")
    
    def load_experiment_config(self):
        """Load experiment configuration"""
        filename = filedialog.askopenfilename(title="Load Experiment Configuration", filetypes=[("Config files", "*.cfg"), ("JSON files", "*.json"), ("All files", "*.*")])
        if not filename: return
        
        try:
            with open(filename, 'r') as f:
                config_data = json.load(f)
            
            # Load configuration
            self.model_file = config_data.get('model_file')
            self.queries_file = config_data.get('queries_file')
            self.user_variables = OrderedDict(config_data.get('user_variables', {}))
            self.seed_value.set(config_data.get('seed', '0'))
            self.num_threads.set(config_data.get('num_threads', 1))
            
            # Load transformations
            loaded_transformations = config_data.get('transformations', {})
            self.transformations = {}
            self.transformed_data = {}
            
            for name, code in loaded_transformations.items():
                self.transformations[name] = code
            
            self.plot_configs = OrderedDict(config_data.get('plot_configs', {}))
            
            # Update UI
            if self.model_file:
                self.model_entry.delete(0, tk.END)
                self.model_entry.insert(0, self.model_file)
                self.load_model_declarations()
            
            if self.queries_file:
                self.queries_entry.delete(0, tk.END)
                self.queries_entry.insert(0, self.queries_file)
                with open(self.queries_file) as f:
                    self.declarations["Queries File"] = f.read()
                self.declaration_combo['values'] = list(self.declarations.keys())
            
            self.merge_variables()
            self.load_variables()
            self.update_plot_configs_list()
            if self.plot_configs:
                self.plot_config_var.set(list(self.plot_configs.keys())[0])
                self.on_plot_config_selected(None)
            
            self.update_transform_list()
            messagebox.showinfo("Success", f"Experiment configuration loaded from {filename}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load configuration: {str(e)}")
            traceback.print_exc()
    
    def export_experiment_data(self):
        """Export experiment data (results) to file"""
        if not self.raw_data and not self.results:
            messagebox.showwarning("Warning", "No experiment data to export")
            return
        
        filename = filedialog.asksaveasfilename(title="Export Experiment Data", filetypes=[("JSON files", "*.json"), ("Pickle files", "*.pkl"), ("All files", "*.*")], defaultextension=".json")
        if not filename: return
        
        try:
            if filename.endswith('.json'):
                export_data = {
                    'raw_data': self.raw_data,
                    'results': self.results,
                    'transformed_data': self.transformed_data,
                    'export_time': datetime.now().isoformat()
                }
                with open(filename, 'w') as f:
                    json.dump(export_data, f, indent=2, default=str)
            elif filename.endswith('.pkl'):
                export_data = {
                    'raw_data': self.raw_data,
                    'results': self.results,
                    'transformed_data': self.transformed_data,
                    'export_time': datetime.now().isoformat()
                }
                with open(filename, 'wb') as f:
                    pickle.dump(export_data, f)
            
            messagebox.showinfo("Success", f"Experiment data exported to {filename}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export data: {str(e)}")
    
    # ==================== MODEL TAB METHODS ====================
    
    def load_model_declarations(self):
        """Load declarations from model file"""
        if not self.model_file: return
        
        try:
            with open(self.model_file) as f:
                model = xml.parse(f)
            
            self.declarations = {}
            
            # Project declarations
            project = model.xpath("declaration")
            if project:
                self.declarations["project"] = project[0].text or ""
            
            # Template declarations
            templates = model.xpath("template//declaration")
            for template in templates:
                parent = template.getparent().xpath("name")
                if parent:
                    self.declarations[parent[0].text] = template.text or ""
            
            # System declarations
            system = model.xpath("system")
            if system:
                self.declarations["system"] = system[0].text or ""
            
            self.extract_default_variables()
            self.declaration_combo['values'] = list(self.declarations.keys())
            if self.declarations:
                self.declaration_combo.current(0)
                self.on_declaration_selected(None)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load model: {str(e)}")
    
    def extract_default_variables(self):
        """Extract default variables from declarations"""
        self.default_variables = OrderedDict()
        
        for section, text in self.declarations.items():
            if not text: continue
            
            lines = text.splitlines()
            for line in lines:
                if "@param" in line:
                    line = line.split(";")[0]
                    if "=" in line:
                        parts = line.split("=", 1)
                        if len(parts) == 2:
                            var_part = parts[0].strip()
                            value = parts[1].strip()
                            var_name = var_part.split()[-1]
                            
                            if section not in self.default_variables:
                                self.default_variables[section] = OrderedDict()
                            
                            self.default_variables[section][var_name] = value
        
        self.merge_variables()
        self.load_variables()
    
    def merge_variables(self):
        """Merge default variables with user-modified variables"""
        self.variables = OrderedDict()
        
        # Start with default variables
        for section, vars_dict in self.default_variables.items():
            if section not in self.variables:
                self.variables[section] = OrderedDict()
            
            for var_name, default_value in vars_dict.items():
                if (section in self.user_variables and var_name in self.user_variables[section]):
                    self.variables[section][var_name] = self.user_variables[section][var_name]
                else:
                    self.variables[section][var_name] = default_value
        
        # Add any user variables not in defaults
        for section, vars_dict in self.user_variables.items():
            if section not in self.variables:
                self.variables[section] = OrderedDict()
            
            for var_name, value in vars_dict.items():
                if var_name not in self.variables[section]:
                    self.variables[section][var_name] = value
    
    def load_variables(self):
        """Load variables into treeview"""
        for item in self.var_tree.get_children():
            self.var_tree.delete(item)
        
        for section, vars_dict in self.variables.items():
            for var_name, value in vars_dict.items():
                self.var_tree.insert('', tk.END, values=(f"{section}.{var_name}", value))
    
    def refresh_variables(self):
        """Refresh variables from declarations (preserving user changes)"""
        if self.model_file:
            self.extract_default_variables()
            messagebox.showinfo("Refreshed", "Variables refreshed from declarations")
        else:
            messagebox.showwarning("Warning", "No model file selected")
    
    def on_variable_double_click(self, _):
        """Handle double-click on variable to edit"""
        item = self.var_tree.selection()
        if not item: return
        
        item = item[0]
        values = self.var_tree.item(item, 'values')
        if len(values) < 2: return
        
        full_name = values[0]
        current_value = values[1] if len(values) > 1 else ""
        
        # Create edit dialog
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Edit Variable Value")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.geometry(f"+{self.root.winfo_rootx()+200}+{self.root.winfo_rooty()+200}")
        
        ttk.Label(dialog, text="New Value:").pack(anchor=tk.W, padx=20, pady=(10, 0))
        new_value_var = tk.StringVar(value=current_value)
        entry = ttk.Entry(dialog, textvariable=new_value_var, width=40)
        entry.pack(padx=20, pady=(5, 0))
        entry.select_range(0, tk.END)
        entry.focus_set()
        
        ttk.Label(dialog, text="Examples: 5, range(0,10,2), list(1,3,5)", font=('Segoe UI', 8), foreground='gray').pack(padx=20, pady=(5, 15))
        
        def save_changes():
            new_value = new_value_var.get()
            self.var_tree.item(item, values=(full_name, new_value))
            
            # Update user_variables dictionary
            if '.' in full_name:
                section, var_name = full_name.split('.', 1)
            elif ',' in full_name:
                section, var_name = full_name.split(',', 1)
            else:
                section = "project"
                var_name = full_name
            
            if section not in self.user_variables:
                self.user_variables[section] = OrderedDict()
            
            self.user_variables[section][var_name] = new_value
            self.merge_variables()
            dialog.destroy()
        
        def cancel():
            dialog.destroy()
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=(0, 15))
        ttk.Button(btn_frame, text="Save", command=save_changes, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=cancel, width=10).pack(side=tk.LEFT, padx=5)
        
        dialog.bind('<Return>', lambda e: save_changes())
        dialog.bind('<Escape>', lambda e: cancel())
    
    # ==================== DECLARATIONS TAB METHODS ====================
    
    def load_declarations(self):
        """Load declarations into combo box"""
        if not self.declarations:
            messagebox.showwarning("Warning", "No declarations loaded")
            return
        
        self.declaration_combo['values'] = list(self.declarations.keys())
        if self.declarations:
            self.declaration_combo.current(0)
            self.on_declaration_selected(None)
    
    def on_declaration_selected(self, _):
        """Handle declaration selection"""
        selection = self.declaration_var.get()
        if selection in self.declarations:
            self.declaration_editor.delete(1.0, tk.END)
            self.declaration_editor.insert(1.0, self.declarations[selection])
    
    def save_declaration(self):
        """Save declaration changes back to model file"""
        selection = self.declaration_var.get()
        if not selection:
            messagebox.showwarning("Warning", "No declaration selected")
            return
        
        path = f"//template[declaration and name/text()='{selection}']//declaration"
        new_text = self.declaration_editor.get(1.0, tk.END).strip()
        if selection == "project":
            path = "declaration"
        elif selection == "System":
            path = "system"
        elif selection == "Queries File":
            with open(self.queries_file, "w") as f:
                f.write(new_text)
                messagebox.showinfo("Saved", f"Declaration '{selection}' updated")
            return
            
        with open(self.model_file, "r") as f:
            model = xml.parse(f)

        elements = model.xpath(path)
        if elements:
            elem = elements[0]
            if elem.text:
                elem.text = new_text
        
        with open(self.model_file, "w") as f:
            f.write(xml.tostring(model).decode("UTF-8"))

        self.declarations[selection] = new_text
        self.extract_default_variables()
        messagebox.showinfo("Saved", f"Declaration '{selection}' updated")
    
    # ==================== EXPERIMENTS TAB METHODS ====================
    
    def start_experiment(self):
        """Start experiments"""
        if not self.model_file or not self.queries_file:
            messagebox.showwarning("Missing Files", "Please select model and queries files")
            return
        
        try:
            seed = int(self.seed_value.get())
        except ValueError:
            messagebox.showwarning("Invalid Seed", "Seed must be an integer")
            return
        
        # Prepare variables for process_model
        vars_dict = {}
        for item in self.var_tree.get_children():
            name, value = self.var_tree.item(item, 'values')
            section = name.split('.')[0]
            var_name = name.split('.')[1]
            
            if section not in vars_dict:
                vars_dict[section] = []
            vars_dict[section].append([var_name, value])
        
        if not vars_dict:
            messagebox.showwarning("No Variables", "No variables configured")
            return
        
        # Clear previous results
        self.results_text.delete(1.0, tk.END)
        self.raw_data = {}
        self.transformed_data = {}
        self.update_data_sources()
        self.update_transform_list()
        
        # Update UI
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.status_label.config(text="Starting experiments...")
        self.progress_bar['value'] = 0
        
        # Start thread
        self.experiment_thread = threading.Thread(
            target=self.run_experiment,
            args=(seed, self.num_threads.get(), vars_dict),
            daemon=True
        )
        self.experiment_thread.start()
    
    def run_experiment(self, seed, threads, vars_dict):
        """Run experiment in background thread"""
        try:
            def progress_callback(current, total):
                self.progress_queue.put(('progress', current, total))
            
            self.results = process_model.run_verification_pipeline(
                self.model_file,
                self.queries_file,
                vars_dict,
                seed=seed,
                threads=threads,
                progress_callback=progress_callback
            )
            
            self.progress_queue.put(('complete', self.results))
            
        except Exception as e:
            self.progress_queue.put(('error', str(e)))
    
    def stop_experiment(self):
        """Stop experiment"""
        self.stop_event.set()
        self.status_label.config(text="Stopping...")
    
    def check_progress(self):
        """Check for progress updates"""
        try:
            while True:
                msg = self.progress_queue.get_nowait()
                
                if msg[0] == 'progress':
                    current, total = msg[1], msg[2]
                    progress = (current / total) * 100 if total > 0 else 0
                    self.progress_bar['value'] = progress
                    self.status_label.config(text=f"Processing {current}/{total} variations")
                    
                elif msg[0] == 'complete':
                    self.experiment_complete(msg[1])
                    
                elif msg[0] == 'error':
                    self.status_label.config(text=f"Error: {msg[1]}")
                    self.start_btn.config(state='normal')
                    self.stop_btn.config(state='disabled')
        
        except queue.Empty:
            pass
        
        finally:
            self.root.after(100, self.check_progress)
    
    def experiment_complete(self, results):
        """Handle experiment completion"""
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.progress_bar['value'] = 100
        self.status_label.config(text="Experiment completed successfully")
        
        if results:
            self.results = results
            self.process_raw_data()
            self.display_results()
            self.update_data_sources()
            self.update_transform_list()
            self.plot_status.config(text=f"Experiment data ready ({len(self.raw_data)} variations)")
    
    def process_raw_data(self):
        """Process raw results into simple data structure"""
        self.raw_data = {}
        
        for key, result in self.results.items():
            if key == 'statistics': continue
            
            var_id = result.get('variation_id', 0)
            assignment = result.get('assignment', [])
            
            # Create assignment dict
            assign_dict = {}
            for sec, var, val in assignment:
                assign_dict[var] = val
            
            # Create label
            label_parts = [f"{var}={val}" for var, val in assign_dict.items()]
            label = ", ".join(label_parts) if label_parts else f"Variation {var_id}"
            
            # Extract data points
            data_points = result.get('data_points', {})
            
            # Extract formula satisfaction
            formula_satisfaction = 0
            summary = result.get('summary', {})
            if 'satisfied_formulas' in summary:
                formula_satisfaction = sum(1 for f in summary['satisfied_formulas'] if f.get('satisfied'))
            
            # Store data
            self.raw_data[var_id] = {
                'variation_id': var_id,
                'assignment': assign_dict,
                'label': label,
                'data_points': data_points,
                'formula_satisfaction': formula_satisfaction,
                'success': result.get('success', False)
            }
    
    def display_results(self):
        """Display results in text area"""
        self.results_text.delete(1.0, tk.END)
        
        if not self.results:
            self.results_text.insert(tk.END, "No results")
            return
        
        stats = self.results.get('statistics', {})
        
        # Display statistics
        self.results_text.insert(tk.END, "=" * 60 + "\n")
        self.results_text.insert(tk.END, "EXPERIMENT RESULTS\n")
        self.results_text.insert(tk.END, "=" * 60 + "\n\n")
        
        self.results_text.insert(tk.END, f"Total variations: {stats.get('total_variations', 0)}\n")
        self.results_text.insert(tk.END, f"Successful runs: {stats.get('successful_runs', 0)}\n")
        self.results_text.insert(tk.END, f"Failed runs: {stats.get('failed_runs', 0)}\n")
        self.results_text.insert(tk.END, f"Random seed: {stats.get('seed_used', 'N/A')}\n")
        self.results_text.insert(tk.END, f"Threads used: {stats.get('threads_used', 'N/A')}\n\n")
        
        # Display each variation
        self.results_text.insert(tk.END, "-" * 60 + "\n")
        self.results_text.insert(tk.END, "VARIATION DETAILS\n")
        self.results_text.insert(tk.END, "-" * 60 + "\n\n")
        
        for var_id, data in self.raw_data.items():
            self.results_text.insert(tk.END, f"Variation {var_id}:\n")
            self.results_text.insert(tk.END, f"  Label: {data['label']}\n")
            self.results_text.insert(tk.END, f"  Status: {'SUCCESS' if data['success'] else 'FAILED'}\n")
            self.results_text.insert(tk.END, f"  Formulas satisfied: {data['formula_satisfaction']}\n")
            if data['data_points']:
                for data_point in data['data_points']:
                    self.results_text.insert(tk.END, f"  Data variables: {', '.join(data_point.keys())}\n")
            self.results_text.insert(tk.END, "\n")
    
    def copy_results(self):
        """Copy results to clipboard"""
        self.root.clipboard_clear()
        self.root.clipboard_append(self.results_text.get(1.0, tk.END))
        messagebox.showinfo("Copied", "Results copied to clipboard")
    
    def view_raw_data(self):
        """View raw data summary in a dialog"""
        if not self.raw_data:
            messagebox.showinfo("No Data", "No raw data available")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Raw Data Summary")
        dialog.geometry("500x400")
        
        text = scrolledtext.ScrolledText(dialog, height=20, font=('Consolas', 9))
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        text.insert(tk.END, f"RAW DATA SUMMARY\n")
        text.insert(tk.END, "=" * 50 + "\n\n")
        text.insert(tk.END, f"Total variations: {len(self.raw_data)}\n")
        text.insert(tk.END, f"Successful runs: {sum(1 for d in self.raw_data.values() if d.get('success', False))}\n\n")
        
        text.insert(tk.END, "VARIATION SUMMARY:\n")
        text.insert(tk.END, "-" * 40 + "\n")
        
        for var_id, data in self.raw_data.items():
            text.insert(tk.END, f"Variation {var_id}:\n")
            text.insert(tk.END, f"  Label: {data.get('label', 'N/A')}\n")
            text.insert(tk.END, f"  Status: {'SUCCESS' if data.get('success', False) else 'FAILED'}\n\n")
            data_points = data.get('data_points', [])
            for data_point in data_points:
                for trace, data in data_point.items():
                    text.insert(tk.END,f"{trace} {data}")
        
        text.configure(state='disabled')
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        ttk.Button(btn_frame, text="Close", command=dialog.destroy).pack()
    
    def clear_results(self):
        """Clear all results"""
        self.results = None
        self.raw_data = {}
        self.transformed_data = {}
        self.results_text.delete(1.0, tk.END)
        self.figure.clear()
        self.canvas.draw()
        self.update_data_sources()
        self.update_transform_list()
        self.status_label.config(text="Ready")
        self.plot_status.config(text="No data")
    
    # ==================== TRANSFORM TAB METHODS ====================
    
    def new_transformation(self):
        """Create a new transformation"""
        self.transform_name_var.set("new_transformation")
        self.transform_code.delete(1.0, tk.END)
        self.transform_status.config(text="New transformation created")
    
    def save_transformation(self):
        """Save current transformation"""
        name = self.transform_name_var.get().strip()
        code = self.transform_code.get(1.0, tk.END).strip()
        
        if not name:
            messagebox.showwarning("Warning", "Please enter a transformation name")
            return
        
        if not code:
            messagebox.showwarning("Warning", "Transformation code cannot be empty")
            return
        
        # Save transformation
        self.transformations[name] = code
        
        self.update_transform_list()
        if name in self.transformed_data:
            del self.transformed_data[name]
        
        self.transform_status.config(text=f"Transformation '{name}' saved")
    
    def remove_transformation(self):
        """Remove selected transformation"""
        selection = self.transform_listbox.curselection()
        if not selection:
            messagebox.showinfo("No Selection", "Please select a transformation to remove")
            return
        
        name = self.transform_listbox.get(selection[0])
        
        if messagebox.askyesno("Confirm", f"Remove transformation '{name}'?"):
            if name in self.transformations:
                del self.transformations[name]
            if name in self.transformed_data:
                del self.transformed_data[name]
            self.update_transform_list()
            self.update_data_sources()
            self.transform_status.config(text=f"Transformation '{name}' removed")
    
    def on_transform_list_select(self, _):
        """Handle transformation list selection - update name AND code"""
        selection = self.transform_listbox.curselection()
        if selection:
            name = self.transform_listbox.get(selection[0])
            self.transform_name_var.set(name)
            
            if name in self.transformations:
                code = self.transformations[name]
                self.transform_code.delete(1.0, tk.END)
                self.transform_code.insert(tk.END, code)
                
                if hasattr(self.transform_code, '_highlight'):
                    self.transform_code._highlight()
                self.transform_status.config(text=f"Loaded: {name}")
            else:
                self.transform_code.delete(1.0, tk.END)
                self.transform_status.config(text=f"Not found: {name}")
    
    def update_transform_list(self):
        """Update transformations listbox"""
        self.transform_listbox.delete(0, tk.END)
        for name in sorted(self.transformations.keys()):
            self.transform_listbox.insert(tk.END, name)
    
    def run_all_transformations(self):
        """Execute all transformations"""
        if not self.transformations:
            messagebox.showinfo("No Transformations", "No transformations to run")
            return
        
        if not self.raw_data:
            messagebox.showwarning("No Data", "No experiment data available")
            return
        
        if not messagebox.askyesno("Run All", f"Run all {len(self.transformations)} transformations?"):
            return
        
        # Create progress dialog
        progress_dialog = tk.Toplevel(self.root)
        progress_dialog.title("Running Transformations")
        progress_dialog.transient(self.root)
        progress_dialog.resizable(False, False)
        ttk.Label(progress_dialog, text=f"Running {len(self.transformations)} transformations...", font=('Segoe UI', 10)).pack(pady=(20, 10))
        progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(progress_dialog, variable=progress_var, maximum=len(self.transformations), mode='determinate')
        progress_bar.pack(padx=20, pady=(0, 20), fill=tk.X)
        progress_dialog.update()
        
        # Run each transformation
        success_count = 0
        current_data_source = self.data_source_var.get()
        should_update_plot = False
        
        for i, (name, code) in enumerate(self.transformations.items()):
            try:
                if self.execute_transformation(name, code, silent=True):
                    success_count += 1
                    if name == current_data_source:
                        should_update_plot = True
            except Exception as e:
                print(f"Error in transformation '{name}': {e}")
            
            progress_var.set(i + 1)
            progress_dialog.update()
        
        progress_dialog.destroy()
        self.update_transform_list()
        self.update_data_sources()
        
        # AUTO-UPDATE PLOT IF CURRENT DATA SOURCE WAS EXECUTED
        if should_update_plot and self.notebook.tab(self.notebook.select(), "text") == "Plot":
            self.auto_update_plot()
        
        messagebox.showinfo("Complete", f"Ran {len(self.transformations)} transformations\nSuccess: {success_count}\nFailed: {len(self.transformations) - success_count}")
        self.transform_status.config(text=f"Ran all transformations ({success_count} successful)")
        
    def execute_current_transformation(self):
        name = self.transform_name_var.get().strip()
        code = self.transform_code.get(1.0, tk.END)
        self.execute_transformation(name, code)
    
    def execute_transformation(self, name, code,  silent=False):
        """Execute transformation code"""
        if not self.raw_data and not silent:
            messagebox.showwarning("No Data", "No experiment data available")
            return
        
        if not name and not silent:
            messagebox.showwarning("No Name", "Please specify a transformation name")
            return
        
        # Save the transformation first
        self.transformations[name] = code
        
        try:
            safe_globals = {
                'raw_data': self.raw_data,
                'results': self.results,
                'np': np,
                'math': __import__('math'),
                'statistics': __import__('statistics'),
                'json': json,
                'list': list,
                'range': range,
                'dict': dict
            }
            
            exec(code, safe_globals)
            result = None
            if "result" in safe_globals:
                result = safe_globals["result"]
            
            if result is not None:
                self.transformed_data[name] = result
                if not silent:
                    self.update_transform_list()
                    self.update_data_sources()
                    self.transform_status.config(text=f"Success: {name} ({len(result)} items)")
                else:
                    return True
                
                # AUTO-UPDATE PLOT IF THIS IS THE CURRENT DATA SOURCE
                if not silent and (self.notebook.tab(self.notebook.select(), "text") == "Plot" and 
                    self.data_source_var.get() == name):
                    self.auto_update_plot()
            else:
                if not silent:
                    messagebox.showwarning("No Result", "Transformation did not produce a result")
                
        except Exception as e:
            error_msg = str(e)
            self.transform_status.config(text=f"Error: {error_msg[:50]}...")
            if not silent:
                messagebox.showerror("Execution Error", f"{error_msg}\n\nSee console for details")
            traceback.print_exc()
        return False
    
    def view_transform_result(self):
        """View transformation result"""
        name = self.transform_name_var.get()
        if name not in self.transformed_data:
            messagebox.showinfo("No Result", f"Transformation '{name}' has not been executed")
            return
        
        result = self.transformed_data[name]
        
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Transformation Result: {name}")
        
        columns = ('key', 'x_type', 'x_len', 'y_type', 'y_len', 'label')
        tree = ttk.Treeview(dialog, columns=columns, show='headings', height=15)
        
        for col in columns:
            tree.heading(col, text=col.replace('_', ' ').title())
            tree.column(col, width=100)
        
        scrollbar = ttk.Scrollbar(dialog, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        for key, value in result.items():
            if isinstance(value, dict):
                x_val = value.get('x', [])
                y_val = value.get('y', [])
                x_type = type(x_val).__name__
                y_type = type(y_val).__name__
                x_len = len(x_val) if hasattr(x_val, '__len__') else 1
                y_len = len(y_val) if hasattr(y_val, '__len__') else 1
                label = value.get('label', '')
                tree.insert('', tk.END, values=(key, x_type, x_len, y_type, y_len, label))
    
    # ==================== PLOT TAB METHODS ====================
    
    def create_plot_config(self):
        """Create a new plot configuration"""
        dialog = tk.Toplevel(self.root)
        dialog.title("New Plot Configuration")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        
        ttk.Label(dialog, text="New Plot Configuration", font=('Segoe UI', 10, 'bold')).pack(pady=(20, 10))
        ttk.Label(dialog, text="Configuration Name:").pack()
        name_var = tk.StringVar(value=f"plot_{len(self.plot_configs) + 1}")
        name_entry = ttk.Entry(dialog, textvariable=name_var, width=30)
        name_entry.pack(pady=5)
        name_entry.select_range(0, tk.END)
        name_entry.focus_set()
        
        def create():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("Warning", "Please enter a name")
                return
            
            if name in self.plot_configs:
                messagebox.showwarning("Warning", f"Configuration '{name}' already exists")
                return
            
            self.plot_configs[name] = {
                'data_source': 'raw',
                'plot_type': 'scatter',
                'series': [],
                'title': 'Plot',
                'x_label': 'X',
                'y_label': 'Y',
                'include_seed': False
            }
            
            self.update_plot_configs_list()
            self.plot_config_var.set(name)
            self.on_plot_config_selected(None)
            dialog.destroy()
        
        def cancel():
            dialog.destroy()
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=15)
        ttk.Button(btn_frame, text="Create", command=create, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=cancel, width=10).pack(side=tk.LEFT, padx=5)
        
        dialog.bind('<Return>', lambda e: create())
        dialog.bind('<Escape>', lambda e: cancel())
    
    def auto_save_plot_config(self):
        """Automatically save the current plot configuration"""
        name = self.plot_config_var.get()
        if not name or name not in self.plot_configs:
            return
        
        config = {
            'data_source': self.data_source_var.get(),
            'plot_type': self.plot_type_var.get(),
            'series': [],
            'title': self.plot_title_var.get(),
            'x_label': self.x_label_var.get(),
            'y_label': self.y_label_var.get(),
            'include_seed': self.include_seed_var.get()
        }
        
        for i in range(self.series_listbox.size()):
            series_str = self.series_listbox.get(i)
            if ' | ' in series_str:
                parts = series_str.split(' | ')
                if len(parts) >= 5:
                    series = {
                        'label': parts[0],
                        'x_array': parts[1],
                        'y_array': parts[2],
                        'color': parts[3],
                        'series_key': parts[4] if len(parts) > 4 else ''
                    }
                    config['series'].append(series)
        
        self.plot_configs[name] = config
        self.plot_status.config(text=f"Configuration '{name}' auto-saved")
    
    def rename_plot_config(self):
        """Rename the current plot configuration"""
        name = self.plot_config_var.get()
        if name not in self.plot_configs:
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Rename Plot Configuration")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        
        ttk.Label(dialog, text="Rename Plot Configuration", font=('Segoe UI', 10, 'bold')).pack(pady=(20, 10))
        ttk.Label(dialog, text="Current Name:").pack()
        ttk.Label(dialog, text=name, font=('Consolas', 10), background='white', relief=tk.SUNKEN, width=30).pack(pady=5)
        ttk.Label(dialog, text="New Name:").pack()
        new_name_var = tk.StringVar(value=name)
        name_entry = ttk.Entry(dialog, textvariable=new_name_var, width=30)
        name_entry.pack(pady=5)
        name_entry.select_range(0, tk.END)
        name_entry.focus_set()
        
        def rename():
            new_name = new_name_var.get().strip()
            if not new_name:
                messagebox.showwarning("Warning", "Please enter a new name")
                return
            
            if new_name == name:
                dialog.destroy()
                return
            
            if new_name in self.plot_configs:
                messagebox.showwarning("Warning", f"Configuration '{new_name}' already exists")
                return
            
            self.plot_configs[new_name] = self.plot_configs.pop(name)
            self.update_plot_configs_list()
            self.plot_config_var.set(new_name)
            dialog.destroy()
            self.auto_update_plot()
            self.plot_status.config(text=f"Renamed '{name}' to '{new_name}'")
        
        def cancel():
            dialog.destroy()
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=15)
        ttk.Button(btn_frame, text="Rename", command=rename, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=cancel, width=10).pack(side=tk.LEFT, padx=5)
        
        dialog.bind('<Return>', lambda e: rename())
        dialog.bind('<Escape>', lambda e: cancel())
    
    def auto_config_change(self, _=None):
        """Handle configuration changes by auto-saving and auto-updating"""
        self.auto_save_plot_config()
        if self.notebook.tab(self.notebook.select(), "text") == "Plot":
            self.auto_update_plot()
    
    def auto_update_plot(self):
        """Automatically update plot with current configuration"""
        self.plot_status.config(text=f"Updating plot....")
        try:
            data_source = self.data_source_var.get()
            
            if data_source in self.transformed_data:
                data = self.transformed_data[data_source]
            else:
                return
            
            if not data: return
            
            self.figure.clear()
            ax = self.figure.add_subplot(111)
            plot_type = self.plot_type_var.get()
            
            base_title = self.plot_title_var.get()
            if self.include_seed_var.get() and self.seed_value.get() != "0":
                title = f"{base_title} (Seed: {self.seed_value.get()})"
            else:
                title = base_title
            
            x_label = self.x_label_var.get()
            y_label = self.y_label_var.get()
            x_vals = []
            y_vals = []
            labels = []
            colors = []
            for i in range(self.series_listbox.size()):
                series_str = self.series_listbox.get(i)
                parts = series_str.split(' | ')
                
                if len(parts) < 5: continue
                label, _, _, color, series_key = parts[0], parts[1], parts[2], parts[3], parts[4]
                
                if series_key in data:
                    series_data = data[series_key]

                    x_vals.append(series_data.get('x', []))
                    y_vals.append(series_data.get('y', []))
                    labels.append(label)
                    colors.append(color)
            try:
                if (plot_type == "box"):
                    ax.boxplot(y_vals, tick_labels=x_vals)
                elif (plot_type == "histogram"):
                    ax.hist(y_vals, bins=20, alpha=0.7, color='blue', edgecolor='black')
                else:
                    for x, y, c, l in zip(x_vals, y_vals, colors, labels):
                        if (plot_type == "scatter"):
                            ax.scatter(x, y, color=c, label=l, alpha=0.6, s=80)
                        elif (plot_type == "line"):
                            ax.plot(x, y, color=c, label=l, marker='o', linewidth=2)
                        elif (plot_type == "bar"):
                            ax.bar(x, y, color=c, label=l, alpha=0.7)
                        else:
                            self.plot_status.config(text=f"Error creating box plot: {str(e)}")
                            return
            except Exception as e:
                self.plot_status.config(text=f"Error creating box plot: {str(e)}")
            ax.set_title(title)
            ax.set_xlabel(x_label)
            ax.set_ylabel(y_label)
            
            self.figure.tight_layout()
            self.canvas.draw()
            
            from datetime import datetime
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.plot_status.config(text=f"Plot auto-updated at {timestamp}")
            
        except Exception as e:
            print(f"Auto-update plot error: {e}")
    
    def delete_plot_config(self):
        """Delete current plot configuration"""
        name = self.plot_config_var.get()
        if name not in self.plot_configs:
            return
        
        if messagebox.askyesno("Confirm", f"Delete plot configuration '{name}'?"):
            del self.plot_configs[name]
            self.update_plot_configs_list()
            
            if self.plot_configs:
                self.plot_config_var.set(list(self.plot_configs.keys())[0])
                self.on_plot_config_selected(None)
            else:
                self.create_plot_config()
    
    def on_plot_config_selected(self, _):
        """Handle plot configuration selection"""
        name = self.plot_config_var.get()
        if name in self.plot_configs:
            config = self.plot_configs[name]
            
            self.data_source_var.set(config.get('data_source', 'raw'))
            self.plot_type_var.set(config.get('plot_type', 'scatter'))
            self.plot_title_var.set(config.get('title', 'Plot'))
            self.x_label_var.set(config.get('x_label', 'X'))
            self.y_label_var.set(config.get('y_label', 'Y'))
            self.include_seed_var.set(config.get('include_seed', False))
            
            self.series_listbox.delete(0, tk.END)
            for series in config.get('series', []):
                label = series.get('label', '')
                x_array = series.get('x_array', '')
                y_array = series.get('y_array', '')
                color = series.get('color', 'blue')
                series_key = series.get('series_key', '')
                series_str = f"{label} | {x_array} | {y_array} | {color} | {series_key}"
                self.series_listbox.insert(tk.END, series_str)
            
            self.auto_update_plot()
    
    def update_plot_configs_list(self):
        """Update plot configurations combo box"""
        self.plot_config_combo['values'] = list(self.plot_configs.keys())
    
    def add_series_dialog(self):
        """Open dialog to add a new series with array selection"""
        data_source = self.data_source_var.get()
        
        if data_source == "raw":
            messagebox.showinfo("Info", "Raw data requires transformation before plotting.\nPlease create a transformation first.")
            return
        
        if data_source not in self.transformed_data:
            messagebox.showwarning("No Data", f"No data available for '{data_source}'")
            return
        
        data = self.transformed_data[data_source]
        available_series = list(data.keys())
        if not available_series:
            messagebox.showwarning("No Series", "No series found in the selected data source")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Data Series")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        
        ttk.Label(dialog, text="Add New Data Series", font=('Segoe UI', 10, 'bold')).pack(pady=(15, 10))
        ttk.Label(dialog, text="Select Series:").pack(anchor=tk.W, padx=20)
        series_var = tk.StringVar(value=available_series[0])
        series_combo = ttk.Combobox(dialog, textvariable=series_var, values=available_series, state='readonly', width=40)
        series_combo.pack(padx=20, pady=(0, 10))
        
        preview_frame = ttk.LabelFrame(dialog, text="Series Preview", padding=10)
        preview_frame.pack(fill=tk.X, padx=20, pady=(0, 10))
        preview_text = tk.StringVar(value="Select a series to preview")
        preview_label = ttk.Label(preview_frame, textvariable=preview_text, font=('Consolas', 8), wraplength=300)
        preview_label.pack()
        
        def update_preview(*args):
            selected_series = series_var.get()
            if selected_series in data:
                series_data = data[selected_series]
                x_len = len(series_data.get('x', [])) if hasattr(series_data.get('x', []), '__len__') else 1
                y_len = len(series_data.get('y', [])) if hasattr(series_data.get('y', []), '__len__') else 1
                preview_text.set(f"X: array of {x_len}, Y: array of {y_len}, Label: {series_data.get('label', selected_series)}")
        
        series_var.trace('w', update_preview)
        update_preview()
        
        ttk.Label(dialog, text="Series Label:").pack(anchor=tk.W, padx=20)
        label_var = tk.StringVar(value=f"Series {self.series_listbox.size() + 1}")
        ttk.Entry(dialog, textvariable=label_var, width=40).pack(padx=20, pady=(0, 10))
        
        ttk.Label(dialog, text="Color:").pack(anchor=tk.W, padx=20)
        color_var = tk.StringVar(value="blue")
        color_combo = ttk.Combobox(dialog, textvariable=color_var, width=20,
                                values=["blue", "red", "green", "orange", "purple", "brown", "pink", "gray", "cyan", "magenta"])
        color_combo.pack(padx=20, pady=(0, 15))
        
        def add_series():
            selected_series = series_var.get()
            label = label_var.get().strip()
            color = color_var.get()
            
            if not label:
                messagebox.showwarning("Warning", "Please enter a series label")
                return
            
            series_str = f"{label} | x | y | {color} | {selected_series}"
            self.series_listbox.insert(tk.END, series_str)
            dialog.destroy()
            self.auto_update_plot()
            self.auto_save_plot_config()
        
        def cancel():
            dialog.destroy()
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=(0, 15))
        ttk.Button(btn_frame, text="Add", command=add_series, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=cancel, width=10).pack(side=tk.LEFT, padx=5)
        
        dialog.bind('<Return>', lambda e: add_series())
        dialog.bind('<Escape>', lambda e: cancel())
    
    def add_all_series(self):
        """Add all series from the current data source"""
        data_source = self.data_source_var.get()
        
        if data_source == "raw":
            messagebox.showinfo("Info", "Raw data requires transformation before plotting.\nPlease create a transformation first.")
            return
        
        if data_source not in self.transformed_data:
            messagebox.showwarning("No Data", f"No data available for '{data_source}'")
            return
        
        data = self.transformed_data[data_source]
        if not data:
            messagebox.showwarning("No Series", "No series found in the selected data source")
            return
        
        colors = ["blue", "red", "green", "orange", "purple", "brown", "pink", "gray", "cyan", "magenta", "navy", "maroon", "olive", "teal", "coral"]
        
        if self.series_listbox.size() > 0:
            if not messagebox.askyesno("Confirm", "Clear existing series before adding all?"):
                return
            self.series_listbox.delete(0, tk.END)
        
        series_names = list(data.keys())
        series_names = [name for name in series_names if not name.startswith('_')]
        
        if not series_names:
            messagebox.showwarning("No Series", "No valid series found to add")
            return
        
        # Show progress dialog for large datasets
        if len(series_names) > 10:
            progress_dialog = tk.Toplevel(self.root)
            progress_dialog.title("Adding Series")
            progress_dialog.transient(self.root)
            progress_dialog.resizable(False, False)
            ttk.Label(progress_dialog, text=f"Adding {len(series_names)} series...", font=('Segoe UI', 10)).pack(pady=(20, 10))
            progress_var = tk.DoubleVar()
            progress_bar = ttk.Progressbar(progress_dialog, variable=progress_var, maximum=len(series_names), mode='determinate')
            progress_bar.pack(padx=20, pady=(0, 20), fill=tk.X)
            progress_dialog.update()
        
        for i, series_name in enumerate(series_names):
            series_data = data[series_name]
            label = series_data.get('label', series_name)
            color = series_data.get('color', colors[i % len(colors)])
            series_str = f"{label} | x | y | {color} | {series_name}"
            self.series_listbox.insert(tk.END, series_str)
            
            if len(series_names) > 10:
                progress_var.set(i + 1)
                progress_dialog.update()
        
        if len(series_names) > 10:
            progress_dialog.destroy()
        
        self.plot_status.config(text=f"Added {len(series_names)} series")
        self.auto_update_plot()
        self.auto_save_plot_config()
    
    def remove_series(self):
        """Remove selected series"""
        selection = self.series_listbox.curselection()
        if selection:
            self.series_listbox.delete(selection[0])
            self.auto_save_plot_config()
            self.auto_update_plot()
    
    def remove_all_series(self):
        """Remove all series from the plot"""
        if self.series_listbox.size() == 0:
            messagebox.showinfo("No Series", "No series to remove")
            return
        
        if messagebox.askyesno("Confirm", f"Remove all {self.series_listbox.size()} series?"):
            self.series_listbox.delete(0, tk.END)
            self.plot_status.config(text="All series removed")
            self.figure.clear()
            self.canvas.draw()
            self.auto_save_plot_config()
    
    def edit_series_dialog(self):
        """Edit selected series"""
        selection = self.series_listbox.curselection()
        if not selection:
            messagebox.showinfo("No Selection", "Please select a series to edit")
            return
        
        series_str = self.series_listbox.get(selection[0])
        parts = series_str.split(' | ')
        
        if len(parts) < 5:
            return
        
        data_source = self.data_source_var.get()
        if data_source not in self.transformed_data:
            messagebox.showwarning("No Data", f"No data available for '{data_source}'")
            return
        
        data = self.transformed_data[data_source]
        available_series = list(data.keys())
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Data Series")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        
        ttk.Label(dialog, text="Edit Data Series", font=('Segoe UI', 10, 'bold')).pack(pady=(15, 10))
        ttk.Label(dialog, text="Select Series:").pack(anchor=tk.W, padx=20)
        series_var = tk.StringVar(value=parts[4] if len(parts) > 4 else '')
        series_combo = ttk.Combobox(dialog, textvariable=series_var, values=available_series, state='readonly', width=40)
        series_combo.pack(padx=20, pady=(0, 10))
        
        ttk.Label(dialog, text="Series Label:").pack(anchor=tk.W, padx=20)
        label_var = tk.StringVar(value=parts[0])
        ttk.Entry(dialog, textvariable=label_var, width=40).pack(padx=20, pady=(0, 10))
        
        ttk.Label(dialog, text="Color:").pack(anchor=tk.W, padx=20)
        color_var = tk.StringVar(value=parts[3] if len(parts) > 3 else 'blue')
        color_combo = ttk.Combobox(dialog, textvariable=color_var, width=20,
                                values=["blue", "red", "green", "orange", "purple", "brown", "pink", "gray", "cyan", "magenta"])
        color_combo.pack(padx=20, pady=(0, 15))
        
        def save_changes():
            selected_series = series_var.get()
            label = label_var.get().strip()
            color = color_var.get()
            
            if not label:
                messagebox.showwarning("Warning", "Please enter a series label")
                return
            
            series_str = f"{label} | x | y | {color} | {selected_series}"
            self.series_listbox.delete(selection[0])
            self.series_listbox.insert(selection[0], series_str)
            dialog.destroy()
            self.auto_save_plot_config()
            self.auto_update_plot()
        
        def cancel():
            dialog.destroy()
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=(0, 15))
        ttk.Button(btn_frame, text="Save", command=save_changes, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=cancel, width=10).pack(side=tk.LEFT, padx=5)
        
        dialog.bind('<Return>', lambda e: save_changes())
        dialog.bind('<Escape>', lambda e: cancel())
    
    def update_data_sources(self):
        """Update data source dropdown"""
        sources = []
        sources.extend(self.transformed_data.keys())
        self.data_source_combo['values'] = sources
        
        current = self.data_source_var.get()
        if current not in sources and sources:
            self.data_source_var.set(sources[0])
    
    def on_closing(self):
        """Handle window closing"""
        if self.experiment_thread and self.experiment_thread.is_alive():
            self.stop_event.set()
            self.experiment_thread.join(timeout=1.0)
        self.root.destroy()

def main():
    root = tk.Tk()
    root.title("UPPAAL Experiment Suite")
    app = UPPAALExperimentRunner(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()