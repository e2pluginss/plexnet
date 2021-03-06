import py
from pypy.rpython.extregistry import ExtRegistryEntry
from pypy.rpython.lltypesystem import lltype, lloperation, rclass, llmemory
from pypy.rpython.annlowlevel import llhelper
from pypy.jit.metainterp.policy import StopAtXPolicy
from pypy.rlib.jit import JitDriver, hint, dont_look_inside
from pypy.rlib.jit import OPTIMIZER_SIMPLE, OPTIMIZER_FULL
from pypy.rlib.rarithmetic import intmask
from pypy.jit.metainterp.test.test_basic import LLJitMixin, OOJitMixin
from pypy.rpython.lltypesystem.rvirtualizable2 import VABLERTIPTR
from pypy.rpython.rclass import FieldListAccessor
from pypy.jit.metainterp.warmspot import get_stats, get_translator
from pypy.jit.metainterp import history, heaptracker
from pypy.jit.metainterp.test.test_optimizefindnode import LLtypeMixin

def promote_virtualizable(*args):
    pass
class Entry(ExtRegistryEntry):
    "Annotation and rtyping of LLOp instances, which are callable."
    _about_ = promote_virtualizable

    def compute_result_annotation(self, *args):
        from pypy.annotation.model import lltype_to_annotation
        return lltype_to_annotation(lltype.Void)

    def specialize_call(self, hop):
        op = self.instance    # the LLOp object that was called
        args_v = [hop.inputarg(hop.args_r[0], 0),
                  hop.inputconst(lltype.Void, hop.args_v[1].value),
                  hop.inputconst(lltype.Void, {})]
        hop.exception_cannot_occur()
        return hop.genop('promote_virtualizable',
                         args_v, resulttype=lltype.Void)

debug_print = lloperation.llop.debug_print

# ____________________________________________________________

