#
# BSD 3-Clause License
#
# Copyright (c) 2017-2018, plures
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

"""
Xnd implements a container for mapping all Python values relevant for
scientific computing directly to memory.

xnd supports ragged arrays, categorical types, indexing, slicing, aligned
memory blocks and type inference.

Operations like indexing and slicing return zero-copy typed views on the
data.

Importing PEP-3118 buffers is supported.
"""


# Ensure that libndtypes is loaded and initialized.
from ndtypes import ndt, instantiate, MAX_DIM
from ._xnd import Xnd, XndEllipsis, data_shapes, _typeof
from .contrib.pretty import pretty

__all__ = ['xnd', 'array', 'XndEllipsis', 'typeof']


# ======================================================================
#                              xnd object
# ======================================================================

class xnd(Xnd):
    """General container type for unboxing a wide range of Python values
       to typed memory blocks.

       Operations like indexing and slicing return zero-copy typed views
       on the data.

       Create fixed or ragged arrays:

           >>> xnd([[1,2,3], [4,5,6]])
           xnd([[1, 2, 3], [4, 5, 6]], type="2 * 3 * int64")

           >>> xnd([[1,2,3], [4]])
           xnd([[1, 2, 3], [4]], type="var * var * int64")

       Create a record:

           >>> xnd({'a': "xyz", 'b': [1, 2, 3]})
           xnd({'a': 'xyz', 'b': [1, 2, 3]}, type="{a : string, b : 3 * int64}")

       Create a categorical type:

           >>> xnd(['a', 'b', None, 'a'], levels=['a', 'b', None])
           xnd(['a', 'b', None, 'a'], type="4 * categorical('a', 'b', NA)")

       Create an explicitly typed memory block:

           >>> xnd(100000 * [1], type="100000 * uint8")
          xnd([1, 1, 1, 1, 1, 1, 1, 1, 1, ...], type="100000 * uint8")

       Create an empty (zero initialized) memory block:

           >>> xnd.empty("100000 * uint8")
           xnd([0, 0, 0, 0, 0, 0, 0, 0, 0, ...], type="100000 * uint8")

       Import a memory block from a buffer exporter:

           >>> xnd.from_buffer(b"123")
           xnd([49, 50, 51], type="3 * uint8")
    """

    def __new__(cls, value, *, type=None, dtype=None, levels=None,
                typedef=None, dtypedef=None, device=None):
        if (type, dtype, levels, typedef, dtypedef).count(None) < 2:
            raise TypeError(
                "the 'type', 'dtype', 'levels' and 'typedef' arguments are "
                "mutually exclusive")
        if type is not None:
            if isinstance(type, str):
                type = ndt(type)
        elif dtype is not None:
            type = typeof(value, dtype=dtype)
        elif levels is not None:
            args = ', '.join("'%s'" % l if l is not None else 'NA' for l in levels)
            t = "%d * categorical(%s)" % (len(value), args)
            type = ndt(t)
        elif typedef is not None:
            type = ndt(typedef)
            if type.isabstract():
                dtype = type.hidden_dtype
                t = typeof(value, dtype=dtype)
                type = instantiate(typedef, t)
        elif dtypedef is not None:
            dtype = ndt(dtypedef)
            type = typeof(value, dtype=dtype)
        else:
            type = typeof(value)

        if device is not None:
            name, no = device.split(":")
            no = -1 if no == "managed" else int(no)
            device = (name, no)

        return super().__new__(cls, type=type, value=value, device=device)

    def __repr__(self):
        value = self.short_value(maxshape=10)
        fmt = pretty((value, "@type='%s'@" % self.type), max_width=120)
        fmt = fmt.replace('"@', "")
        fmt = fmt.replace('@"', "")
        fmt = fmt.replace("\n", "\n   ")
        return "xnd%s" % fmt

    def copy_contiguous(self, dtype=None):
        if isinstance(dtype, str):
            dtype = ndt(dtype)
        return super().copy_contiguous(dtype=dtype)

    def reshape(self, *args, order=None):
        return super()._reshape(args, order=order)

    @classmethod
    def empty(cls, type=None, device=None):
        if device is not None:
            name, no = device.split(":")
            no = -1 if no == "managed" else no
            device = (name, int(no))

        return super(xnd, cls).empty(type, device)

    @classmethod
    def unsafe_from_data(cls, obj=None, type=None):
        """Return an xnd object that obtains memory from 'obj' via the
           buffer protocol.  The buffer protocol's type is overridden by
          'type'.  No safety checks are performed, the user is responsible
           for passing a suitable type.
        """
        if isinstance(type, str):
            type = ndt(type)
        return cls._unsafe_from_data(obj, type)

