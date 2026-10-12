import json
import urllib.error
import urllib.parse
import urllib.request

PYPI_URL = "https://pypi.org/pypi"


def read_requirements(path):
    """Return the dependency lines of a requirements file (blank lines and comments are skipped)."""
    if not isinstance(path, str) or path.strip() == "":
        raise TypeError("The file path must be a non-empty string.")

    try:
        with open(path, "r", encoding="utf-8") as file:
            raw_lines = file.readlines()
    except FileNotFoundError:
        raise FileNotFoundError("Could not find the file '" + path + "'.")

    lines = []
    for raw_line in raw_lines:
        line = raw_line.strip()
        if line == "" or line.startswith("#"):
            continue
        lines.append(line)

    if len(lines) == 0:
        raise ValueError("The file '" + path + "' contains no dependencies.")
    return lines


def parse_line(line):
    """Split a line like 'requests==2.31.0' into ('requests', '2.31.0')."""
    if not isinstance(line, str):
        raise TypeError("A requirement line must be text, not " + type(line).__name__ + ".")

    # Remove inline comments and environment markers such as '; python_version < "3.8"'
    line = line.split("#")[0]
    line = line.split(";")[0]
    line = line.strip()

    if line == "":
        raise ValueError("The requirement line is empty.")
    if "==" not in line:
        raise ValueError("'" + line + "' has no pinned version (expected name==version).")

    parts = line.split("==")
    if len(parts) != 2:
        raise ValueError("'" + line + "' is malformed (expected name==version).")

    name = parts[0].strip()
    version = parts[1].strip()

    if name == "" or version == "":
        raise ValueError("'" + line + "' is missing a package name or a version.")
    return name, version


def fetch_json(url):
    """Download JSON from PyPI. Returns None if PyPI answers 404 (not found)."""
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise ConnectionError("PyPI returned HTTP error " + str(error.code) + " for " + url)
    except urllib.error.URLError as error:
        raise ConnectionError("Could not reach PyPI: " + str(error.reason))

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise ValueError("PyPI sent data that is not valid JSON for " + url)


def check_package(name, version):
    """Ask PyPI about one package and version.

    Returns a dictionary with a 'status' of 'missing_package', 'missing_version' or 'found'.
    For 'found', 'upload_time' holds the upload time of the first file (or None if there are no files).
    """
    safe_name = urllib.parse.quote(name)
    safe_version = urllib.parse.quote(version)

    package_data = fetch_json(PYPI_URL + "/" + safe_name + "/json")
    if package_data is None:
        return {"status": "missing_package"}

    version_data = fetch_json(PYPI_URL + "/" + safe_name + "/" + safe_version + "/json")
    if version_data is None:
        return {"status": "missing_version"}

    upload_time = None
    files = version_data.get("urls", [])
    if len(files) > 0:
        upload_time = files[0].get("upload_time")
    return {"status": "found", "upload_time": upload_time}


def check_requirements(lines):
    """Check every requirement line against PyPI and collect the results."""
    if not isinstance(lines, list):
        raise TypeError("The requirements must be given as a list of lines.")
    if len(lines) == 0:
        raise ValueError("There are no dependencies to check.")

    results = {
        "checked": len(lines),
        "missing_packages": [],
        "missing_versions": [],
        "invalid_lines": [],
        "not_checked": [],
        "oldest": None,
        "oldest_time": None,
    }

    for line in lines:
        try:
            name, version = parse_line(line)
        except (TypeError, ValueError) as error:
            results["invalid_lines"].append(str(error))
            continue

        print("Checking " + name + "==" + version + " ...")
        try:
            answer = check_package(name, version)
        except (ConnectionError, ValueError) as error:
            results["not_checked"].append(name + "==" + version + " (" + str(error) + ")")
            continue

        if answer["status"] == "missing_package":
            results["missing_packages"].append(name + "==" + version)
        elif answer["status"] == "missing_version":
            results["missing_versions"].append(name + "==" + version)
        else:
            upload_time = answer["upload_time"]
            # ISO timestamps like '2015-10-07T16:56:29' can be compared as plain text
            if upload_time is not None:
                if results["oldest_time"] is None or upload_time < results["oldest_time"]:
                    results["oldest_time"] = upload_time
                    results["oldest"] = name + "==" + version + "(" + upload_time[:4] + ")"

    return results


def print_list(title, items):
    print(title + ": " + str(len(items)))
    for item in items:
        print("  - " + item)


def print_report(results):
    print()
    print("Dependencies checked: " + str(results["checked"]))
    print_list("Packages not on PyPI", results["missing_packages"])
    print_list("Versions not on PyPI", results["missing_versions"])
    if results["oldest"] is None:
        print("Oldest pinned release: none found")
    else:
        print("Oldest pinned release: " + results["oldest"])

    # Only shown when something went wrong
    if len(results["invalid_lines"]) > 0:
        print_list("Invalid lines", results["invalid_lines"])
    if len(results["not_checked"]) > 0:
        print_list("Could not be checked", results["not_checked"])


if __name__ == "__main__":
    print("=== Checking requirements.txt ===")
    try:
        requirement_lines = read_requirements("requirements.txt")
        report = check_requirements(requirement_lines)
        print_report(report)
    except (TypeError, ValueError, FileNotFoundError, ConnectionError) as error:
        print("Error: " + str(error))

    print()
    print("=== Error handling demo ===")

    # Missing file
    try:
        read_requirements("does_not_exist.txt")
    except FileNotFoundError as error:
        print("Missing file -> " + str(error))

    # Wrong type for the path
    try:
        read_requirements(123)
    except TypeError as error:
        print("Wrong path type -> " + str(error))

    # Empty data
    try:
        check_requirements([])
    except ValueError as error:
        print("Empty data -> " + str(error))

    # Malformed lines
    bad_lines = ["flask", "==1.0.0", "requests==", "a==1==2", "", 42]
    for bad_line in bad_lines:
        try:
            parse_line(bad_line)
        except (TypeError, ValueError) as error:
            print("Bad line " + repr(bad_line) + " -> " + str(error))