class ExplicitVirtualizableTests:

    XY = lltype.GcStruct(
        'XY',
        ('parent', rclass.OBJECT),
        ('vable_base', llmemory.Address),
        ('vable_rti', VABLERTIPTR),
        ('inst_x', lltype.Signed),
        ('inst_node', lltype.Ptr(LLtypeMixin.NODE)),
        hints = {'virtualizable2_accessor': FieldListAccessor()})
    XY._hints['virtualizable2_accessor'].initialize(
        XY, {'inst_x' : "", 'inst_node' : ""})

    xy_vtable = lltype.malloc(rclass.OBJECT_VTABLE, immortal=True)
    heaptracker.set_testing_vtable_for_gcstruct(XY, xy_vtable, 'XY')

    def _freeze_(self):
        return True

    def setup(self):
        xy = lltype.malloc(self.XY)
        xy.vable_rti = lltype.nullptr(VABLERTIPTR.TO)
        xy.parent.typeptr = self.xy_vtable
        return xy

    def test_preexisting_access(self):
        myjitdriver = JitDriver(greens = [], reds = ['n', 'xy'],
                                virtualizables = ['xy'])
        def f(n):
            xy = self.setup()
            xy.inst_x = 10
            while n > 0:
                myjitdriver.can_enter_jit(xy=xy, n=n)
                myjitdriver.jit_merge_point(xy=xy, n=n)
                promote_virtualizable(xy, 'inst_x')
                x = xy.inst_x
                xy.inst_x = x + 1
                n -= 1
            promote_virtualizable(xy, 'inst_x')                
            return xy.inst_x
        res = self.meta_interp(f, [20])
        assert res == 30
        self.check_loops(getfield_gc=0, setfield_gc=0)

    def test_preexisting_access_2(self):
        myjitdriver = JitDriver(greens = [], reds = ['n', 'xy'],
                                virtualizables = ['xy'])
        def f(n):
            xy = self.setup()
            xy.inst_x = 100
            while n > -8:
                myjitdriver.can_enter_jit(xy=xy, n=n)
                myjitdriver.jit_merge_point(xy=xy, n=n)
                if n > 0:
                    promote_virtualizable(xy, 'inst_x')
                    x = xy.inst_x
                    xy.inst_x = x + 1
                else:
                    promote_virtualizable(xy, 'inst_x')
                    x = xy.inst_x
                    xy.inst_x = x + 10
                n -= 1
            promote_virtualizable(xy, 'inst_x')                
            return xy.inst_x
        assert f(5) == 185
        res = self.meta_interp(f, [5])
        assert res == 185
        self.check_loops(getfield_gc=0, setfield_gc=0)

    def test_two_paths_access(self):
        myjitdriver = JitDriver(greens = [], reds = ['n', 'xy'],
                                virtualizables = ['xy'])
        def f(n):
            xy = self.setup()
            xy.inst_x = 100
            while n > 0:
                myjitdriver.can_enter_jit(xy=xy, n=n)
                myjitdriver.jit_merge_point(xy=xy, n=n)
                promote_virtualizable(xy, 'inst_x')
                x = xy.inst_x
                if n <= 10:
                    x += 1000
                promote_virtualizable(xy, 'inst_x')                    
                xy.inst_x = x + 1
                n -= 1
            promote_virtualizable(xy, 'inst_x')                
            return xy.inst_x
        res = self.meta_interp(f, [18])
        assert res == 10118
        self.check_loops(getfield_gc=0, setfield_gc=0)

    def test_synchronize_in_return(self):
        myjitdriver = JitDriver(greens = [], reds = ['n', 'xy'],
                                virtualizables = ['xy'])
        def g(xy, n):
            while n > 0:
                myjitdriver.can_enter_jit(xy=xy, n=n)
                myjitdriver.jit_merge_point(xy=xy, n=n)
                promote_virtualizable(xy, 'inst_x')
                xy.inst_x += 1
                n -= 1
        def f(n):
            xy = self.setup()
            xy.inst_x = 10000
            m = 10
            while m > 0:
                g(xy, n)
                m -= 1
            return xy.inst_x
        res = self.meta_interp(f, [18])
        assert res == 10180
        self.check_loops(getfield_gc=0, setfield_gc=0)

    def test_virtualizable_and_greens(self):
        myjitdriver = JitDriver(greens = ['m'], reds = ['n', 'xy'],
                                virtualizables = ['xy'])
        def g(n):
            xy = self.setup()
            xy.inst_x = 10
            m = 0
            while n > 0:
                myjitdriver.can_enter_jit(xy=xy, n=n, m=m)
                myjitdriver.jit_merge_point(xy=xy, n=n, m=m)
                promote_virtualizable(xy, 'inst_x')
                x = xy.inst_x
                xy.inst_x = x + 1
                m = (m+1) & 3     # the loop gets unrolled 4 times
                n -= 1
            promote_virtualizable(xy, 'inst_x')                
            return xy.inst_x
        def f(n):
            res = 0
            k = 4
            while k > 0:
                res += g(n)
                k -= 1
            return res
        res = self.meta_interp(f, [40])
        assert res == 50 * 4
        self.check_loops(getfield_gc=0, setfield_gc=0)

    def test_double_frame(self):
        myjitdriver = JitDriver(greens = [], reds = ['n', 'xy', 'other'],
                                virtualizables = ['xy'])
        def f(n):
            xy = self.setup()
            xy.inst_x = 10
            other = self.setup()
            other.inst_x = 15
            while n > 0:
                myjitdriver.can_enter_jit(xy=xy, n=n, other=other)
                myjitdriver.jit_merge_point(xy=xy, n=n, other=other)
                promote_virtualizable(other, 'inst_x')
                value = other.inst_x         # getfield_gc
                other.inst_x = value + 1     # setfield_gc
                promote_virtualizable(xy, 'inst_x')
                xy.inst_x = value + 100      # virtualized away
                n -= 1
            promote_virtualizable(xy, 'inst_x')                
            return xy.inst_x
        res = self.meta_interp(f, [20])
        assert res == 134
        self.check_loops(getfield_gc=1, setfield_gc=1)

    def test_external_read_while_tracing(self):
        myjitdriver = JitDriver(greens = [], reds = ['n', 'm', 'xy'],
                                virtualizables = ['xy'])
        class Outer:
            pass
        outer = Outer()
        def ext():
            xy = outer.xy
            promote_virtualizable(xy, 'inst_x')
            return xy.inst_x + 2
        def f(n):
            xy = self.setup()
            xy.inst_x = 10
            outer.xy = xy
            m = 0
            while n > 0:
                myjitdriver.can_enter_jit(xy=xy, n=n, m=m)
                myjitdriver.jit_merge_point(xy=xy, n=n, m=m)
                promote_virtualizable(xy, 'inst_x')
                xy.inst_x = n + 9998     # virtualized away
                m += ext()               # 2x setfield_gc, 2x getfield_gc
                promote_virtualizable(xy, 'inst_x')
                xy.inst_x = 10           # virtualized away
                n -= 1
            return m
        assert f(20) == 10000*20 + (20*21)/2
        res = self.meta_interp(f, [20], policy=StopAtXPolicy(ext))
        assert res == 10000*20 + (20*21)/2
        self.check_loops(call=1, getfield_gc=2, setfield_gc=2)
        # xxx for now a call that forces the virtualizable during tracing
        # is supposed to always force it later too.

    def test_external_write_while_tracing(self):
        myjitdriver = JitDriver(greens = [], reds = ['n', 'm', 'xy'],
                                virtualizables = ['xy'])
        class Outer:
            pass
        outer = Outer()
        def ext():
            xy = outer.xy
            promote_virtualizable(xy, 'inst_x')
            xy.inst_x += 2
        def f(n):
            xy = self.setup()
            xy.inst_x = 10
            outer.xy = xy
            m = 0
            while n > 0:
                myjitdriver.can_enter_jit(xy=xy, n=n, m=m)
                myjitdriver.jit_merge_point(xy=xy, n=n, m=m)
                promote_virtualizable(xy, 'inst_x')
                xy.inst_x = n + 9998     # virtualized away
                ext()                    # 2x setfield_gc, 2x getfield_gc
                promote_virtualizable(xy, 'inst_x')
                m += xy.inst_x           # virtualized away
                n -= 1
            return m
        res = self.meta_interp(f, [20], policy=StopAtXPolicy(ext))
        assert res == f(20)
        self.check_loops(call=1, getfield_gc=2, setfield_gc=2)
        # xxx for now a call that forces the virtualizable during tracing
        # is supposed to always force it later too.

    # ------------------------------

    XY2 = lltype.GcStruct(
        'XY2',
        ('parent', rclass.OBJECT),
        ('vable_base', llmemory.Address),
        ('vable_rti', VABLERTIPTR),
        ('inst_x', lltype.Signed),
        ('inst_l1', lltype.Ptr(lltype.GcArray(lltype.Signed))),
        ('inst_l2', lltype.Ptr(lltype.GcArray(lltype.Signed))),
        hints = {'virtualizable2_accessor': FieldListAccessor()})
    XY2._hints['virtualizable2_accessor'].initialize(
        XY2, {'inst_x' : "", 'inst_l1' : "[*]", 'inst_l2' : "[*]"})

    xy2_vtable = lltype.malloc(rclass.OBJECT_VTABLE, immortal=True)
    heaptracker.set_testing_vtable_for_gcstruct(XY2, xy2_vtable, 'XY2')

    def setup2(self):
        xy2 = lltype.malloc(self.XY2)
        xy2.vable_rti = lltype.nullptr(VABLERTIPTR.TO)
        xy2.parent.typeptr = self.xy2_vtable
        return xy2

    def test_access_list_fields(self):
        myjitdriver = JitDriver(greens = [], reds = ['n', 'xy2'],
                                virtualizables = ['xy2'])
        ARRAY = lltype.GcArray(lltype.Signed)
        def f(n):
            xy2 = self.setup2()
            xy2.inst_x = 100
            xy2.inst_l1 = lltype.malloc(ARRAY, 3)
            xy2.inst_l1[0] = -9999999
            xy2.inst_l1[1] = -9999999
            xy2.inst_l1[2] = 3001
            xy2.inst_l2 = lltype.malloc(ARRAY, 2)
            xy2.inst_l2[0] = 80
            xy2.inst_l2[1] = -9999999
            while n > 0:
                myjitdriver.can_enter_jit(xy2=xy2, n=n)
                myjitdriver.jit_merge_point(xy2=xy2, n=n)
                promote_virtualizable(xy2, 'inst_l1')                
                promote_virtualizable(xy2, 'inst_l2')
                xy2.inst_l1[2] += xy2.inst_l2[0]
                n -= 1
            promote_virtualizable(xy2, 'inst_l1')                
            return xy2.inst_l1[2]
        res = self.meta_interp(f, [16])
        assert res == 3001 + 16 * 80
        self.check_loops(getfield_gc=0, setfield_gc=0,
                         getarrayitem_gc=0, setarrayitem_gc=0)

    def test_synchronize_arrays_in_return(self):
        myjitdriver = JitDriver(greens = [], reds = ['n', 'xy2'],
                                virtualizables = ['xy2'])
        ARRAY = lltype.GcArray(lltype.Signed)
        def g(xy2, n):
            while n > 0:
                myjitdriver.can_enter_jit(xy2=xy2, n=n)
                myjitdriver.jit_merge_point(xy2=xy2, n=n)
                promote_virtualizable(xy2, 'inst_x')
                promote_virtualizable(xy2, 'inst_l2')
                xy2.inst_l2[0] += xy2.inst_x
                n -= 1
        def f(n):
            xy2 = self.setup2()
            xy2.inst_x = 2
            xy2.inst_l1 = lltype.malloc(ARRAY, 2)
            xy2.inst_l1[0] = 1941309
            xy2.inst_l1[1] = 2941309
            xy2.inst_l2 = lltype.malloc(ARRAY, 1)
            xy2.inst_l2[0] = 10000
            m = 10
            while m > 0:
                g(xy2, n)
                m -= 1
            return xy2.inst_l2[0]
        assert f(18) == 10360
        res = self.meta_interp(f, [18])
        assert res == 10360
        self.check_loops(getfield_gc=0, setfield_gc=0,
                         getarrayitem_gc=0)

    def test_array_length(self):
        myjitdriver = JitDriver(greens = [], reds = ['n', 'xy2'],
                                virtualizables = ['xy2'])
        ARRAY = lltype.GcArray(lltype.Signed)
        def g(xy2, n):
            while n > 0:
                myjitdriver.can_enter_jit(xy2=xy2, n=n)
                myjitdriver.jit_merge_point(xy2=xy2, n=n)
                promote_virtualizable(xy2, 'inst_l1')
                promote_virtualizable(xy2, 'inst_l2')                
                xy2.inst_l1[1] += len(xy2.inst_l2)
                n -= 1
        def f(n):
            xy2 = self.setup2()
            xy2.inst_x = 2
            xy2.inst_l1 = lltype.malloc(ARRAY, 2)
            xy2.inst_l1[0] = 1941309
            xy2.inst_l1[1] = 2941309
            xy2.inst_l2 = lltype.malloc(ARRAY, 1)
            xy2.inst_l2[0] = 10000
            g(xy2, n)
            return xy2.inst_l1[1]
        res = self.meta_interp(f, [18])
        assert res == 2941309 + 18
        self.check_loops(getfield_gc=0, setfield_gc=0,
                         getarrayitem_gc=0, arraylen_gc=0)

    def test_residual_function(self):
        myjitdriver = JitDriver(greens = [], reds = ['n', 'xy2'],
                                virtualizables = ['xy2'])
        ARRAY = lltype.GcArray(lltype.Signed)
        #
        @dont_look_inside
        def h(xy2):
            # this function is marked for residual calls because
            # it does something with a virtualizable's array that is not
            # just accessing an item
            return xy2.inst_l2
        #
        def g(xy2, n):
            while n > 0:
                myjitdriver.can_enter_jit(xy2=xy2, n=n)
                myjitdriver.jit_merge_point(xy2=xy2, n=n)
                promote_virtualizable(xy2, 'inst_l1')
                xy2.inst_l1[1] = xy2.inst_l1[1] + len(h(xy2))
                n -= 1
        def f(n):
            xy2 = self.setup2()
            xy2.inst_x = 2
            xy2.inst_l1 = lltype.malloc(ARRAY, 2)
            xy2.inst_l1[0] = 1941309
            xy2.inst_l1[1] = 2941309
            xy2.inst_l2 = lltype.malloc(ARRAY, 1)
            xy2.inst_l2[0] = 10000
            g(xy2, n)
            return xy2.inst_l1[1]
        res = self.meta_interp(f, [18])
        assert res == 2941309 + 18
        self.check_loops(getfield_gc=0, setfield_gc=0,
                         getarrayitem_gc=0, arraylen_gc=1, call=1)

    def test_double_frame_array(self):
        myjitdriver = JitDriver(greens = [], reds = ['n', 'xy2', 'other'],
                                virtualizables = ['xy2'])
        ARRAY = lltype.GcArray(lltype.Signed)
        def f(n):
            xy2 = self.setup2()
            xy2.inst_x = 10
            xy2.inst_l1 = lltype.malloc(ARRAY, 1)
            xy2.inst_l1[0] = 1982731
            xy2.inst_l2 = lltype.malloc(ARRAY, 1)
            xy2.inst_l2[0] = 10000
            other = self.setup2()
            other.inst_x = 15
            other.inst_l1 = lltype.malloc(ARRAY, 2)
            other.inst_l1[0] = 189182
            other.inst_l1[1] = 58421
            other.inst_l2 = lltype.malloc(ARRAY, 2)
            other.inst_l2[0] = 181
            other.inst_l2[1] = 189
            while n > 0:
                myjitdriver.can_enter_jit(xy2=xy2, n=n, other=other)
                myjitdriver.jit_merge_point(xy2=xy2, n=n, other=other)
                promote_virtualizable(other, 'inst_l2')
                length = len(other.inst_l2)       # getfield_gc/arraylen_gc
                value = other.inst_l2[0]          # getfield_gc/getarrayitem_gc
                other.inst_l2[0] = value + length # getfield_gc/setarrayitem_gc
                promote_virtualizable(xy2, 'inst_l2')
                xy2.inst_l2[0] = value + 100      # virtualized away
                n -= 1
            promote_virtualizable(xy2, 'inst_l2')                
            return xy2.inst_l2[0]
        expected = f(20)
        res = self.meta_interp(f, [20], optimizer=OPTIMIZER_SIMPLE)
        assert res == expected
        self.check_loops(getfield_gc=3, setfield_gc=0,
                         arraylen_gc=1, getarrayitem_gc=1, setarrayitem_gc=1)

    # ------------------------------

    XY2SUB = lltype.GcStruct(
        'XY2SUB',
        ('parent', XY2))

    xy2sub_vtable = lltype.malloc(rclass.OBJECT_VTABLE, immortal=True)
    heaptracker.set_testing_vtable_for_gcstruct(XY2SUB, xy2sub_vtable,
                                                'XY2SUB')

    def setup2sub(self):
        xy2 = lltype.malloc(self.XY2SUB)
        xy2.parent.vable_rti = lltype.nullptr(VABLERTIPTR.TO)
        xy2.parent.parent.typeptr = self.xy2_vtable
        return xy2

    def test_subclass(self):
        myjitdriver = JitDriver(greens = [], reds = ['n', 'xy2'],
                                virtualizables = ['xy2'])
        ARRAY = lltype.GcArray(lltype.Signed)
        def g(xy2, n):
            while n > 0:
                myjitdriver.can_enter_jit(xy2=xy2, n=n)
                myjitdriver.jit_merge_point(xy2=xy2, n=n)
                parent = xy2.parent
                promote_virtualizable(parent, 'inst_x')                
                promote_virtualizable(parent, 'inst_l2')                
                parent.inst_l2[0] += parent.inst_x
                n -= 1
        def f(n):
            xy2 = self.setup2sub()
            xy2.parent.inst_x = 2
            xy2.parent.inst_l1 = lltype.malloc(ARRAY, 2)
            xy2.parent.inst_l1[0] = 1941309
            xy2.parent.inst_l1[1] = 2941309
            xy2.parent.inst_l2 = lltype.malloc(ARRAY, 1)
            xy2.parent.inst_l2[0] = 10000
            m = 10
            while m > 0:
                g(xy2, n)
                m -= 1
            return xy2.parent.inst_l2[0]
        assert f(18) == 10360
        res = self.meta_interp(f, [18])
        assert res == 10360
        self.check_loops(getfield_gc=0, setfield_gc=0,
                         getarrayitem_gc=0)

    # ------------------------------


