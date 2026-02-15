#!/usr/bin/env python3
"""
Convert f-string log calls to lazy %-formatting.

    logger.info(f"Text: {var}")  →  logger.info("Text: %s", var)

Safe to run multiple times (idempotent).
"""

import re
import sys
from pathlib import Path

# Matches:  logger.LEVEL(f"..." or f'...'
_LOG_FSTRING_RE = re.compile(
    r"(\.(?:info|debug|warning|error|critical)\()"  # group 1: .level(
    r'f(["\'])'  # group 2: opening quote
)


# Matches {expression} inside an f-string, handling nested braces/brackets/parens
def _extract_expressions(template: str):
    """Yield (start, end, expression) for each {...} in an f-string body."""
    i = 0
    while i < len(template):
        if template[i] == "{":
            if i + 1 < len(template) and template[i + 1] == "{":
                i += 2  # escaped {{
                continue
            # Find matching }
            depth = 1
            j = i + 1
            while j < len(template) and depth > 0:
                ch = template[j]
                if ch in ("{", "(", "["):
                    depth += 1
                elif ch in ("}", ")", "]"):
                    depth -= 1
                elif ch in ('"', "'"):
                    # skip string literal inside expression
                    quote = ch
                    j += 1
                    while j < len(template) and template[j] != quote:
                        if template[j] == "\\":
                            j += 1
                        j += 1
                j += 1
            yield i, j, template[i + 1 : j - 1]
            i = j
        elif template[i] == "}" and i + 1 < len(template) and template[i + 1] == "}":
            i += 2  # escaped }}
        else:
            i += 1


def convert_line(line: str) -> str:
    """Convert a single line containing an f-string log call."""
    m = _LOG_FSTRING_RE.search(line)
    if not m:
        return line

    prefix = line[: m.start()]  # everything before .level(
    level_call = m.group(1)  # .info( etc.
    quote = m.group(2)  # " or '
    rest = line[m.end() :]  # everything after f"

    # Find the closing quote that ends the f-string
    # Be careful about escaped quotes
    body_end = None
    i = 0
    while i < len(rest):
        if rest[i] == "\\":
            i += 2
            continue
        if rest[i] == quote:
            body_end = i
            break
        i += 1

    if body_end is None:
        return line  # multi-line f-string or parse failure — skip

    body = rest[:body_end]
    suffix = rest[body_end + 1 :]  # after closing quote, e.g., )

    # Extract all {expr} from the body
    expressions = list(_extract_expressions(body))

    if not expressions:
        # No interpolations — just remove the f prefix
        return f"{prefix}{level_call}{quote}{body}{quote}{suffix}"

    # Build the template string with %s placeholders
    new_template = ""
    last = 0
    args = []
    for start, end, expr in expressions:
        new_template += body[last:start]
        new_template += "%s"
        args.append(expr.strip())
        last = end
    new_template += body[last:]

    # Reconstruct
    args_str = ", ".join(args)
    return f"{prefix}{level_call}{quote}{new_template}{quote}, {args_str}{suffix}"


def process_file(filepath: Path, dry_run: bool = False) -> int:
    """Process one file. Returns count of converted lines."""
    text = filepath.read_text()
    lines = text.split("\n")
    count = 0
    new_lines = []

    for line in lines:
        if _LOG_FSTRING_RE.search(line):
            new_line = convert_line(line)
            if new_line != line:
                count += 1
                if dry_run:
                    print(f"  - {line.strip()}")
                    print(f"  + {new_line.strip()}")
            new_lines.append(new_line)
        else:
            new_lines.append(line)

    if count and not dry_run:
        filepath.write_text("\n".join(new_lines))

    return count


def main():
    dry_run = "--dry-run" in sys.argv
    src = Path(__file__).parent.parent / "src"

    total = 0
    for py_file in sorted(src.rglob("*.py")):
        n = process_file(py_file, dry_run=dry_run)
        if n:
            print(f"{py_file.relative_to(src.parent)}: {n} conversions")
            total += n

    print(f"\nTotal: {total} f-string log calls converted")


if __name__ == "__main__":
    main()
