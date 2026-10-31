def read_trace(path):
    """
    Read a trace file. Each line is: <type> <hex address>
      0 = data read, 1 = data write, 2 = instruction fetch
    Blank lines and anything after a '#' are ignored.
    Yields (type, address) one access at a time.
    """
    with open(path) as f:
        for line_no, line in enumerate(f, 1):
            line = line.split("#")[0].strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) != 2:
                raise ValueError(f"{path}:{line_no}: expected '<type> <address>'")
            try:
                kind = int(parts[0])
                addr = int(parts[1], 16)
            except ValueError:
                raise ValueError(f"{path}:{line_no}: bad number in '{line}'")
            if kind not in (0, 1, 2):
                raise ValueError(f"{path}:{line_no}: type must be 0, 1 or 2")
            yield kind, addr