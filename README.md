# UPPAAL Experiment Runner

A simple tool to run parameterized models by marking variables with a comment containing `@param`.

## Cli runner
The cli tool should be constructed as a cli program that takes a python file as a config.
the python tool will have access to a set of variables.
- `model` which is the path to the model file
- `queries` which is either a path to a query file or a list of queries.
- `vars` A dict of dicts where the outer dict is the section and the inner dict is the variable definitions.
    - The variable value should be a list of values that can be cast to string.
- `threads` the number of threads to use when runinning model queries.
- `experiment_data` the file path for the data of the experiment.
- `plots` a list of functions generating matplotlib graphs.
- `export_plots` a list of formats to export the plots to.

The tool should be able to generate a default list of variable assignments based on the placement of `@param` by runinng `runner --get-params` when the `model` variable is set.
The tool should be able to then get the experiment data by running `runner --run` generating a file when the `model`, `queries` and `experiment_data` are set.
The tool should be able to generate a window with user designed plots using `runner --plots` when the previous varaibles are set and `plots` is not an empty list. 
The tool should be able to export user plots when the preivous variables and `export_plots` is set by running `runner --export`.