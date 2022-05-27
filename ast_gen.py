import argparse
import ast
import json
import mimetypes
import re
from functools import partial, reduce
from itertools import starmap

import black
import isort.api
import isort.profiles
import yaml
from autoflake import fix_code

mimetypes.add_type("application/yaml", ".yml")
mimetypes.add_type("application/yaml", ".yaml")


REF = re.compile(r"^#/components/schemas/(.+)$")


def has_ref(config: dict) -> bool:
    match config:
        case {"$ref": _}:
            return True
        case {"type": "array", "items": items}:
            return has_ref(items)
        case {"anyOf": items}:
            return any(map(has_ref, items))
        case _:
            return False


def get_type_annotation(config):
    match config:
        case {"type": "integer"}:
            return ast.Name(id="int", ctx=ast.Store())
        case {"type": "string", "format": "date-time"}:
            return ast.Name(id="datetime", ctx=ast.Store())
        case {"type": "string"}:
            return ast.Name(id="str", ctx=ast.Store())
        case {"$ref": ref} if ref.startswith("#/components/schemas/"):
            return ast.Constant(value=REF.match(ref).group(1))
        case {"type": "array", "items": arr_conf}:
            return ast.Subscript(
                value=ast.Name(id="list", ctx=ast.Load()),
                slice=get_type_annotation(arr_conf),
                ctx=ast.Load(),
            )
        case {"anyOf": items}:
            return ast.Subscript(
                value=ast.Attribute(
                    value=ast.Name(id="typing", ctx=ast.Load()),
                    attr="Union",
                    ctx=ast.Load(),
                ),
                slice=ast.Tuple(
                    elts=[get_type_annotation(item) for item in items],
                    ctx=ast.Load(),
                ),
                ctx=ast.Load(),
            )
        case {"type": "boolean"}:
            return ast.Name(id="bool", ctx=ast.Load())
        case _:
            return ast.Attribute(
                value=ast.Name(id="typing", ctx=ast.Load()), attr="Any", ctx=ast.Load()
            )


def get_field(name, config):
    match config:
        case {"default": value}:
            return ast.AnnAssign(
                target=ast.Name(id=name, ctx=ast.Store()),
                annotation=get_type_annotation(config),
                value=ast.Constant(value=value),
                simple=1,
            )
        case _:
            return ast.AnnAssign(
                target=ast.Name(id=name, ctx=ast.Store()),
                annotation=get_type_annotation(config),
                simple=1,
            )


def get_enum_bases(enum_type):
    match enum_type:
        case "string":
            return [
                ast.Name(id="str", ctx=ast.Load()),
                ast.Name(id="Enum", ctx=ast.Load()),
            ]
        case "integer":
            return [
                ast.Name(id="int", ctx=ast.Load()),
                ast.Name(id="Enum", ctx=ast.Load()),
            ]
        case _:
            return [
                ast.Name(id="Enum", ctx=ast.Load()),
            ]


def get_enum_body(enum_type, members):
    match enum_type:
        case "integer":
            return [
                ast.Assign(
                    targets=[ast.Name(id=chr(97 + i), ctx=ast.Store())],
                    value=ast.Constant(value=m),
                )
                for i, m in enumerate(members)
            ]
        case _:
            return [
                ast.Assign(
                    targets=[ast.Name(id=m, ctx=ast.Store())],
                    value=ast.Constant(value=m),
                )
                for m in members
            ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("openapi")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    main = ast.Module(
        body=[],
        type_ignores=[],
    )

    module_imports = [
        ast.ImportFrom(module="pydantic", names=[ast.alias(name="BaseModel")], level=0),
        ast.ImportFrom(module="enum", names=[ast.alias(name="Enum")], level=0),
        ast.ImportFrom(module="datetime", names=[ast.alias(name="datetime")], level=0),
        ast.Import(names=[ast.alias(name="typing")]),
    ]

    models: list[ast.ClassDef] = []

    forward_refs = []

    with open(args.openapi) as f:
        filetype, encoding = mimetypes.guess_type(f.name)
        match filetype:
            case "application/json":
                spec = json.load(f)
            case "application/yaml":
                spec = yaml.load(f, Loader=yaml.SafeLoader)
            case t:
                raise ValueError(f"unsupported file type {t}")

    for name, schema in spec["components"]["schemas"].items():
        match schema:
            case {"type": "object", "properties": properties}:
                models.append(
                    ast.ClassDef(
                        name=name,
                        bases=[ast.Name(id="BaseModel", ctx=ast.Load())],
                        keywords=[],
                        body=list(starmap(get_field, properties.items())),
                        decorator_list=[],
                    )
                )
                if any(map(has_ref, properties.values())):
                    forward_refs.append(
                        ast.Expr(
                            value=ast.Call(
                                func=ast.Attribute(
                                    value=ast.Name(id=name, ctx=ast.Load()),
                                    attr="update_forward_refs",
                                    ctx=ast.Load(),
                                ),
                                args=[],
                                keywords=[],
                            )
                        ),
                    )
            case {"type": enum_type, "enum": members}:
                models.append(
                    ast.ClassDef(
                        name=name,
                        bases=get_enum_bases(enum_type),
                        keywords=[],
                        body=get_enum_body(enum_type, members),
                        decorator_list=[],
                    )
                )
            case {"enum": members}:
                models.append(
                    ast.ClassDef(
                        name=name,
                        bases=get_enum_bases(None),
                        keywords=[],
                        body=get_enum_body(None, members),
                        decorator_list=[],
                    )
                )

    main.body.extend(module_imports)
    main.body.extend(models)
    main.body.extend(forward_refs)

    output_ops = [
        ast.fix_missing_locations,
        ast.unparse,
        partial(fix_code, remove_all_unused_imports=True),
        partial(isort.api.sort_code_string, **isort.profiles.black),
        partial(black.format_str, mode=black.Mode()),
    ]

    debug_ops = [
        ast.fix_missing_locations,
        partial(ast.dump, indent=4),
    ]

    code = reduce(
        lambda acc, f: f(acc),
        debug_ops if args.debug else output_ops,
        main,
    )

    print(code)
