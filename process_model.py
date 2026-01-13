import subprocess
import re
import tempfile
import itertools
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from lxml import etree as xml
import h5py
import numpy as np
from threading import Lock
from queue import Queue, Empty
from threading import Thread, Event

def parse_variable_definition(var_def):
    """Parse variable definition into list of values - handles both strings and lists"""
    # If var_def is already a list, return it as is
    if isinstance(var_def, list) or hasattr(var_def, '__iter__') and not isinstance(var_def, str):
        # Convert to list and handle any nested strings
        result = []
        for item in var_def:
            if isinstance(item, str):
                result.append(item.strip())
            else:
                result.append(item)
        return result
    
    # If it's a string, parse it
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

    return [var_def]

def generate_all_assignments(variables):
    """Generate all variable assignments as generator to avoid memory explosion"""
    options = []
    
    for section, var_list in variables.items():
        for var, val in var_list:
            values = parse_variable_definition(val)
            options.append([(section, var, v) for v in values])
    
    if not options:
        return []
    
    # Return generator instead of list
    return (list(comb) for comb in itertools.product(*options))

def generate_model_variations(model_content, assignments):
    """Create model files for each assignment - yield instead of storing all"""
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
        yield f.name, assignment, i

def run_verifyta_single(model_file, query_file, seed, timeout, var_id, assignment):
    """Run verifyta on a single model and return result with metadata"""
    cmd = ["verifyta"]
    if seed != 0:
        cmd.extend(["--seed", str(seed)])
    cmd.extend([model_file, query_file])
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        
        # Parse output
        data_points = []
        formulas = []
        fidx = -1

        lines = result.stdout.split('\n')
        
        for idx, line in enumerate(lines):
            line = line.strip()
            if line.endswith(":") and idx != 0:
                fidx += 1
                data_points.append({})
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
            'return_code': result.returncode,
            'id': var_id,
            'assignment': assignment
        }
    
    except subprocess.TimeoutExpired:
        return {'success': False, 'error': 'Timeout', 'id': var_id, 'assignment': assignment}
    except Exception as e:
        return {'success': False, 'error': str(e), 'id': var_id, 'assignment': assignment}

def store_result_hdf5(h5file, result):
    """Store a single result in HDF5 format"""
    var_id = result['id']
    assignment = result['assignment']
    
    var_group = h5file.create_group(f'var_{var_id}')
    
    # Store assignment as attributes
    for section, var, val in assignment:
        var_group.attrs[f'param_{section}_{var}'] = val
    
    # Store basic results
    var_group.attrs['success'] = result['success']
    var_group.attrs['return_code'] = result.get('return_code', -1)
    
    if not result['success']:
        if 'error' in result:
            var_group.attrs['error'] = result['error']
        if 'stderr' in result:
            var_group.create_dataset('stderr', data=result['stderr'].encode())
        return
    
    # Store formulas
    if result.get('formulas'):
        formulas_ds = var_group.create_dataset('formulas', 
                                              shape=(len(result['formulas']),),
                                              dtype=h5py.special_dtype(vlen=str))
        for i, formula in enumerate(result['formulas']):
            formulas_ds[i] = f"Formula {formula['number']}: {'SATISFIED' if formula['satisfied'] else 'NOT SATISFIED'}"
    
    # Store data points efficiently
    if result.get('data_points'):
        
        for formula_idx, formula_data in enumerate(result['data_points']):
            formula_group = var_group.create_group(f'formula_{formula_idx}')
            
            for var_name, points in formula_data.items():
                if points:
                    # Convert to structured array for efficient storage
                    dtype = np.dtype([('time', 'f8'), ('value', 'f8')])
                    arr = np.array([(t, v) for t, v in points], dtype=dtype)
                    
                    # Store with compression
                    formula_group.create_dataset(var_name, 
                                                data=arr,
                                                compression='gzip',
                                                compression_opts=4)

