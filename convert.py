#!/usr/bin/env python3

import json
from datetime import datetime
import sys

print("This tool converts CycloneDX Tool Center v1.0 format (YAML) to v2.0 format (JSON).")
response = input("Press [Enter] to continue or type 'x' to exit: ").strip().lower()

if response == 'x':
    print("Exiting.")
    sys.exit(0)

# ------------------------------------------------------------------------------
# Hardcoded file paths
# ------------------------------------------------------------------------------
YAML_FILE = "tools.yaml"
JSON_FILE = "tools.json"

# ------------------------------------------------------------------------------
# Configuration: if True, always include empty arrays in the JSON output;
# if False, omit those properties when they would be empty.
# ------------------------------------------------------------------------------
INCLUDE_EMPTY_ARRAYS = True

# ------------------------------------------------------------------------------
# Mapping from your recognized category -> (schema property, enum value)
# ------------------------------------------------------------------------------
CATEGORY_MAPPINGS = {
    "opensource":        ("availability", "OPEN_SOURCE"),
    "proprietary":       ("availability", "SUBSCRIPTION"),
    "analysis":          ("functions",     "ANALYSIS"),
    "transform":         ("functions",     "TRANSFORM"),
    "signing-notary":    ("functions",     "SIGNING/NOTARY"),
    "build-integration": ("functions",     "PACKAGE_MANAGER_INTEGRATION"),
    "distribute":        ("functions",     "DISTRIBUTE"),
    "author":            ("functions",     "AUTHOR"),
    "library":           ("packaging",    "LIBRARY"),
    "github-action":     ("packaging",    "GITHUB_ACTION"),
    "github-app":        ("packaging",    "GITHUB_APP"),
}


def naive_yaml_parser(lines):
    tools = []
    current = None
    in_categories = False
    in_multiline_description = False
    multiline_desc_lines = []
    indent_level = None

    def set_value(dct, key, val):
        dct[key] = val

    for i, line in enumerate(lines):
        raw_line = line
        line = line.rstrip("\n")
        stripped = line.strip()

        # New tool entry
        if stripped.startswith("- name:"):
            if current:
                # flush multiline desc if pending
                if in_multiline_description:
                    current["description"] = " ".join(multiline_desc_lines).strip()
                    in_multiline_description = False
                tools.append(current)
            current = {"categories": []}
            name_val = line.split("name:", 1)[1].strip()
            set_value(current, "name", name_val)
            in_categories = False
            continue

        if not current:
            continue

        # Inside multiline description block
        if in_multiline_description:
            if line.strip() == "":
                multiline_desc_lines.append("")  # preserve blank lines
                continue
            curr_indent = len(raw_line) - len(raw_line.lstrip())
            if curr_indent > indent_level:
                multiline_desc_lines.append(stripped)
                continue
            else:
                # End of multiline block
                current["description"] = " ".join(multiline_desc_lines).strip()
                in_multiline_description = False
                multiline_desc_lines = []

        if stripped.startswith("publisher:"):
            set_value(current, "publisher", stripped.split("publisher:", 1)[1].strip())
            in_categories = False
        elif stripped.startswith("description: >") or stripped.startswith("description: |"):
            in_multiline_description = True
            multiline_desc_lines = []
            indent_level = len(raw_line) - len(raw_line.lstrip())
        elif stripped.startswith("description:"):
            set_value(current, "description", stripped.split("description:", 1)[1].strip())
            in_categories = False
        elif stripped.startswith("repoUrl:"):
            set_value(current, "repoUrl", stripped.split("repoUrl:", 1)[1].strip())
            in_categories = False
        elif stripped.startswith("websiteUrl:"):
            set_value(current, "websiteUrl", stripped.split("websiteUrl:", 1)[1].strip())
            in_categories = False
        elif stripped.startswith("categories:"):
            in_categories = True
        elif in_categories and stripped.startswith("-"):
            current["categories"].append(stripped.lstrip("-").strip())

    # Final flush
    if current:
        if in_multiline_description:
            current["description"] = " ".join(multiline_desc_lines).strip()
        tools.append(current)

    return tools



def truncate_description(text, max_len=250):
    """Truncate description to `max_len` characters."""
    return text[:max_len] if len(text) > max_len else text


def map_categories_to_schema(item):
    """Convert 'categories' to availability, function, packaging arrays."""
    availability = []
    function = []
    packaging = []

    for cat in item.get("categories", []):
        cat_lower = cat.lower().strip()
        if cat_lower in CATEGORY_MAPPINGS:
            prop, enum_val = CATEGORY_MAPPINGS[cat_lower]
            if prop == "availability" and enum_val not in availability:
                availability.append(enum_val)
            elif prop == "functions" and enum_val not in function:
                function.append(enum_val)
            elif prop == "packaging" and enum_val not in packaging:
                packaging.append(enum_val)
    return availability, function, packaging


def build_tool_schema(item):
    """
    Build a dict conforming to the tool center v2 schema from a single parsed item.
    """
    # Extract fields
    name = item.get("name", "").strip()
    publisher = item.get("publisher", "").strip()
    description = item.get("description", "").strip()
    repo_url = item.get("repoUrl", "").strip()
    website_url = item.get("websiteUrl", "").strip()

    # Truncate description
    description = truncate_description(description)

    # Convert categories
    availability, function, packaging = map_categories_to_schema(item)

    # We'll store the arrays in a dictionary; then optionally remove them if empty
    arrays = {
        "capabilities": [],
        "analysis": [],
        "transform": [],
        "library": [],
        "platform": [],
        "lifecycle": [],
        "supportedStandards": [],
        "cycloneDxVersion": [],
        "supportedLanguages": []
    }

    # Build final object
    tool_obj = {
        "name": name,
        "publisher": publisher,
        "description": description,
        "availability": availability,
        "functions": function,
        "packaging": packaging,
    }

    if repo_url:
        tool_obj["repository_url"] = repo_url
    if website_url:
        tool_obj["website_url"] = website_url

    # Decide whether to keep empty arrays (INCLUDE_EMPTY_ARRAYS)
    if INCLUDE_EMPTY_ARRAYS:
        for key, val in arrays.items():
            tool_obj[key] = val
    else:
        for key, val in arrays.items():
            if val:  # only add if non-empty
                tool_obj[key] = val

    return tool_obj


def main():
    # 1) Read from tools.yaml
    with open(YAML_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 2) Parse the naive YAML
    items = naive_yaml_parser(lines)

    # 3) Build schema objects
    tool_objs = []
    for it in items:
        tool_objs.append(build_tool_schema(it))

    # 4) Current UTC time with HH:MM:SS (and date)
    #    Example: "2023-05-07T13:45:30Z"
    now_utc = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    # 5) Final JSON structure
    result = {
        "$schema": "https://cyclonedx.org/schema/tool-center-v2.schema.json",
        "specVersion": "2.0",
        "last_updated": now_utc,
        "tools": tool_objs
    }

    # 6) Write to tools.json (overwrite if exists)
    with open(JSON_FILE, "w", encoding="utf-8") as out_f:
        json.dump(result, out_f, indent=2, ensure_ascii=False)

    print(f"Converted {len(tool_objs)} tools from {YAML_FILE} → {JSON_FILE}")
    print(f"Set last_updated to: {now_utc}")


if __name__ == "__main__":
    main()
