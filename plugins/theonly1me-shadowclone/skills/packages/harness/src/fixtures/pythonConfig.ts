import type { FixtureRepository } from "./materialize";

const config = `import json


def load_config(path):
    with open(path, encoding="utf-8") as handle:
        values = json.load(handle)
    if not isinstance(values, dict):
        raise ValueError("config must be a JSON object")
    return {str(key): str(value) for key, value in values.items()}


def get_value(values, key):
    if key not in values:
        raise KeyError(key)
    return values[key]
`;

const main = `import sys

from configcli.config import get_value, load_config


def main(arguments):
    if len(arguments) != 3 or arguments[0] != "get":
        print("usage: python3 -m configcli get <key> <file>", file=sys.stderr)
        return 2
    print(get_value(load_config(arguments[2]), arguments[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
`;

const existingTests = `import json
import tempfile
import unittest
from pathlib import Path

from configcli.config import get_value, load_config


class ConfigTest(unittest.TestCase):
    def test_reads_a_value_from_the_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"region": "eu"}), encoding="utf-8")
            self.assertEqual(get_value(load_config(path), "region"), "eu")


if __name__ == "__main__":
    unittest.main()
`;

const acceptance = `import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from configcli.config import get_value, load_config


class EnvironmentOverrideTest(unittest.TestCase):
    def write(self, directory, values):
        path = Path(directory) / "config.json"
        path.write_text(json.dumps(values), encoding="utf-8")
        return path

    def test_environment_overrides_the_file(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {"CONFIGCLI_REGION": "us"}):
            self.assertEqual(get_value(load_config(self.write(directory, {"region": "eu"})), "region"), "us")

    def test_environment_supplies_a_missing_key(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {"CONFIGCLI_TIMEOUT": "30"}):
            self.assertEqual(get_value(load_config(self.write(directory, {})), "timeout"), "30")

    def test_unrelated_environment_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {"REGION": "us"}):
            self.assertEqual(get_value(load_config(self.write(directory, {"region": "eu"})), "region"), "eu")


if __name__ == "__main__":
    unittest.main()
`;

export const pythonConfig: FixtureRepository = {
  name: "python-config-cli",
  files: {
    "pyproject.toml":
      '[project]\nname = "configcli"\nversion = "0.1.0"\nrequires-python = ">=3.10"\n',
    "README.md": "# configcli\n\nRead values from a JSON configuration file.\n",
    "configcli/__init__.py": "",
    "configcli/config.py": config,
    "configcli/__main__.py": main,
    "tests/__init__.py": "",
    "tests/test_config.py": existingTests,
  },
  specification:
    "Add environment overrides: an environment variable named CONFIGCLI_<KEY>, with the key upper-cased, overrides the file value for that key and supplies keys the file lacks. Other environment variables are ignored.",
  acceptance: { "tests/test_env_override.py": acceptance },
  acceptanceCommand: "python3 -m unittest tests.test_env_override",
};
