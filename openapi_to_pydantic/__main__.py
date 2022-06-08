import argparse
import ast
import json
import mimetypes
import sys
from functools import partial, reduce

import black
import isort.api
import isort.profiles
import yaml
from autoflake import fix_code

from openapi_to_pydantic import openapi_to_pydantic

mimetypes.add_type("application/yaml", ".yml")
mimetypes.add_type("application/yaml", ".yaml")

parser = argparse.ArgumentParser(prog="openapi_to_pydantic")
parser.add_argument("openapi")
parser.add_argument(
    "-o",
    "--output",
    default=sys.stdout,
    type=argparse.FileType("w"),
    required=False,
)
parser.add_argument("--debug", action="store_true")
args = parser.parse_args()

with open(args.openapi) as f:
    filetype, encoding = mimetypes.guess_type(f.name)
    match filetype:
        case "application/json":
            spec = json.load(f)
        case "application/yaml":
            spec = yaml.load(f, Loader=yaml.SafeLoader)
        case t:
            raise ValueError(f"unsupported file type {t}")

main = openapi_to_pydantic(spec)

output_ops = [
    ast.unparse,
    partial(fix_code, remove_all_unused_imports=True),
    partial(isort.api.sort_code_string, **isort.profiles.black),
    partial(black.format_str, mode=black.Mode()),
]

debug_ops = [
    partial(ast.dump, indent=4),
]

code = reduce(
    lambda acc, f: f(acc),
    debug_ops if args.debug else output_ops,
    main,
)

print(code, file=args.output, end="")
