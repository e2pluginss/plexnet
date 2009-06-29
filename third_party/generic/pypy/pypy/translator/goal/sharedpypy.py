
import sys
from pypy.translator.c.dlltool import DLLDef
from pypy.config.translationoption import get_combined_translation_config
from pypy.rpython.lltypesystem.rffi import charp2str, CCHARP
from pypy.tool.option import make_objspace
from pypy.interpreter.error import OperationError
from pypy.config.pypyoption import pypy_optiondescription
from pypy.interpreter.pyopcode import prepare_exec
from pypy.translator.goal.ann_override import PyPyAnnotatorPolicy

OVERRIDES = {
    'translation.debug': False,
}

def main(argv):
    config = get_combined_translation_config(pypy_optiondescription,
        overrides=OVERRIDES, translating=True)
    config.objspace.nofaking = True
    config.objspace.compiler = "ast"
    config.translating = True
    print config

    space = make_objspace(config)
    policy = PyPyAnnotatorPolicy(single_space = space)

    def interpret(source):
        source = charp2str(source)
        w_dict = space.newdict()
        try:
            ec = space.getexecutioncontext()
            pycode = ec.compiler.compile(source, 'source', 'exec', 0)
            pycode.exec_code(space, w_dict, w_dict)
        except OperationError, e:
            print "OperationError:"
            print " operror-type: " + e.w_type.getname(space, '?')
            print " operror-value: " + space.str_w(space.str(e.w_value))
            return 1
        return 0

    dll = DLLDef('pypylib', [(interpret, [CCHARP])], policy=policy)
    exe_name = dll.compile()

if __name__ == '__main__':
    main(sys.argv)
