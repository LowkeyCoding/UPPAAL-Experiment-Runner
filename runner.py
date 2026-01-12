import argparse
from lxml import etree
import pprint
import itertools
import process_model
import numpy as np
import matplotlib.pyplot as plt
import h5py
from pathlib import Path
import ast

def get_var_val(assignment, section, name):
    """Get variable value from assignment tuple list"""
    for sec, var, val in assignment:
        if sec == section and var == name:
            return val
    return None

def h5_progress_callback(h5file_path):
    """Create a progress callback that updates HDF5 file"""
    def callback(result, var_id, total):
        # Just print progress, HDF5 is updated in main function
        print(f"Completed variation {var_id}")
    return callback

def main(args):
    globals = {
        'model': None,
        'queries': None,
        'vars': None,
        'threads': 1,
        'seed': 0,
        'experiment_data': None,
        'plots': [],
        'export_plots': None,
        'extensions': [],
        'get_var_val': get_var_val,
        'np': np,
        'plt': plt,
        'h5py': h5py  # Make h5py available in config
    }
    
    with open(args.config) as f:
        code = f.read()
    
    exec(code, globals)
    
    if args.get_params:
        if globals['model'] != None:
            pprint.pp(get_params(get_sections(globals['model'])))
        else:
            raise Exception("The model parameter must be set") 
    
    if args.run:
        if globals['model'] != None and globals['queries'] != None and globals["experiment_data"]:
            Path(globals["experiment_data"]).mkdir(parents=True, exist_ok=True)
            
            hdf5_path = Path(globals["experiment_data"]) / "results.h5"
            
            # Convert vars to list format expected by process_model
            vars_list = {}
            if globals["vars"]:
                for section, var_dict in globals["vars"].items():
                    vars_list[section] = [(var, val) for var, val in var_dict.items()]
            
            # Get assignments as generator (not stored in memory)
            assignments = process_model.generate_all_assignments(vars_list)
            
            # Count total assignments if needed for progress
            # Note: This could be expensive for large combinations
            
            process_model.run_verification_pipeline(
                globals["model"],
                globals["queries"],
                assignments,
                globals["seed"],
                globals["threads"],
                hdf5_file=str(hdf5_path),
                progress_callback=h5_progress_callback(hdf5_path))
            
            print(f"Results saved to {hdf5_path}")
    
    if args.plot or args.export:
        if globals["experiment_data"] != None:
            hdf5_path = Path(globals["experiment_data"]) / "results.h5"
            
            if not hdf5_path.exists():
                print(f"Error: HDF5 file not found at {hdf5_path}")
                return
            
            # Plot from HDF5 without loading everything at once
            with h5py.File(hdf5_path, 'r') as h5file:
                # Create plotting function that streams from HDF5
                for plot_func, kw in globals["plots"]:
                    fig, ax = plt.subplots(subplot_kw=kw)
                    
                    # Plot function needs to handle HDF5 directly
                    plot_func(ax, h5file)
                    
                    if args.export and len(globals["extensions"]):
                        title = ax.get_title().replace(" ", "_") if ax.get_title() else "plot"
                        for ex in globals["extensions"]:
                            plt.savefig(
                                Path(globals["experiment_data"]) / f"{title}.{ex}",
                                format=ex)
                
                if args.plot:
                    plt.show()

def get_sections(model):
    """Extract sections from XML model"""
    with open(model) as f:
        model_tree = etree.parse(f)
    
    sections = {}
    
    # Project declarations
    project = model_tree.xpath("declaration")
    if project:
        sections["project"] = project[0].text or ""
    
    # Template declarations
    templates = model_tree.xpath("template//declaration")
    for template in templates:
        parent = template.getparent().xpath("name")
        if parent:
            sections[parent[0].text] = template.text or ""
    
    # System declarations
    system = model_tree.xpath("system")
    if system:
        sections["system"] = system[0].text or ""
    
    return sections

def get_params(sections):
    """Extract parameters marked with @param"""
    vars = {}
    for section, code in sections.items():
        if section not in vars:
            vars[section] = {}
        
        for line in code.splitlines():
            if "@param" in line:
                line = line.split(";")[0]
                if "=" in line:
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        var_part = parts[0].strip()
                        value = parts[1].strip()
                        var_name = var_part.split()[-1]
                        vars[section][var_name] = value
    
    return {k: v for k, v in vars.items() if v}

def get_assignments(vars):
    """Generate assignments - returns generator for memory efficiency"""
    options = []
    for section, var_list in vars.items():
        for var, val in var_list.items():
            if isinstance(val, str):
                # Parse string definitions
                parsed = process_model.parse_variable_definition(val)
                options.append([(section, var, v) for v in parsed])
            elif hasattr(val, '__iter__'):
                options.append([(section, var, v) for v in val])
            else:
                options.append([(section, var, val)])
    
    if not options:
        return []
    
    # Return as generator to avoid memory explosion
    return (list(comb) for comb in itertools.product(*options))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Experimental parameter sweeper for UPPAAL models"
    )
    parser.add_argument("--config", required=True, type=str,
                       help="Configuration Python file")
    parser.add_argument("--get_params", action='store_true',
                       help="Extract parameters from model and exit")
    parser.add_argument("--run", action='store_true',
                       help="Run the experiments")
    parser.add_argument("--plot", action='store_true',
                       help="Plot results")
    parser.add_argument("--export", action='store_true',
                       help="Export plots to files")
    args = parser.parse_args()
    main(args)