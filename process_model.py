# process_model.py - Simplified
import subprocess
import re
import tempfile
import itertools
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from lxml import etree as xml

def parse_variable_definition(var_def):
    """Parse variable definition into list of values"""
    if 'range' in var_def:
        try:
            match = re.search(r'range\((\d+),\s*(\d+)(?:,\s*(\d+))?\)', var_def)
            if match:
                start = int(match.group(1))
                end = int(match.group(2))
                step = int(match.group(3)) if match.group(3) else 1
                return list(range(start, end, step))
        except:
            return []
    elif 'list' in var_def:
        try:
            match = re.search(r'list\((.*?)\)', var_def)
            if match:
                return [v.strip() for v in match.group(1).split(',')]
        except:
            pass
    
    # Comma-separated values
    return [v.strip() for v in var_def.split(',') if v.strip()]

def generate_all_assignments(variables):
    """Generate all variable assignments"""
    options = []
    
    for section, var_list in variables.items():
        for var, val in var_list:
            values = parse_variable_definition(val)
            options.append([(section, var, v) for v in values])
    
    if not options:
        return []
    
    # Cartesian product
    return [list(comb) for comb in itertools.product(*options)]

def generate_model_variations(model_content, assignments):
    """Create model files for each assignment"""
    temp_files = []
    
    for i, assignment in enumerate(assignments):
        tree = xml.fromstring(model_content.encode())
        
        # Group by section
        by_section = {}
        for section, var, val in assignment:
            if section not in by_section:
                by_section[section] = []
            by_section[section].append((var, val))
        
        # Replace in each section
        for section, vars_list in by_section.items():
            if section == "project":
                path = "declaration"
            elif section == "system":
                path = "system"
            else:
                path = f"//template[declaration and name/text()='{section}']//declaration"
            
            elements = tree.xpath(path)
            if elements:
                elem = elements[0]
                if elem.text:
                    for var, val in vars_list:
                        pattern = rf"{var}\s*=\s*[^;]*;"
                        replacement = f"{var} = {val};"
                        elem.text = re.sub(pattern, replacement, elem.text, flags=re.MULTILINE)
        # Save to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix=f'_var_{i}.xml', delete=False) as f:
            f.write(xml.tostring(tree).decode("UTF-8"))
            temp_files.append(f.name)
    
    return temp_files

def run_verifyta_single(model_file, query_file, seed, timeout):
    """Run verifyta on a single model"""
    cmd = ["verifyta"]
    if seed != 0:
        cmd.extend(["--seed", str(seed)])
    cmd.extend([model_file, query_file])
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        
        # Parse output
        data_points = []
        formulas = []
        # Formular index
        fidx = -1

        lines = result.stdout.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Data points
            if line.startswith("["):
                parts = line.split(':', 1)
                if len(parts) == 2:
                    var = parts[0].strip()
                    points_str = parts[1].strip()
                    
                    # Parse (t, v) pairs
                    points = []
                    matches = re.findall(r'\(([^,]+),\s*([^)]+)\)', points_str)
                    for t, v in matches:
                        try:
                            t_val = float(t) if '.' in t else int(t)
                            v_val = float(v) if '.' in v else int(v)
                            points.append((t_val, v_val))
                        except:
                            points.append((t, v))
                    if points:
                        data_points[fidx][var] = points
            
            # Formula verification
            elif 'Verifying formula' in line:
                match = re.search(r'Verifying formula (\d+)', line)
                if match:
                    fidx += 1
                    data_points.append({})
                    formulas.append({
                        'number': match.group(1),
                        'satisfied': None
                    })
            
            elif ' -- Formula is satisfied' in line and formulas:
                formulas[-1]['satisfied'] = True
            
            elif ' -- Formula is not satisfied' in line and formulas:
                formulas[-1]['satisfied'] = False

        return {
            'success': result.returncode == 0,
            'stderr': result.stderr,
            'data_points': data_points,
            'formulas': formulas,
            'return_code': result.returncode
        }
    
    except subprocess.TimeoutExpired:
        return {'success': False, 'error': 'Timeout'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def run_verification_pipeline(model_file, query_file, assignments, seed=0, threads=4, timeout=None, progress_callback=None):
    """Main pipeline to run all experiments"""
    # Read model
    with open(model_file) as f:
        model_content = f.read()
    
    if not assignments:
        return {}
    
    print(f"Running {len(assignments)} variations...")
    
    # Create model variations
    temp_files = generate_model_variations(model_content, assignments)
    
    results = {}
    
    try:
        # Run in parallel
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {}
            for i, (model_file, assignment) in enumerate(zip(temp_files, assignments)):
                future = executor.submit(run_verifyta_single, model_file, query_file, seed, timeout)
                futures[future] = (i, assignment)
            
            # Collect results
            for i, future in enumerate(as_completed(futures)):
                var_id, assignment = futures[future]
                try:
                    result = future.result(timeout=timeout)
                    
                    # Add assignment info
                    result['variation_id'] = var_id
                    result['assignment'] = assignment
                    
                    # Create summary
                    satisfied = sum(1 for f in result.get('formulas', []) if f.get('satisfied'))
                    result['summary'] = {
                        'satisfied_formulas': [{
                            'formula': f.get('number'),
                            'satisfied': f.get('satisfied')
                        } for f in result.get('formulas', [])],
                        'satisfied_count': satisfied
                    }
                    
                    results[f"variation_{var_id}"] = result
                    
                    # Update progress
                    if progress_callback:
                        progress_callback(i + 1, len(assignments))
                    
                except Exception as e:
                    print(f"Error in variation {var_id}: {e}")
        
        return results
    
    finally:
        # Cleanup
        for f in temp_files:
            try:
                os.unlink(f)
            except:
                pass