"""Strict scalar validation without native or DTCC dependencies."""
import math
from collections.abc import Mapping
from numbers import Integral,Real
import numpy as np


def versioned_mapping(payload, name, *, schema_name=None):
    """Copy a version-1 specification without accepting bool/float versions."""
    if not isinstance(payload, Mapping):
        raise ValueError(f"{name} must be a versioned mapping")
    fields = dict(payload)
    version = fields.pop("schema_version", None)
    if type(version) is not int or version != 1:
        raise ValueError(f"Unsupported {schema_name or name} schema_version; expected 1")
    return fields


def real(value,name,*,positive=False,nonnegative=False,float32=False) -> float:
    """Return a finite real scalar; optional narrowing checks do not round it."""
    if isinstance(value,(bool,np.bool_)) or not isinstance(value,Real):
        raise ValueError(f"{name} must be a finite real number")
    try:
        result=float(value)
    except (ValueError,OverflowError) as error:
        raise ValueError(f"{name} must be a finite real number") from error
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if positive and result<=0:
        raise ValueError(f"{name} must be positive")
    if nonnegative and result<0:
        raise ValueError(f"{name} must be nonnegative")
    if float32:
        with np.errstate(over="ignore",under="ignore",invalid="ignore"):
            narrowed=np.float32(result)
        if not np.isfinite(narrowed) or positive and narrowed<=0:
            raise ValueError(f"{name} must be {'positive and ' if positive else ''}finite in float32")
    return result


def integer(value,name,*,minimum=1,maximum=np.iinfo(np.int32).max) -> int:
    """Return an integer scalar in inclusive bounds; reject booleans/coercion."""
    if isinstance(value,(bool,np.bool_)) or not isinstance(value,Integral) or not minimum<=value<=maximum:
        raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return int(value)
