"""Conservative display guard for newly invented code assignments/indexes.

This is a lexical provenance check, not a semantic fact checker. Preserve raw
model answers in evaluation. Never guess a corrected parameter from ASR.
"""

import re

POLICY = "source_code_v1"
NOTICE = "相应设置（准确代码写法需核对视频画面）"
EXPRESSION = re.compile(
    r"\b[A-Za-z_][A-Za-z0-9_.]*(?:[ \t]*\[[ \t]*-?\d+[ \t]*\]"
    r"|[ \t]*=[ \t]*(?:true|false|True|False|-?\d+(?:\.\d+)?|\"[^\"\n]{0,80}\"|'[^'\n]{0,80}'))"
)
INLINE_CODE = re.compile(r"`([^`\n]+)`")


def guard_source_code(answer: str, sources: list[dict], question: str):
    """Replace unsupported *new* executable-looking expressions with a notice.

    Existing expressions in the question may need discussion, so leave them
    intact; that does not verify their factual correctness. Verbatim source
    presence likewise establishes spelling only, not semantic correctness.
    """
    normalize = lambda s: re.sub(r"\s+", "", s)
    known = [normalize(question), *(normalize(s.get("text", "")) for s in sources)]
    changes = []

    def unsupported(expression):
        value = normalize(expression)
        return not any(value in text for text in known)

    def code_span(match):
        expressions = [m.group() for m in EXPRESSION.finditer(match.group(1))]
        bad = [x for x in expressions if unsupported(x)]
        if bad:
            changes.extend(bad)
            return NOTICE
        return match.group()

    result = INLINE_CODE.sub(code_span, answer)

    def bare_expression(match):
        expression = match.group()
        if unsupported(expression):
            changes.append(expression)
            return NOTICE
        return expression

    result = EXPRESSION.sub(bare_expression, result)
    return result, {"policy": POLICY, "replaced_expressions": list(dict.fromkeys(changes))}


def guard_answer_stream(deltas, sources, question):
    """Buffer a line so code split across network deltas cannot bypass checks."""
    buffer = ""
    for delta in deltas:
        buffer += delta
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            yield guard_source_code(line + "\n", sources, question)[0]
    if buffer:
        yield guard_source_code(buffer, sources, question)[0]