def typeof(v, dtype=None):
    if isinstance(dtype, str):
        dtype = ndt(dtype)
    return _typeof(v, dtype=dtype, shortcut=True)


# ======================================================================
#                              array object
# ======================================================================

class array(xnd):
    """Extended array type that relies on gumath for the array functions."""

    _functions = None
    _cuda = None
    _np = None

    @property
    def shape(self):
        return self.type.shape

    @property
    def strides(self):
        return self.type.strides

    def __repr__(self):
        value = self.short_value(maxshape=10)
        fmt = pretty((value, "@type='%s'@" % self.type), max_width=120)
        fmt = fmt.replace('"@', "")
        fmt = fmt.replace('@"', "")
        fmt = fmt.replace("\n", "\n     ")
        return "array%s" % fmt

    def tolist(self):
        return self.value

    def _get_module(self, *devices):
        if all(d == "cuda:managed" for d in devices):
            if array._cuda is None:
                import gumath.cuda
                array._cuda = gumath.cuda
            return array._cuda
        else:
            if array._functions is None:
                import gumath.functions
                array._functions = gumath.functions
            return array._functions

    def _call_unary(self, name, out=None):
        m = self._get_module(self.device)
        return getattr(m, name)(self, out=out, cls=array)

    def _call_binary(self, name, other, out=None):
        m = self._get_module(self.device, other.device)
        return getattr(m, name)(self, other, out=out, cls=array)

    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs):
        if array._np is None:
            import numpy
            array._np = numpy
        np = array._np

        np_inputs = []
        for v in inputs:
            if not isinstance(v, array):
                raise TypeError(
                    "all inputs must be 'xnd.array', got '%s'" % type(v))
            np_inputs.append(np.array(v, copy=False))

        out = kwargs.pop('out', None)
        if out is not None:
            np_outputs = []
            for v in out:
                if not isinstance(v, array):
                    raise TypeError(
                        "all outputs must be 'xnd.array', got '%s'" % type(v))
                np_outputs.append(np.array(v, copy=False))
            kwargs["out"] = np_outputs

        np_self = np_inputs[0]
        np_res = np_self.__array_ufunc__(ufunc, method, *np_inputs, **kwargs)

        if out is None:
            if isinstance(np_res, tuple):
                return tuple(xnd.from_buffer(v) for v in np_res)
            else:
                return array.from_buffer(np_res)
        else:
            return out

    def __bool__(self):
        raise ValueError("the truth value is ambiguous")

    def __neg__(self):
        return self._call_unary("negative")

    def __pos__(self):
        return self.copy()

    def __abs__(self):
        raise NotImplementedError("abs() is not implemented")

    def __invert__(self):
        return self._call_unary("invert")

    def __complex__(self):
        raise TypeError("complex() is not supported")

    def __int__(self):
        raise TypeError("int() is not supported")

    def __float__(self):
        raise TypeError("float() is not supported")

    def __index__(self):
        raise TypeError("index() is not supported")

    def __round__(self):
        return self._call_unary("round")

    def __trunc__(self):
        return self._call_unary("trunc")

    def __floor__(self):
        return self._call_unary("floor")

    def __ceil__(self):
        return self._call_unary("ceil")

    def __eq__(self, other):
        return self._call_binary("equal", other)

    def __ne__(self, other):
        return self._call_binary("not_equal", other)

    def __lt__(self, other):
        return self._call_binary("less", other)

    def __le__(self, other):
        return self._call_binary("less_equal", other)

    def __ge__(self, other):
        return self._call_binary("greater_equal", other)

    def __gt__(self, other):
        return self._call_binary("greater", other)

    def __add__(self, other):
        return self._call_binary("add", other)

    def __sub__(self, other):
        return self._call_binary("subtract", other)

    def __mul__(self, other):
        return self._call_binary("multiply", other)

    def __matmul__(self, other):
        raise NotImplementedError("matrix multiplication is not implemented")

    def __truediv__(self, other):
        return self._call_binary("divide", other)

    def __floordiv__(self, other):
        return self._call_binary("floor_divide", other)

    def __mod__(self, other):
        return self._call_binary("remainder", other)

    def __divmod__(self, other):
        return self._call_binary("divmod", other)

    def __pow__(self, other):
        raise NotImplementedError("power is not implemented")

    def __lshift__(self, other):
        raise TypeError("the '<<' operator is not supported")

    def __rshift__(self, other):
        raise TypeError("the '>>' operator is not supported")

    def __and__(self, other):
        return self._call_binary("bitwise_and", other)

    def __or__(self, other):
        return self._call_binary("bitwise_or", other)

    def __xor__(self, other):
        return self._call_binary("bitwise_xor", other)

    def __iadd__(self, other):
        return self._call_binary("add", other, out=self)

    def __isub__(self, other):
        return self._call_binary("subtract", other, out=self)

    def __imul__(self, other):
        return self._call_binary("multiply", other, out=self)

    def __imatmul__(self, other):
        raise NotImplementedError("inplace matrix multiplication is not implemented")

    def __itruediv__(self, other):
        return self._call_binary("divide", other, out=self)

    def __ifloordiv__(self, other):
        return self._call_binary("floor_divide", other, out=self)

    def __imod__(self, other):
        return self._call_binary("remainder", other, out=self)

    def __idivmod__(self, other):
        return self._call_binary("divmod", other, out=self)

    def __ipow__(self, other):
        raise NotImplementedError("inplace power is not implemented")

    def __ilshift__(self, other):
        raise TypeError("the inplace '<<' operator is not supported")

    def __irshift__(self, other):
        raise TypeError("the inplace '>>' operator is not supported")

    def __iand__(self, other):
        return self._call_binary("bitwise_and", other, out=self)

    def __ior__(self, other):
        return self._call_binary("bitwise_or", other, out=self)

    def __ixor__(self, other):
        return self._call_binary("bitwise_xor", other, out=self)

    def copy(self, out=None):
        return self._call_unary("copy", out=out)

    def acos(self, out=None):
        return self._call_unary("acos", out=out)

    def acosh(self, out=None):
        return self._call_unary("acosh", out=out)

    def asin(self, out=None):
        return self._call_unary("asin", out=out)

    def asinh(self, out=None):
        return self._call_unary("asinh", out=out)

    def atan(self, out=None):
        return self._call_unary("atan", out=out)

    def atanh(self, out=None):
        return self._call_unary("atanh", out=out)

    def cbrt(self, out=None):
        return self._call_unary("cbrt", out=out)

    def cos(self, out=None):
        return self._call_unary("cos", out=out)

    def cosh(self, out=None):
        return self._call_unary("cosh", out=out)

    def erf(self, out=None):
        return self._call_unary("erf", out=out)

    def erfc(self, out=None):
        return self._call_unary("erfc", out=out)

    def exp(self, out=None):
        return self._call_unary("exp", out=out)

    def exp2(self, out=None):
        return self._call_unary("exp2", out=out)

    def expm1(self, out=None):
        return self._call_unary("expm1", out=out)

    def fabs(self, out=None):
        return self._call_unary("fabs", out=out)

    def lgamma(self, out=None):
        return self._call_unary("lgamma", out=out)

    def log(self, out=None):
        return self._call_unary("log", out=out)

    def log10(self, out=None):
        return self._call_unary("log10", out=out)

    def log1p(self, out=None):
        return self._call_unary("log1p", out=out)

    def log2(self, out=None):
        return self._call_unary("log2", out=out)

    def logb(self, out=None):
        return self._call_unary("logb", out=out)

    def nearbyint(self, out=None):
        return self._call_unary("nearbyint", out=out)

    def sin(self, out=None):
        return self._call_unary("sin", out=out)

    def sinh(self, out=None):
        return self._call_unary("sinh", out=out)

    def sqrt(self, out=None):
        return self._call_unary("sqrt", out=out)

    def tan(self, out=None):
        return self._call_unary("tan", out=out)

    def tanh(self, out=None):
        return self._call_unary("tanh", out=out)

    def tanh(self, out=None):
        return self._call_unary("tgamma", out=out)

    def equaln(self, other, out=None):
        return self._call_binary("equaln", other, out=out)
