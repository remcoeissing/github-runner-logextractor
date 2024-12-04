import logging
import json
import re
import os
from datetime import datetime
from applicationinsights import TelemetryClient

WORKSPACE_DIAGNOSTICS_DIR = os.getenv('RUNNER_WORKSPACE_DIAG', '/home/runner/_diag')
TELEMETRY_KEY = os.getenv('TELEMETRY_KEY')

class Constants:
    """
    A class to store constants used in the log extractor.
    """

    DATE_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'
    ACCESS_TOKEN_PATTERN = "\"AccessToken\""
    WORKER_LOG_FILE_PATTERN = "Worker_"
    ACTION_MESSAGE_PATTERN = re.compile(r'\[.*? INFO ExecutionContext\] Publish step telemetry for current step \{')
    JOB_MESSAGE_PATTERN = re.compile(r'\[.*? INFO Worker\] Job message:.*')

class CheckoutStepDetails:
    """
    A class to represent the details of a checkout step in a CI/CD pipeline.

    Attributes:
    id (str): The unique identifier of the checkout step.
    startTime (str): The start time of the checkout step in ISO 8601 format.
    finishTime (str): The finish time of the checkout step in ISO 8601 format.
    repository (str): The repository associated with the checkout step.
    duration (float): The duration of the checkout step in seconds.
    """
    def __init__(self, id, startTime, finishTime, repository, parameters) -> None:
        self.id = id
        self.startTime = startTime
        self.finishTime = finishTime
        self.repository = repository
        self.parameters = parameters

    @property
    def duration(self) -> float:
        start = datetime.strptime(truncate_microseconds(self.startTime), Constants.DATE_FORMAT)
        finish = datetime.strptime(truncate_microseconds(self.finishTime), Constants.DATE_FORMAT)
        return (finish - start).total_seconds()

    def __repr__(self) -> str:
        return f"CheckoutStepDetails(id={self.id}, startTime={self.startTime}, finishTime={self.finishTime}, duration={self.duration}, repository={self.repository}, parameters={self.parameters})"

def truncate_microseconds(date_str: str) -> str:
    """
    Truncates the microseconds from a date string.

    Args:
        date_str (str): A date string containing microseconds.

    Returns:
        str: The date string without the microseconds.
    """
    if '.' in date_str:
        date_str = date_str[:date_str.index('.') + 7] + 'Z'
    return date_str

def read_file(file_path: str) -> list[str]:
    """
    Reads the content of a file and returns it as a list of lines.

    Args:
    file_path (str): The path to the file.

    Returns:
    list[str]: The lines of the file.
    """
    try:
        with open(file_path, 'r') as file:
            return file.readlines()
    except FileNotFoundError:
        logging.error(f"File not found: {file_path}")
        return []
    except IOError as e:
        logging.error(f"IO error occurred while reading {file_path}: {e}")
        return []

def process_line(line: str, capturing: bool, json_str: str) -> tuple[bool, str, dict] | None:
    """
    Processes a single line from the log file.

    Args:
    line (str): The line to process.
    capturing (bool): Whether JSON capturing is in progress.
    json_str (str): The current JSON string being captured.

    Returns:
    tuple[bool, str, dict]: Updated capturing status, JSON string, and parsed data if available.
    """
    if Constants.JOB_MESSAGE_PATTERN.search(line):
        logging.debug("Recognized job message pattern, starting to capture.")
        capturing = True
    elif not capturing:
        match = Constants.ACTION_MESSAGE_PATTERN.search(line)
        if match:
            logging.debug("Recognized pattern, starting to capture JSON.")
            json_str = '{'
            capturing = True
    elif capturing and line.strip().endswith("}."):
        logging.debug("Recognized end of JSON, stopping capture.")
        json_str += '}'
        try:
            data = parse_json(json_str)
            return False, '', data
        except json.JSONDecodeError:
            logging.error("Failed to parse JSON.")
            return False, '', None
    elif line.strip().startswith(Constants.ACCESS_TOKEN_PATTERN):
        logging.debug("Skipping AccessToken")
        return capturing, json_str, None
    elif capturing and line.startswith("["):
        try:
            data = parse_json(json_str)
            return False, '', data
        except json.JSONDecodeError:
            logging.error("Failed to parse JSON.")
            return False, '', None
    elif capturing:
        json_str += line.strip()

    return capturing, json_str, None

def extract_checkout_actions(file_path: str) -> list[dict]:
    """
    Extracts checkout actions from a log file.

    Args:
    file_path (str): The path to the log file.

    Returns:
    list[dict]: A list of checkout action dictionaries.
    """
    lines = read_file(file_path)
    if not lines:
        logging.warning("No lines found in the file.")
        return []

    checkout_actions = []
    capturing = False
    json_str = ''

    for line in lines:
        capturing, json_str, data = process_line(line, capturing, json_str)
        if data:
            checkout_actions.append(data)

    return checkout_actions

def is_jobId(item: dict) -> bool:
    """
    Checks if the item is a job ID.

    Args:
    item (dict): The item to check.

    Returns:
    bool: True if the item is a job ID, False otherwise.
    """
    return item.get("k") == "run_id"

