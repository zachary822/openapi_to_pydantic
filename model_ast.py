import ast
from pydantic import BaseModel
from enum import Enum
import typing


class A(BaseModel):
    """description
    aoeu
    aoeuoe"""

    a: list[int]
    b: "B"
    c: typing.Union[int, str]
    d: typing.Any
    e: bool = False


class B(str, Enum):
    a = "a"
    b = "b"


A.update_forward_refs()

if __name__ == "__main__":
    with open(__file__) as f:
        print(ast.dump(ast.parse(f.read()), indent=4))
