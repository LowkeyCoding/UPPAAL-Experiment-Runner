import argparse
from lxml import etree
import pprint
import itertools
import process_model
import numpy as np
import matplotlib.pyplot as plt
import simdjson
from pathlib import Path

def get_var_val(assignment, section, name):
    return list(filter(lambda x: x[0] == section and x[1] == name, assignment))[0][2]

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
        'plt': plt
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
            raw = process_model.run_verification_pipeline(
                globals["model"],
                globals["queries"],
                get_assignments(globals["vars"]),
                globals["seed"],
                globals["threads"])
            with open(globals["experiment_data"] + "out.data", "w") as f:
                f.write(simdjson.dumps(raw))
    if args.plot or args.export:
        if globals["experiment_data"] != None:
            with open(globals["experiment_data"] + "out.data") as f:
                data = simdjson.loads(f.read())
                for plot, kw in globals["plots"]:
                    fig, ax = plt.subplots(subplot_kw=kw)
                    plot(ax, data)
                    if args.export and len(globals["extensions"]):
                        for ex in globals["extensions"]:
                            plt.savefig(globals["experiment_data"] + ax.get_title().replace(" ", "_") +f".{ex}", format=ex)
                if args.plot:
                    plt.show()

def get_sections(model):
    with open(model) as f:
        model = etree.parse(f)
    # Project declarations
    project = model.xpath("declaration")
    sections = {}
    if project:
        sections["project"] = project[0].text or ""
    
    # Template declarations
    templates = model.xpath("template//declaration")
    for template in templates:
        parent = template.getparent().xpath("name")
        if parent:
            sections[parent[0].text] = template.text or ""
    
    # System declarations
    system = model.xpath("system")
    if system:
        sections["system"] = system[0].text or ""
    return sections

def get_params(sections):
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
    options = []
    for section, var_list in vars.items():
        for var, val in var_list.items():
            if type(val) != str:
                options.append([(section, var, v) for v in val])
            else:
                options.append([(section, var, val)])
    if not options:
        return []
    # Cartesian product
    return [list(comb) for comb in itertools.product(*options)]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="TBD"
    )
    parser.add_argument("--config", required=True, type=str)
    parser.add_argument("--get_params", action='store_true')
    parser.add_argument("--run", action='store_true')
    parser.add_argument("--plot", action='store_true')
    parser.add_argument("--export", action='store_true')
    args = parser.parse_args()
    main(args)