from typing import Literal

ConfigState = Literal[
    "file_not_exists",
    "format_error",
    "low_version",
    "high_version",
    "key_missing",
    "normal",
]

