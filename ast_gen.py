import argparse
import ast
import json
import re
from functools import partial, reduce

import black
import isort.api
import isort.profiles
from autoflake import fix_code

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


def convert_type(config):
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
            return convert_type(arr_conf)
        case {"anyOf": items}:
            return ast.Subscript(
                value=ast.Attribute(
                    value=ast.Name(id="typing", ctx=ast.Load()),
                    attr="Union",
                    ctx=ast.Load(),
                ),
                slice=ast.Tuple(
                    elts=[convert_type(item) for item in items],
                    ctx=ast.Load(),
                ),
                ctx=ast.Load(),
            )
        case _:
            return ast.Attribute(
                value=ast.Name(id="typing", ctx=ast.Load()), attr="Any", ctx=ast.Load()
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("openapi")
    args = parser.parse_args()

    main = ast.Module(
        body=[],
        type_ignores=[],
    )

    module_imports = [
        ast.ImportFrom(module="pydantic", names=[ast.alias(name="BaseModel")], level=0),
        ast.ImportFrom(module="enum", names=[ast.alias(name="Enum")], level=0),
        ast.ImportFrom(module="datetime", names=[ast.alias(name="datetime")], level=0),
        ast.Import(module="typing", names=[], level=0),
    ]

    models: list[ast.ClassDef] = []

    forward_refs = []

    with open(args.openapi) as f:
        spec = json.load(f)

    for name, schema in spec["components"]["schemas"].items():
        match schema:
            case {"type": "object", "properties": properties}:
                models.append(
                    ast.ClassDef(
                        name=name,
                        bases=[ast.Name(id="BaseModel", ctx=ast.Load())],
                        keywords=[],
                        body=[
                            ast.AnnAssign(
                                target=ast.Name(id=name, ctx=ast.Store()),
                                annotation=convert_type(config),
                                simple=1,
                            )
                            for name, config in properties.items()
                        ],
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
            case {"type": "string", "enum": members}:
                models.append(
                    ast.ClassDef(
                        name=name,
                        bases=[
                            ast.Name(id="str", ctx=ast.Load()),
                            ast.Name(id="Enum", ctx=ast.Load()),
                        ],
                        keywords=[],
                        body=[
                            ast.Assign(
                                targets=[ast.Name(id=m, ctx=ast.Store())],
                                value=ast.Constant(value=m),
                            )
                            for m in members
                        ],
                        decorator_list=[],
                    )
                )

    main.body.extend(module_imports)
    main.body.extend(models)
    main.body.extend(forward_refs)

    code = reduce(
        lambda acc, f: f(acc),
        [
            ast.fix_missing_locations,
            ast.unparse,
            partial(fix_code, remove_all_unused_imports=True),
            partial(isort.api.sort_code_string, **isort.profiles.black),
            partial(black.format_str, mode=black.Mode()),
        ],
        main,
    )

    print(code)
