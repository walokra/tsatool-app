# tsatool-app

Tool for analyzing Finnish road weather station (TieSääAsema) data. Data will is located and handled in a PostgreSQL & [TimescaleDB](https://www.timescale.com/) database, and analyses are run through a Python API. See the [Wiki page](https://github.com/webbidevaajat/tsatool-app/wiki) for more details and examples.

To get familiar with road weather station data models and properties, see the documentation for the [real time API](https://www.digitraffic.fi/tieliikenne/).

You can get some kind of a clue about what this is about by reading our first [Wiki page](https://github.com/webbidevaajat/tsatool-app/wiki/Ehtosetin-muotoilu) about formatting the input data (in Finnish).

## Installation

This tool has been developed in Python 3.7.
Older versions will not work.
Make sure you have [pip](https://pypi.org/project/pip/) pkg manager installed,
and run the following command in the project directory to install the dependencies:

```
pip install -r requirements.txt
```

Optionally, you can use [virtualenv](https://docs.python-guide.org/dev/virtualenvs/) to use an isolated Python environment to run the tool. It's worth noting that on macOS you need to use stdlib's [venv](https://docs.python.org/3/library/venv.html) instead of virtualenv, see: [Working with Matplotlib on OSX](https://matplotlib.org/3.1.0/faq/osx_framework.html).

For example:

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Data model (briefly)

- Data is read from an input Excel file into an [`AnalysisCollection`](tsa/analysis_collection.py).
It can contain multiple Excel sheets.
The sheets must contain data in exactly correct cells to be readable (see `example_data/`).
An `AnalysisCollection` represents a whole analysis dataset run at once.
- Each Excel sheet is read into a [`CondCollection`](tsa/cond_collection.py).
This collection contains condition rows and a start and an end date that are common for all the conditions in the collection.
For instance, you could analyze the same conditions for 1.1.-28.2.2018 and 1.9.-31.10.2018 by using two separate sheets.
- Each condition row in an Excel sheet is read into a [`Condition`](tsa/condition.py).
It is a collection of boolean sensor states or states of other `Condition`s combined by `AND`, `OR`, `NOT` and parentheses, thus resulting in a boolean `master` value.
A `Collection` must have a `site` and a `master_alias` identifier that together are unique within their parent `CondCollection`.
*Primary* `Collection` consists of primary `Block`s only, *secondary* `Collection`s have at least one secondary `Block`.
- Each `Condition` consists of [`Block`s](tsa/block.py).
A `Block` represents the state of a sensor of a station (*Primary*) or the state of another referenced `Condition` (*Secondary*).
On the database side, it renders a single boolean column.
A `Block` could be defined as `s1122#tie_1 < 3`, for instance.
Note the three-valued logic: if the sensor's numeric value in a time period is not known (`NULL`), also the value of the boolean column will be `NULL`.

## Database and raw data handling

See [database](database/).

To successfully run the `tsabatch.py` analysis script,
you should have the following environment variables prepared,
unless you have configured the database instance according to the default values:

| Variable name 	| Default value in `tsa/analysis_collection.py` 	|
|---------------	|-----------------------------------------------	|
| `PG_HOST`     	| `localhost`                                   	|
| `PG_PORT`     	| `5432`                                        	|
| `PG_DBNAME`   	| `tsa`                                         	|
| `PG_USER`     	| `postgres`                                    	|
| `PG_PASSWORD` 	| `postgres`                                    	|

## Running an analysis

Run `python tsabatch.py --help` to see available command line arguments and their usage.

### "Dry" validation

With the `--dryvalidate` flag,
the analysis script prepares the conditions,
checks their syntax,
checks the existence of sensor names, ids and station ids against hard-coded sets
(see [`utils.py`](tsa/utils.py)),
and records possible errors.
No database interaction is needed,
so you can use the result of dry validation to determine whether to spin up a database instance for actual analysis, for example.

```
python tsabatch.py -i example_data/testset.xlsx -n test_analysis --dryvalidate
```

Now, if there were *any* errors in the above run,
the script will raise an error (which you can catch in a shell script, for example),
and corresponding logs and error message JSON tree are saved in `results/`.
If the run was clean, the script exits normally.

### Full analysis

Full analysis is done without `--dryvalidate` flag,
given that the database is available.
You could combine dry validation and full analysis e.g. as follows:

```
python tsabatch.py -i example_data/toimiva.xlsx -n test_analysis --dryvalidate \
  # The && requires that the dry validation did not cause an error:
  && some_script_that_spins_up_the_database.sh
  # Now without --dryvalidate:
  && python tsabatch.py -i example_data/toimiva.xlsx -n test_analysis
```

All file paths here are relative to the project directory.
The above command would save resulting Excel and PowerPoint files as `results/test_analysis_[...]`.

## Logging

Default logging level is `info`, at which most of the essential analysis steps are saved to the log stream.
You can specify a logging level with the `--log` argument and one of the following values: `error, warning, info, debug`. `debug` will print out all the SQL `CREATE` statements, for example.

Example:

```
python tsabatch.py -i example_data/toimiva.xlsx -n test_analysis --log debug
```

Log files are saved to `results/[analysis name].log`.
No file rotation is configured,
and a second run using the same name will overwrite the log file (as well as other result files with the same name).

## Errors

Examples of erroneous inputs can be found in `example_data/testset.xlsx`.
Error messages are recorded to the log stream of the analysis,
and they are saved into per-object error lists as well.
These lists are collected into a tree structure and saved as JSON in `results/`.

Fatal errors, such as missing input file, interrupt the entire analysis script.
Most errors will just render a sheet or condition row invalid, and that sheet / condition will not be analyzed further.

## Authors

- **Arttu Kosonen** - [datarttu](https://github.com/datarttu), arttu.kosonen (ät) wsp.com

## Copyright

WSP Finland & ITM Finland 2019
