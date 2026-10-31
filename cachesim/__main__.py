import argparse

from .config import load_hierarchy
from .trace import read_trace


def main():
    parser = argparse.ArgumentParser(description="Cache hierarchy simulator")
    parser.add_argument("--config", required=True, help="TOML config file")
    parser.add_argument("--trace", required=True, help="trace file")
    parser.add_argument("--verbose", action="store_true",
                        help="print one line per access")
    args = parser.parse_args()

    h = load_hierarchy(args.config)
    h.run(read_trace(args.trace), verbose=args.verbose)
    print(h.report())


if __name__ == "__main__":
    main()