
import json
import os
import re
import sys
from pathlib import Path

IGNORED_DIRS = {
    ".git", ".venv", "venv", "node_modules",
    "__pycache__", ".idea", ".vscode",
    "dist", "build", "target"
}

LANGUAGE_RULES = {
    "Python": {
        "markers": [
            "requirements.txt", "pyproject.toml",
            "Pipfile", "setup.py", "setup.cfg"
        ],
        "extensions": [".py"]
    },
    "JavaScript": {
        "markers": ["package.json"],
        "extensions": [".js", ".jsx", ".mjs", ".cjs"]
    },
    "TypeScript": {
        "markers": ["tsconfig.json"],
        "extensions": [".ts", ".tsx"]
    },
    "Java": {
        "markers": ["pom.xml", "build.gradle", "build.gradle.kts"],
        "extensions": [".java"]
    },
    "Go": {
        "markers": ["go.mod"],
        "extensions": [".go"]
    },
    "Ruby": {
        "markers": ["Gemfile"],
        "extensions": [".rb"]
    },
    "PHP": {
        "markers": ["composer.json"],
        "extensions": [".php"]
    },
    "C#": {
        "markers": [],
        "extensions": [".cs", ".csproj"]
    }
}

PYTHON_FRAMEWORKS = {
    "Flask": ["flask"],
    "Django": ["django"],
    "FastAPI": ["fastapi"]
}

JAVASCRIPT_FRAMEWORKS = {
    "Express": ["express"],
    "React": ["react"],
    "Next.js": ["next"],
    "Vue": ["vue"],
    "Angular": ["@angular/core"]
}




def read_version_file(path):
    """Read a runtime version file safely."""

    if not path.is_file():
        return None

    value = path.read_text(
        encoding="utf-8",
        errors="ignore"
    ).strip()

    return value if value else None

def normalize_version_declaration(version):
    """Normalize simple wildcard version declarations."""

    normalized = version.strip().lower()

    if normalized.endswith(".x"):
        normalized = normalized[:-2]

    elif normalized.endswith(".*"):
        normalized = normalized[:-2]

    return normalized


def detect_runtime_versions(root):
    """Detect runtime declarations and identify disagreements."""

    runtimes = {}

    # -------------------------
    # Python version detection
    # -------------------------

    python_candidates = []

    python_file_values = [
        (".python-version", root / ".python-version"),
        ("runtime.txt", root / "runtime.txt")
    ]

    for source, path in python_file_values:
        value = read_version_file(path)

        if value:
            # Normalize common runtime.txt format.
            normalized = value.lower().removeprefix("python-")

            python_candidates.append({
                "version": normalized,
                "source": source
            })

    # -------------------------
    # Node.js version detection
    # -------------------------

    node_candidates = []

    node_file_values = [
        (".nvmrc", root / ".nvmrc"),
        (".node-version", root / ".node-version")
    ]

    for source, path in node_file_values:
        value = read_version_file(path)

        if value:
            node_candidates.append({
                "version": value,
                "source": source
            })

    # Read package.json engines.node
    package_file = root / "package.json"

    if package_file.is_file():
        try:
            package_data = json.loads(
                package_file.read_text(encoding="utf-8")
            )

            if not isinstance(package_data, dict):
                raise ValueError("package.json must contain a JSON object")

            engines = package_data.get("engines", {})

            if not isinstance(engines, dict):
                raise ValueError("package.json engines must be an object")

            engine_version = engines.get("node")

            if isinstance(engine_version, str) and engine_version.strip():
                node_candidates.append({
                    "version": engine_version.strip(),
                    "source": "package.json: engines.node"
                })

        except (json.JSONDecodeError, ValueError) as error:
            print(f"Warning: Could not read package.json: {error}")

    # -------------------------
    # Build runtime report
    # -------------------------

    def build_runtime_report(candidates):

        if not candidates:
            return {
                "version": None,
                "source": None,
                "status": "not_specified",
                "declarations": []
            }

        distinct_versions = {
    normalize_version_declaration(item["version"])
    for item in candidates
}

        if len(distinct_versions) > 1:
            status = "needs_review"
            selected_version = None
            selected_source = None

        else:
            status = "declared"
            selected_version = candidates[0]["version"]
            selected_source = candidates[0]["source"]

        return {
            "version": selected_version,
            "source": selected_source,
            "status": status,
            "declarations": candidates
        }

    runtimes["Python"] = build_runtime_report(
        python_candidates
    )

    runtimes["Node.js"] = build_runtime_report(
        node_candidates
    )

    return runtimes




def collect_project_files(root):
    files = []

    for current_dir, directories, filenames in os.walk(root):
        directories[:] = [
            d for d in directories if d not in IGNORED_DIRS
        ]

        for filename in filenames:
            path = Path(current_dir) / filename
            files.append(path.relative_to(root))

    return files


def detect_languages(root):
    files = collect_project_files(root)
    detected = []

    for language, rules in LANGUAGE_RULES.items():
        markers = []
        source_files = []

        for file in files:
            if file.name in rules["markers"]:
                markers.append(str(file))

            if file.suffix.lower() in rules["extensions"]:
                source_files.append(str(file))

        if markers or source_files:
            detected.append({
                "language": language,
                "confidence": "high" if markers else "medium",
                "manifest_evidence": markers,
                "source_evidence": source_files[:10]
            })

    return detected


def detect_python_frameworks(root):
    frameworks = []

    manifests = [
        root / "requirements.txt",
        root / "pyproject.toml",
        root / "Pipfile"
    ]

    content = ""

    for manifest in manifests:
        if manifest.is_file():
            content += manifest.read_text(
                encoding="utf-8", errors="ignore"
            ).lower() + "\n"

    for framework, packages in PYTHON_FRAMEWORKS.items():
        for package in packages:
            pattern = rf"(?<![a-z0-9_-]){re.escape(package)}(?![a-z0-9_-])"

            if re.search(pattern, content):
                frameworks.append({
                    "name": framework,
                    "language": "Python",
                    "evidence": package
                })
                break

    return frameworks


def detect_javascript_frameworks(root):
    frameworks = []
    package_file = root / "package.json"

    if not package_file.is_file():
        return frameworks

    try:
        package_data = json.loads(
            package_file.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError:
        return [{
            "error": "Invalid package.json",
            "file": "package.json"
        }]

    dependencies = {}

    for section in ["dependencies", "devDependencies"]:
        dependencies.update(package_data.get(section, {}))

    for framework, packages in JAVASCRIPT_FRAMEWORKS.items():
        for package in packages:
            if package in dependencies:
                frameworks.append({
                    "name": framework,
                    "language": "JavaScript",
                    "evidence": package
                })
                break

    return frameworks


def detect_frameworks(root):
    return (
        detect_python_frameworks(root)
        + detect_javascript_frameworks(root)
    )


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 scanner.py <repository_path>")
        sys.exit(1)

    repository = Path(sys.argv[1]).resolve()

    if not repository.is_dir():
        print("Error: Repository directory does not exist.")
        sys.exit(1)

    report = {
    "repository": str(repository),
    "detected_languages": detect_languages(repository),
    "detected_frameworks": detect_frameworks(repository),
    "runtime_versions": detect_runtime_versions(repository)
    }
    print(json.dumps(report, indent=4))


if __name__ == "__main__":
    main()
