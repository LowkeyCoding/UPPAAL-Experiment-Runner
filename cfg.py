model = "/home/lokew/Documents/code/DensityMatrixQuantumSimulator/quantum-superdense-coding-6-sliding-window-2-noisy.xml"
queries = "/home/lokew/Documents/code/DensityMatrixQuantumSimulator/quantum-superdense-coding-6-sliding-window-2-noisy.q"

vars = {
    'project': {
        'Bitstuffing': list(range(0, 9)),
        'T1': '20',
        'T2': '18',
        },
    'system': {
        'sender': 'SenderTimeslotted(qbit, X0, Z0, H0, CNOT, One, Zero, Generate)',
        'receiver': 'RecieverTimeslotted(qbit, H0, CNOT, Measure, Out, One_in, Zero_in, Bitstuff)'
    }
}

threads = 9
seed = 428094
experiment_data = "/home/lokew/Documents/code/UPPAAL-Experiment-Runner/output_cfg/"
plots = []
extensions = ["svg", "eps"]
def get_error_per_bitsuffing(ax, data, TARGET_QUERY_ID = 0):
    if not data:
        raise ValueError("No experiment data available.")

    print(f"Processing {len(data)} variations for box plots...")

    # Group by timeslot value first
    grouped_data = {}  # key: timeslot value, value: list of last values
    # Process each variation
    for _, data in data.items():
        if not data.get('success', False):
            continue
        assignment = data.get('assignment', {})
        bitstuffing = get_var_val(assignment, "project", "Bitstuffing")
        
        # Initialize group if not exists
        if bitstuffing not in grouped_data:
            grouped_data[bitstuffing] = []
        # Extract last values from all traces
        data_points = data.get('data_points', {})
        data_points = data_points[TARGET_QUERY_ID]
        for _, points in data_points.items():
            if points:
                try:
                    last_value = float(points[-1][1])
                    grouped_data[bitstuffing].append(last_value)
                except (ValueError, IndexError, TypeError):
                    continue

    # Convert to plot-ready format
    X = []
    Y = []
    for bitstuffing, values in sorted(grouped_data.items()):
        X.append(bitstuffing)
        Y.append(values)
    ax.boxplot(Y, tick_labels=X)

def errors_per_qubit(ax, data):
    get_error_per_bitsuffing(ax, data)
    ax.set_title("Errors per Qubit Sent")
    ax.set_xlabel("c (Bitstuffing)")
    ax.set_ylabel("Errors / Qubits")

def errors_per_bit(ax, data):
    get_error_per_bitsuffing(ax, data)
    ax.set_title("Errors per Bits Sent")
    ax.set_xlabel("c (Bitstuffing)")
    ax.set_ylabel("Errors / Bits")

def bits_per_qubit(ax, data):
    get_error_per_bitsuffing(ax, data)
    ax.set_title("Bits per Qubit Sent")
    ax.set_xlabel("c (Bitstuffing)")
    ax.set_ylabel("Bits / Qubits")

def bits_per_timeslot(ax, data):
    get_error_per_bitsuffing(ax, data)
    ax.set_title("Bits per Timeslot Sent")
    ax.set_xlabel("c (Bitstuffing)")
    ax.set_ylabel("Bits / Timeslot")

plots.append((errors_per_qubit, {}))
plots.append((errors_per_bit, {}))
plots.append((bits_per_qubit, {}))
plots.append((bits_per_timeslot, {}))