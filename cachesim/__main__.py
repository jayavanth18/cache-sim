import argparse
import os
import sys

from .config import load_hierarchy
from .trace import read_trace


def main():
    parser = argparse.ArgumentParser(description="Cache hierarchy simulator")
    parser.add_argument("--config", required=True, help="TOML config file")
    parser.add_argument("--trace", required=True, help="trace file")
    parser.add_argument("--verbose", action="store_true",
                        help="print one line per access")
    parser.add_argument("--state", action="store_true",
                        help="also show which cache sets each access changed "
                             "(small configs only)")
    parser.add_argument("--no-color", action="store_true",
                        help="plain text, no green/red")
    args = parser.parse_args()

    color = sys.stdout.isatty() and not args.no_color and "NO_COLOR" not in os.environ
    if color and sys.platform == "win32":
        os.system("")        # switches on ANSI colour support in the Windows console

    h = load_hierarchy(args.config)
    h.run(read_trace(args.trace), verbose=args.verbose, state=args.state, color=color)
    print(h.report())


if __name__ == "__main__":
    main()