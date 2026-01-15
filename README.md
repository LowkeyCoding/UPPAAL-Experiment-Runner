# UPPAAL Experiment Runner

A simple tool to run parameterized models by marking variables with a comment containing `@param`.

## Cli runner
The CLI runner takes a python file as a config that is used to define the parameters for the model and how to plot it. 
- `model` The path to the model file
- `queries` The path to the query file.
- `vars` A dict of dicts where the outer dict is the section and the inner dict is the variable definitions.
    - The variable value should be a list of values that can be cast to string.
- `threads` The number of threads to use when runinning model queries.
- `seed` The seed used by verifyta.
- `experiment_data` The path to the directory to store data of the experiment.
- `plots` A list of functions generating matplotlib graphs.
- `export_plots` A list of formats to export the plots to.

### Arguments
- `--get-params` Prints a json object of all parameters marked with `@param` for easy setup of the model config.
- `--config <path>` Select the config to use to run and process experiment data.
- `--run` Tuns the experiment.
    - Argument Requirements: [`--config`]
    - Config Requirements: [`model`, `queries`, `vars`, `experiment_data`]
- `--plots` Generates plots based on the list of plotting functions.
    - Argument Requirements: [`--config`]
    - Config Requirements: [`plots`]
- `--export` Generates plots based on the list of plotting functions and saves them in the formats provided in `extensions`
    - Argument Requirements: [`--config`]
    - Config Requirements: [`plots`, `extensions`]
- `--force` Removes the prompt to prevent accidentally overwriting results file.