class ImplicitVirtualizableTests:

    def test_simple_implicit(self):
        myjitdriver = JitDriver(greens = [], reds = ['frame'],
                                virtualizables = ['frame'])

        class Frame(object):
            _virtualizable2_ = ['x', 'y']

            def __init__(self, x, y):
                self.x = x
                self.y = y

        class SomewhereElse:
            pass
        somewhere_else = SomewhereElse()

        def f(n):
            frame = Frame(n, 0)
            somewhere_else.top_frame = frame        # escapes
            while frame.x > 0:
                myjitdriver.can_enter_jit(frame=frame)
                myjitdriver.jit_merge_point(frame=frame)
                frame.y += frame.x
                frame.x -= 1
            return somewhere_else.top_frame.y

        res = self.meta_interp(f, [10])
        assert res == 55
        self.check_loops(getfield_gc=0, setfield_gc=0)


    def test_virtualizable_with_array(self):
        myjitdriver = JitDriver(greens = [], reds = ['n', 'frame', 'x'],
                                virtualizables = ['frame'])

        class Frame(object):
            _virtualizable2_ = ['l[*]', 's']

            def __init__(self, l, s):
                self.l = l
                self.s = s
        
        def f(n, a):
            frame = Frame([a,a+1,a+2,a+3], 0)
            x = 0
            while n > 0:
                myjitdriver.can_enter_jit(frame=frame, n=n, x=x)
                myjitdriver.jit_merge_point(frame=frame, n=n, x=x)
                frame.s = hint(frame.s, promote=True)
                n -= 1
                x += frame.l[frame.s]
                frame.s += 1
                x += frame.l[frame.s]
                x += len(frame.l)
                frame.s -= 1
            return x

        res = self.meta_interp(f, [10, 1], listops=True)
        assert res == f(10, 1)
        self.check_loops(getarrayitem_gc=0)


    def test_subclass_of_virtualizable(self):
        myjitdriver = JitDriver(greens = [], reds = ['frame'],
                                virtualizables = ['frame'])

        class Frame(object):
            _virtualizable2_ = ['x', 'y']

            def __init__(self, x, y):
                self.x = x
                self.y = y

        class SubFrame(Frame):
            pass

        def f(n):
            Frame(0, 0)    # hack: make sure x and y are attached to Frame
            frame = SubFrame(n, 0)
            while frame.x > 0:
                myjitdriver.can_enter_jit(frame=frame)
                myjitdriver.jit_merge_point(frame=frame)
                frame.y += frame.x
                frame.x -= 1
            return frame.y

        res = self.meta_interp(f, [10])
        assert res == 55
        self.check_loops(getfield_gc=0, setfield_gc=0)


    def test_external_pass(self):
        jitdriver = JitDriver(greens = [], reds = ['frame', 'n', 'z'],
                              virtualizables = ['frame'])

        class BaseFrame(object):
            _virtualizable2_ = ['x[*]']

            def __init__(self, x):
                self.x = x

        class Frame(BaseFrame):
            pass

        def g(frame):
            return frame.x[1] == 1

        def f(n):
            BaseFrame([])     # hack to force 'x' to be in BaseFrame
            frame = Frame([1,2,3])
            z = 0
            while n > 0:
                jitdriver.can_enter_jit(frame=frame, n=n, z=z)
                jitdriver.jit_merge_point(frame=frame, n=n, z=z)
                z += g(frame)
                n -= 1
            return z

        res = self.meta_interp(f, [10], policy=StopAtXPolicy(g))
        assert res == f(10)


    def test_external_read(self):
        jitdriver = JitDriver(greens = [], reds = ['frame'],
                              virtualizables = ['frame'])
        
        class Frame(object):
            _virtualizable2_ = ['x', 'y']
        class SomewhereElse:
            pass
        somewhere_else = SomewhereElse()

        def g():
            result = somewhere_else.top_frame.y     # external read
            debug_print(lltype.Void, '-+-+-+-+- external read:', result)
            return result

        def f(n):
            frame = Frame()
            frame.x = n
            frame.y = 10
            somewhere_else.top_frame = frame
            while frame.x > 0:
                jitdriver.can_enter_jit(frame=frame)
                jitdriver.jit_merge_point(frame=frame)
                frame.x -= g()
                frame.y += 1
            return frame.x

        res = self.meta_interp(f, [123], policy=StopAtXPolicy(g))
        assert res == f(123)


    def test_external_write(self):
        jitdriver = JitDriver(greens = [], reds = ['frame'],
                              virtualizables = ['frame'])

        class Frame(object):
            _virtualizable2_ = ['x', 'y']
        class SomewhereElse:
            pass
        somewhere_else = SomewhereElse()

        def g():
            result = somewhere_else.top_frame.y + 1
            debug_print(lltype.Void, '-+-+-+-+- external write:', result)
            somewhere_else.top_frame.y = result      # external read/write

        def f(n):
            frame = Frame()
            frame.x = n
            frame.y = 10
            somewhere_else.top_frame = frame
            while frame.x > 0:
                jitdriver.can_enter_jit(frame=frame)
                jitdriver.jit_merge_point(frame=frame)
                g()
                frame.x -= frame.y
            return frame.y

        res = self.meta_interp(f, [240], policy=StopAtXPolicy(g))
        assert res == f(240)

    def test_external_read_sometimes(self):
        py.test.skip("known bug: access the frame in a residual call but"
                     " only sometimes, so that it's not seen during tracing")
        jitdriver = JitDriver(greens = [], reds = ['frame'],
                              virtualizables = ['frame'])
        
        class Frame(object):
            _virtualizable2_ = ['x', 'y']
        class SomewhereElse:
            pass
        somewhere_else = SomewhereElse()

        def g():
            somewhere_else.counter += 1
            if somewhere_else.counter == 70:
                result = somewhere_else.top_frame.y     # external read
                debug_print(lltype.Void, '-+-+-+-+- external read:', result)
                assert result == 79
            else:
                result = 1
            return result

        def f(n):
            frame = Frame()
            frame.x = n
            frame.y = 10
            somewhere_else.counter = 0
            somewhere_else.top_frame = frame
            while frame.x > 0:
                jitdriver.can_enter_jit(frame=frame)
                jitdriver.jit_merge_point(frame=frame)
                frame.x -= g()
                frame.y += 1
            return frame.x

        res = self.meta_interp(f, [123], policy=StopAtXPolicy(g))
        assert res == f(123)

    def test_promote_index_in_virtualizable_list(self):
        jitdriver = JitDriver(greens = [], reds = ['frame', 'n'],
                              virtualizables = ['frame'])
        class Frame(object):
            _virtualizable2_ = ['stackpos', 'stack[*]']

        def f(n):
            frame = Frame()
            frame.stack = [42, 0, 0]
            frame.stackpos = 1
            while n > 0:
                jitdriver.can_enter_jit(frame=frame, n=n)
                jitdriver.jit_merge_point(frame=frame, n=n)
                popped = frame.stack[frame.stackpos]
                frame.stackpos -= 1
                to_push = intmask(popped * 3)
                frame.stack[frame.stackpos] = to_push
                frame.stackpos += 1
                n -= 1
            return frame.stack[0]

        res = self.meta_interp(f, [70], listops=True)
        assert res == intmask(42 ** 70)
        self.check_loops(int_add=0,
                         int_sub=1)   # for 'n -= 1' only

    def test_simple_access_directly(self):
        myjitdriver = JitDriver(greens = [], reds = ['frame'],
                                virtualizables = ['frame'])

        class Frame(object):
            _virtualizable2_ = ['x', 'y']

            def __init__(self, x, y):
                self = hint(self, access_directly=True)
                self.x = x
                self.y = y

        class SomewhereElse:
            pass
        somewhere_else = SomewhereElse()

        def f(n):
            frame = Frame(n, 0)
            somewhere_else.top_frame = frame        # escapes
            frame = hint(frame, access_directly=True)
            while frame.x > 0:
                myjitdriver.can_enter_jit(frame=frame)
                myjitdriver.jit_merge_point(frame=frame)
                frame.y += frame.x
                frame.x -= 1
            return somewhere_else.top_frame.y

        res = self.meta_interp(f, [10])
        assert res == 55
        self.check_loops(getfield_gc=0, setfield_gc=0)

        from pypy.jit.backend.test.support import BaseCompiledMixin
        if isinstance(self, BaseCompiledMixin):
            return

        t = get_translator()
        f_graph, portal_graph = [graph for graph in t.graphs
                                       if getattr(graph, 'func', None) is f]
        init_graph = t._graphof(Frame.__init__.im_func)

        deref = t.rtyper.type_system_deref

        def direct_calls(graph):
            return [deref(op.args[0].value)._callable.func_name
                    for block, op in graph.iterblockops()
                        if op.opname == 'direct_call']

        assert direct_calls(f_graph) == ['__init__', 'force_if_necessary', 'll_portal_runner']
        assert direct_calls(portal_graph) == ['force_if_necessary', 'maybe_enter_jit']

        assert direct_calls(init_graph) == []

    def test_virtual_child_frame(self):
        myjitdriver = JitDriver(greens = [], reds = ['frame'],
                                virtualizables = ['frame'])

        class Frame(object):
            _virtualizable2_ = ['x', 'y']

            def __init__(self, x, y):
                self = hint(self, access_directly=True)
                self.x = x
                self.y = y

        class SomewhereElse:
            pass
        somewhere_else = SomewhereElse()

        def f(n):
            frame = Frame(n, 0)
            somewhere_else.top_frame = frame        # escapes
            frame = hint(frame, access_directly=True)
            while frame.x > 0:
                myjitdriver.can_enter_jit(frame=frame)
                myjitdriver.jit_merge_point(frame=frame)
                child_frame = Frame(frame.x, 1)
                frame.y += child_frame.x
                frame.x -= 1
            return somewhere_else.top_frame.y

        res = self.meta_interp(f, [10])
        assert res == 55
        self.check_loops(new_with_vtable=0)

    def test_check_for_nonstandardness_only_once(self):                                          
         myjitdriver = JitDriver(greens = [], reds = ['frame'],                                   
                                 virtualizables = ['frame'])                                      
                                                                                                  
         class Frame(object):                                                                     
             _virtualizable2_ = ['x', 'y', 'z']                                                   
                                                                                                  
             def __init__(self, x, y, z=1):                                                       
                 self = hint(self, access_directly=True)                                          
                 self.x = x                                                                       
                 self.y = y                                                                       
                 self.z = z                                                                       
                                                                                                  
         class SomewhereElse:                                                                     
             pass                                                                                 
         somewhere_else = SomewhereElse()                                                         
                                                                                                  
         def f(n):                                                                                
             frame = Frame(n, 0)                                                                  
             somewhere_else.top_frame = frame        # escapes                                    
             frame = hint(frame, access_directly=True)
             while frame.x > 0:
                 myjitdriver.can_enter_jit(frame=frame)
                 myjitdriver.jit_merge_point(frame=frame)
                 top_frame = somewhere_else.top_frame
                 child_frame = Frame(frame.x, top_frame.z, 17)
                 frame.y += child_frame.x
                 frame.x -= top_frame.z
             return somewhere_else.top_frame.y
 
         res = self.meta_interp(f, [10])
         assert res == 55
         self.check_loops(new_with_vtable=0, oois=1)

    def test_virtual_child_frame_with_arrays(self):
        myjitdriver = JitDriver(greens = [], reds = ['frame'],
                                virtualizables = ['frame'])

        class Frame(object):
            _virtualizable2_ = ['x[*]']

            def __init__(self, x, y):
                self = hint(self, access_directly=True,
                                  fresh_virtualizable=True)
                self.x = [x, y]

        class SomewhereElse:
            pass
        somewhere_else = SomewhereElse()

        def f(n):
            frame = Frame(n, 0)
            somewhere_else.top_frame = frame        # escapes
            frame = hint(frame, access_directly=True)
            while frame.x[0] > 0:
                myjitdriver.can_enter_jit(frame=frame)
                myjitdriver.jit_merge_point(frame=frame)
                child_frame = Frame(frame.x[0], 1)
                frame.x[1] += child_frame.x[0]
                frame.x[0] -= 1
            return somewhere_else.top_frame.x[1]

        res = self.meta_interp(f, [10], listops=True)
        assert res == 55
        self.check_loops(new_with_vtable=0)

    def test_blackhole_should_not_pay_attention(self):
        myjitdriver = JitDriver(greens = [], reds = ['frame'],
                                virtualizables = ['frame'])

        class Frame(object):
            _virtualizable2_ = ['x', 'y']

            def __init__(self, x, y):
                self = hint(self, access_directly=True)
                self.x = x
                self.y = y

        class SomewhereElse:
            pass
        somewhere_else = SomewhereElse()

        def g(frame):
            assert frame.x == 2
            assert frame.y == 52
            frame.y += 100

        def f(n):
            frame = Frame(n, 0)
            somewhere_else.top_frame = frame        # escapes
            frame = hint(frame, access_directly=True)
            while frame.x > 0:
                myjitdriver.can_enter_jit(frame=frame)
                myjitdriver.jit_merge_point(frame=frame)
                if frame.x == 2:
                    g(frame)
                frame.y += frame.x
                frame.x -= 1
            return somewhere_else.top_frame.y

        res = self.meta_interp(f, [10])
        assert res == 155
        self.check_loops(getfield_gc=0, setfield_gc=0)

    def test_blackhole_should_synchronize(self):
        myjitdriver = JitDriver(greens = [], reds = ['frame'],
                                virtualizables = ['frame'])

        class Frame(object):
            _virtualizable2_ = ['x', 'y']

            def __init__(self, x, y):
                self.x = x
                self.y = y

        class SomewhereElse:
            pass
        somewhere_else = SomewhereElse()

        def g(frame):
            assert frame.x == 2
            assert frame.y == 52
            frame.y += 100

        def f(n):
            frame = Frame(n, 0)
            somewhere_else.top_frame = frame        # escapes
            while frame.x > 0:
                myjitdriver.can_enter_jit(frame=frame)
                myjitdriver.jit_merge_point(frame=frame)
                if frame.x == 2:
                    g(frame)
                frame.y += frame.x
                frame.x -= 1
            return somewhere_else.top_frame.y

        res = self.meta_interp(f, [10])
        assert res == 155
        self.check_loops(getfield_gc=0, setfield_gc=0)

    def test_blackhole_should_not_reenter(self):
        from pypy.jit.backend.test.support import BaseCompiledMixin
        if isinstance(self, BaseCompiledMixin):
            py.test.skip("purely frontend test")

        myjitdriver = JitDriver(greens = [], reds = ['frame', 'fail'],
                                virtualizables = ['frame'])

        class Frame(object):
            _virtualizable2_ = ['x', 'y']

            def __init__(self, x, y):
                self = hint(self, access_directly=True)
                self.x = x
                self.y = y

        class SomewhereElse:
            pass
        somewhere_else = SomewhereElse()

        def jump_back(frame, fail):
            myjitdriver.can_enter_jit(frame=frame, fail=fail)            

        def f(n, fail):
            frame = Frame(n, 0)
            somewhere_else.top_frame = frame        # escapes
            frame = hint(frame, access_directly=True)
            while frame.x > 0:
                myjitdriver.jit_merge_point(frame=frame, fail=fail)
                frame.x -= 1
                if fail or frame.x > 2:
                    frame.y += frame.x
                jump_back(frame, fail)

            return somewhere_else.top_frame.y

        def main():
            f(10, True)
            f(10, True)
            f(10, True)
            f(10, True)
            return f(10, False)

        einfo = py.test.raises(AssertionError, self.meta_interp, main, [])
        assert einfo.value.args[0] == "reentering same frame via blackhole"

    def test_inlining(self):
        class Frame(object):
            _virtualizable2_ = ['x', 'next']

            def __init__(self, x):
                self = hint(self, access_directly=True)
                self.x = x
                self.next = None

        driver = JitDriver(greens=[], reds=['frame', 'result'],
                           virtualizables=['frame'])

        def interp(caller):
            f = Frame(caller.x)
            caller.next = f
            f = hint(f, access_directly=True)
            result = 0
            while f.x > 0:
                driver.can_enter_jit(frame=f, result=result)
                driver.jit_merge_point(frame=f, result=result)
                f.x -= 1
                result += indirection(f)
            return result
        def indirection(arg):
            return interp(arg)
        def run_interp(n):
            f = hint(Frame(n), access_directly=True)
            return interp(f)

        res = self.meta_interp(run_interp, [4])
        assert res == run_interp(4)

    def test_guard_failure_in_inlined_function(self):
        from pypy.rpython.annlowlevel import hlstr
        class Frame(object):
            _virtualizable2_ = ['n', 'next']

            def __init__(self, n):
                self = hint(self, access_directly=True)
                self.n = n
                self.next = None

        driver = JitDriver(greens=[], reds=['frame', 'result'],
                           virtualizables=['frame'])

        def p(code, pc):
            code = hlstr(code)
            return "%s %d %s" % (code, pc, code[pc])
        def c(code, pc):
            return "l" not in hlstr(code)
        myjitdriver = JitDriver(greens=['code', 'pc'], reds=['frame'],
                                virtualizables=["frame"],
                                get_printable_location=p, can_inline=c)
        def f(code, frame):
            pc = 0
            while pc < len(code):

                myjitdriver.jit_merge_point(frame=frame, code=code, pc=pc)
                op = code[pc]
                if op == "-":
                    frame.n -= 1
                elif op == "c":
                    subframe = Frame(frame.n)
                    frame.next = subframe
                    frame.n = f("---i---", subframe)
                    frame.next = None
                elif op == "i":
                    if frame.n % 5 == 1:
                        return frame.n
                elif op == "l":
                    if frame.n > 0:
                        myjitdriver.can_enter_jit(frame=frame, code=code, pc=0)
                        pc = 0
                        continue
                else:
                    assert 0
                pc += 1
            return frame.n
        def main(n):
            frame = Frame(n)
            return f("c-l", frame)
        print main(100)
        res = self.meta_interp(main, [100], inline=True,
                                            optimizer=OPTIMIZER_FULL)

class TestOOtype(#ExplicitVirtualizableTests,
                 ImplicitVirtualizableTests,
                 OOJitMixin):
    pass

        
class TestLLtype(ExplicitVirtualizableTests,
                 ImplicitVirtualizableTests,
                 LLJitMixin):
    pass
