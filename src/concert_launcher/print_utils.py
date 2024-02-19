import functools
import textwrap

class ProgressReporter:

    # recursive function call counter
    call_count = 0

    @classmethod
    def count_calls(cls, fn):
        """
        Decorator that counts the number of recursive function calls.
        This is meant to be applied to the install function
        """
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            cls.call_count += 1
            ret = await fn(*args, **kwargs)
            cls.call_count -= 1
            return ret
    
        return wrapper

    @classmethod
    def print(cls, pkg, level, text, **kwargs):
        indent = '..' * level
        fmt_text = f'[{pkg}] {text}'
        fmt_text = textwrap.indent(text=fmt_text, prefix=indent)
        print(fmt_text, **kwargs)

    
    @classmethod
    def get_print_fn(cls, pkg, level):
        return functools.partial(cls.print, pkg, level)