def is_checkout_action(item: dict) -> bool:
    """
    Checks if the item is a checkout action.

    Args:
    item (dict): The item to check.

    Returns:
    bool: True if the item is a checkout action, False otherwise.
    """    
    return item.get("action") == "actions/checkout"

def is_step(item: dict, stepId: str) -> bool:
    """
    Checks if the item is a step with the given step ID.

    Args:
    item (dict): The item to check.
    stepId (str): The step ID to match.

    Returns:
    bool: True if the item is a step with the given step ID, False otherwise.
    """
    return item.get("id") == stepId

def extract_lit_items(data: dict) -> list[tuple[str, str]]:
    """
    Extracts a list of items with 'lit' of the key and 'lit' of the value.

    Args:
    data (dict): The JSON data.

    Returns:
    list: A list of tuples containing 'lit' of the key and 'lit' of the value.
    """
    items = []
    if 'map' in data:
        for item in data['map']:
            key_lit = item['key'].get('lit')
            value_lit = item['value'].get('lit')
            if key_lit and value_lit:
                items.append((key_lit, value_lit))
    return items

def track_action(action: CheckoutStepDetails) -> None:
    """
    Tracks the checkout action as a telemetry event.

    Args:
    action (CheckoutStepDetails): The checkout action to track.
    """
    tc = TelemetryClient(TELEMETRY_KEY)
    tc.track_event(
        f"{action.id}",
        {
            'startTime': action.startTime,
            'finishTime': action.finishTime,
            'duration': action.duration,
            'repository': action.repository,
            'parameters': action.parameters
        }
    )
    logging.debug(f"Tracking event for {action.id}")
    tc.flush()

def process_actions(actions: list[CheckoutStepDetails]) -> None:
    """
    Processes a list of checkout actions.

    Args:
    actions (list[CheckoutStepDetails]): The list of checkout actions to process.
    """
    jobData = actions[0]
    run_id = extract_run_id(jobData)
    mainRepository = extract_main_repository(jobData)
    logging.info(f"Run ID: {run_id}")
    metrics = []
    for action in list(filter(is_checkout_action, actions[1:])):
        process_single_action(action, jobData, mainRepository, metrics)

def extract_run_id(jobData: dict) -> str:
    """
    Extracts the run ID from the job data.

    Args:
        jobData (dict): Dictionary containing job data.

    Returns:
        str: string containing the run id.
    """
    return list(filter(is_jobId, jobData['contextData']['github']['d']))[0]['v']

def extract_main_repository(jobData: dict) -> str:
    """
    Extract the main repository from the job data.

    Args:
        jobData (dict): Dictionary containing job data.

    Returns:
        str: Name and organization of the main repository.
    """
    return list(filter(lambda x: x.get("k") == "repository", jobData['contextData']['github']['d']))[0]['v']

def process_single_action(action: dict, jobData: dict, main_repository: str, metrics: list) -> None:
    """
    Processes a single action from a job, extracts relevant details, and logs the information.

    Args:
        action (dict): The action dictionary containing details about the step.
        jobData (dict): The job data dictionary containing steps and their details.
        main_repository (str): The main repository URL or identifier.
        metrics (list): A list to append the processed metrics for the action.
    """
    logging.info(f"Processing {action['stepId']}")
    t = list(filter(lambda x: x.get("id") == action['stepId'], jobData['steps']))
    if t[0].get('inputs') is not None:
        repo_key = list(filter(lambda x: x.get('key')['lit'] == 'repository', t[0]['inputs']['map']))
        parameters = extract_lit_items(t[0].get('inputs'))
        repo = repo_key[0].get('value')['lit']
    else:
        repo = main_repository
        parameters = []
    logging.debug(f"Action {t[0]['name']} checks out {repo}")
    detail = CheckoutStepDetails(action['stepId'], action['startTime'], action['finishTime'], repo, parameters)
    logging.info(detail)
    metrics.append({'stepId': action['stepId'], 'startTime': action['startTime'], 'finishTime': action['finishTime'], 'repository': repo, 'parameters': parameters})
    track_action(detail)

def parse_json(json_str: str) -> dict:
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        logging.error("Failed to parse JSON.")
        return None

def main() -> None:
    """
    Main function to process log files and extract checkout actions.
    """
    logging.basicConfig(level=logging.INFO)

    log_files = [file for file in os.listdir(WORKSPACE_DIAGNOSTICS_DIR) if file.startswith(Constants.WORKER_LOG_FILE_PATTERN)]
    if log_files:
        most_recent_file = max(log_files, key=lambda f: os.path.getmtime(os.path.join(WORKSPACE_DIAGNOSTICS_DIR, f)))
        file_path = os.path.join(WORKSPACE_DIAGNOSTICS_DIR, most_recent_file)
        logging.info(f"Processing file: {file_path}")
        actions = extract_checkout_actions(file_path)
        logging.info(f"Actions: {actions}")
        process_actions(actions)
    else:
        logging.warning("No log files found matching the pattern. Looking at directory {WORKSPACE_DIAG}")

if __name__ == "__main__":
    main()
