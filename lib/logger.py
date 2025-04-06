import os

class Logger:
    is_debug = os.environ.get('LOG_LEVEL_DEBUG', '0') == '1'
    is_verbose_debug = os.environ.get('LOG_LEVEL_VERBOSE_DEBUG', '0') == '1'

    def __init__(self, name):
        self.name = name

    def debug(self, message):
        if self.is_debug:
            print(f"[{self.name} DEBUG]: {message}")

    def verbose_debug(self, message):
        if self.is_verbose_debug:
            print(f"[{self.name} VERBOSE DEBUG]: {message}")

    def warn(self, message):
        print(f"[{self.name} WARN ]: {message}")

    def error(self, message):
        print(f"[{self.name} ERROR]: {message}")

    def info(self, message):
        print(f"[{self.name} INFO ]: {message}")