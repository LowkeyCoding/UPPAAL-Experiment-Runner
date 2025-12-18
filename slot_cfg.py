model = "/home/lokew/Documents/code/DensityMatrixQuantumSimulator/quantum-superdense-coding-6-sliding-window-2-noisy.xml"
queries = "/home/lokew/Documents/code/DensityMatrixQuantumSimulator/slot.q"

vars = {
    'project': {
        'TIMESLOT':list(range(5, 75, 5)),# + list(range(40, 50, 2)) + list(range(50, 75, 5)),
        'Bitstuffing': list(range(0, 9)),
        'T1': '86',
        'T2': '83',
        'setup_mean': '1',
        'setup_sd': '0.01',
        'generate_mean': '20',
        'generate_sd': '8',
        'purification_mean': '0.01',
        'purification_sd': '0.01',
        'H_mean': '1',
        'H_sd': '0.01',
        'X_mean': '1',
        'X_sd': '0.01',
        'Z_mean': '1',
        'Z_sd': '0.01',
        'CX_mean': '2.75',
        'CX_sd': '0.0275'
        },
    'system': {
        'sender': 'SenderShifting(qbit, X0, Z0, H0, CNOT, One, Zero, Generate, Shift, Bitstuff)',
        'receiver': 'Receiver(qbit, H0, CNOT, Measure, Out, One_in, Zero_in, Bitstuff)'
    }
}

threads = 18
seed = 428094
experiment_data = "/home/lokew/Documents/code/UPPAAL-Experiment-Runner/output_slot/"
plots = []
extensions = ["svg", "eps"]
def get_error_per_timeslot(ax, data, TARGET_QUERY_ID = 0, TARGET_BITSTUFFING = 8, MIN_TIMESLOT = 15):
    if not data:
        raise ValueError("No experiment data available.")

    print(f"Processing {len(data)} variations for box plots...")

    # Group by timeslot value first
    grouped_data = {}  # key: timeslot value, value: list of last values
    # Process each variation
    for var_id, data in data.items():
        if not data.get('success', False):
            continue
        assignment = data.get('assignment', {})
        timeslot = get_var_val(assignment, "project", "TIMESLOT")
        bitstuffing = get_var_val(assignment, "project", "Bitstuffing")
        if bitstuffing != TARGET_BITSTUFFING:
            continue
        if timeslot < MIN_TIMESLOT:
            continue
        
        # Initialize group if not exists
        if timeslot not in grouped_data:
            grouped_data[timeslot] = []
        # Extract last values from all traces
        data_points = data.get('data_points', {})
        data_points = data_points[TARGET_QUERY_ID]
        for _, points in data_points.items():
            if points:
                try:
                    last_value = float(points[-1][1])
                    grouped_data[timeslot].append(last_value)
                except (ValueError, IndexError, TypeError):
                    continue

    # Convert to plot-ready format
    X = []
    Y = []
    for timeslot, values in sorted(grouped_data.items()):
        X.append(timeslot)
        Y.append(values)
    ax.boxplot(Y, tick_labels=X)

def get_3d_error(ax, data, TARGET_QUERY_ID = 0, MIN_TIMESLOT = 30):
    plot_args = {"cmap": "viridis", 'linewidth': 0.2, "antialiased": True}

    if not data:
        raise ValueError("No experiment data available.")

    # Group by timeslot value first
    x_vals = []
    y_vals = []
    z_vals = []
    # Process each variation
    for _, data in data.items():
        if not data.get('success', False):
            continue
        assignment = data.get('assignment', {})
        timeslot = get_var_val(assignment, "project", "TIMESLOT")
        bitstuffing = get_var_val(assignment, "project", "Bitstuffing")
        if timeslot < MIN_TIMESLOT:
            continue
        
        # Extract last values from all traces
        data_points = data.get('data_points', {})
        data_points = data_points[TARGET_QUERY_ID]
        t_z = []
        for _, points in data_points.items():
            t_z.append(float(points[-1][1]))
        x_vals.append(timeslot)
        y_vals.append(bitstuffing+2)
        from statistics import mean
        z_vals.append(mean(t_z))
    ax.plot_trisurf(x_vals, y_vals, z_vals, **plot_args)

def shifting_error_qubit(ax, data):
    get_error_per_timeslot(ax, data)
    ax.set_title("Shifts and Errors per Qubit Sent")
    ax.set_xlabel("TIMESLOTS")
    ax.set_ylabel("errors+shifts / qubits")

def shifting_error_bit(ax, data):
    get_error_per_timeslot(ax, data, TARGET_QUERY_ID = 1)
    ax.set_title("Shifts and Errors per Bit Sent")
    ax.set_xlabel("TIMESLOTS")
    ax.set_ylabel("errors+shifts / bits")

def qubit_3d_error(ax, data):
    get_3d_error(ax, data)
    ax.set_title("Shifts and Errors per Qubit Sent 3D")
    ax.set_xlabel("TIMESLOTS")
    ax.set_ylabel("Bitstuffing")
    ax.set_zlabel("errors+shifts / qubits")

def bit_3d_error(ax, data):
    get_3d_error(ax, data, TARGET_QUERY_ID=1)
    ax.set_title("Shifts and Errors per Bit Sent 3D")
    ax.set_xlabel("TIMESLOTS")
    ax.set_ylabel("Bitstuffing")
    ax.set_zlabel("errors+shifts / bits")

plots.append((shifting_error_qubit,{}))
plots.append((shifting_error_bit,{}))
plots.append((qubit_3d_error, {'projection':'3d'}))
plots.append((bit_3d_error, {'projection':'3d'}))