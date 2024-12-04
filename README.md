# GitHub Runner Log Extractor

The logs on a GitHub Runner contain a wealth of information. There might be cases where you would like to extract specific information from the logs. This tool helps you extract the information you need from the logs.

In this case we are extracting the following information:

- The Id of the Job that ran on the runner.
- Details on any actions/checkout that was performed. This collects details on the repositories that were checked out and what the duration was.

## Usage

The log extractor has been developed as a Python script. Typically we want to run this file whenever a job completes on the runner. The best way to do this is to schedule it on the runner hook job completed event by configuring the script in the `ACTIONS_RUNNER_HOOK_JOB_COMPLETED` environment variable. More details can be found [Running scripts before or after a job](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/running-scripts-before-or-after-a-job).

So we schedule a shell script that runs the Python script. The shell script will be responsible for setting up the Python environment and running the script. This is done in hook-job-completed.sh.

## How the script works

In a nutshell the script takes the `_diag` directory of the runner as input. And from there it finds the most recent Worker log file by looking for `Worker_`.

From within the worker log file it extracts the Job Id and the details on the actions/checkout that was performed. Followed by looking at the executions of the different actions and collecting the start and end time of them.

The script then submits the extracted data to an Application Insights instance where we can view this data in a dashboard or by a query. The script uses the `APPLICATION_INSIGHTS_INSTRUMENTATION_KEY` environment variable to determine where to send the data. The logging is done in `track_action` and can of course be replaced by any other target destination that you prefer.

## Limitations

This script is meant as an example and can be extended to extract more information from the logs. The script will also have some limitations, for example it is not optimized for handling large log files. It is recommended to test the script on a copy of the log files before running it on the actual log files.