def result_writer(h5file, results_queue, h5lock, progress_callback, stop_event):
    """Background thread that writes results to HDF5 as they arrive"""
    processed_count = 0
    while not stop_event.is_set() or not results_queue.empty():
        try:
            result = results_queue.get()
            if result is None:  # Sentinel value
                break
            
            # Write to HDF5
            with h5lock:
                store_result_hdf5(h5file, result)
                h5file.attrs['total_variations'] = processed_count + 1
            
            # Update progress
            if progress_callback:
                progress_callback(result['id'])
            
            processed_count += 1
            results_queue.task_done()
            
        except Empty:
            continue
        except Exception as e:
            print(f"Error in result writer: {e}")
    
    print(f"Result writer finished. Processed {processed_count} results.")

def run_verification_pipeline(model_file, query_file, assignments, seed=0, threads=4, 
                              timeout=None, hdf5_file=None, progress_callback=None, experiment = None):
    """Main pipeline to run all experiments with HDF5 storage"""
    # Read model
    with open(model_file) as f:
        model_content = f.read()

    if not assignments:
        return {}
    print("Running variations...")
    
    # Create HDF5 file
    h5file = h5py.File(hdf5_file, 'w') if hdf5_file else None
    h5lock = Lock() if hdf5_file else None
    
    if h5file:
        # Create datasets structure
        h5file.attrs['total_variations'] = 0
        h5file.attrs['model_file'] = model_file
        h5file.attrs['query_file'] = query_file
        h5file.attrs['experiment'] = str(experiment)
        h5file.attrs['seed'] = seed
    
    # Queue for passing results from worker threads to writer thread
    results_queue = Queue(maxsize=threads * 2)  # Limit queue size
    
    # Event to signal writer thread to stop
    stop_event = None
    
    # Writer thread (if HDF5 is enabled)
    writer_thread = None
    if h5file:
        stop_event = Event()
        writer_thread = Thread(
            target=result_writer,
            args=(h5file, results_queue, h5lock, progress_callback, stop_event),
            daemon=True
        )
        writer_thread.start()
    
    temp_files = []
    total_submitted = 0
    
    try:
        with ThreadPoolExecutor(max_workers=threads) as executor:
            # Submit all jobs, but don't store all futures
            active_futures = set()
            model_gen = generate_model_variations(model_content, assignments)
            
            # Submit initial batch
            for _ in range(threads * 2):
                try:
                    temp_file, assignment, var_id = next(model_gen)
                    future = executor.submit(
                        run_verifyta_single, 
                        temp_file, query_file, seed, timeout, var_id, assignment
                    )
                    active_futures.add(future)
                    temp_files.append(temp_file)
                    total_submitted += 1
                except StopIteration:
                    break
            
            # Process as they complete and submit new ones
            while active_futures:
                # Wait for any future to complete
                done, _ = as_completed(active_futures), None
                for future in done:
                    try:
                        result = future.result(timeout=timeout)
                        
                        # Put result in queue for writer (or process directly)
                        if h5file:
                            results_queue.put(result)
                        
                        # Remove from active futures (allows garbage collection)
                        active_futures.remove(future)
                        del future  # Explicitly delete reference
                        
                        # Submit new job if available
                        try:
                            temp_file, assignment, var_id = next(model_gen)
                            future = executor.submit(
                                run_verifyta_single, 
                                temp_file, query_file, seed, timeout, var_id, assignment
                            )
                            active_futures.add(future)
                            temp_files.append(temp_file)
                            total_submitted += 1
                        except StopIteration:
                            pass
                            
                    except Exception as e:
                        print(f"Error processing future: {e}")
                        if future in active_futures:
                            active_futures.remove(future)
        
        # Signal writer thread to finish
        if stop_event:
            stop_event.set()
            results_queue.put(None)  # Sentinel
        
        # Wait for writer to finish
        if writer_thread:
            writer_thread.join()
            if writer_thread.is_alive():
                print("Warning: Writer thread did not finish in time")
        
        print(f"Total variations submitted: {total_submitted}")
        
    finally:
        # Cleanup temp files
        for f in temp_files:
            try:
                os.unlink(f)
            except:
                pass
        
        # Close HDF5 file
        if h5file:
            # Flush and close
            h5file.flush()
            h5file.close()