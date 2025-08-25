import re


_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def _norm_tokens(s: str):
    # lowercase; drop quotes spacing differences by keeping punctuation as tokens
    return [t.lower() for t in _TOKEN_RE.findall(s)]


def _orig_tokens(s: str):
    return _TOKEN_RE.findall(s)


def _detok(tokens):
    # naive detokenizer that handles spacing around punctuation decently
    out = []
    for i, t in enumerate(tokens):
        if i == 0:
            out.append(t)
            continue
        if t in ".,!?:;)]}":
            out[-1] = out[-1] + t
        elif out[-1] in "([{":
            out[-1] = out[-1] + t
        else:
            out.append(" " + t)
    return "".join(out)


def merge_segment(merged_tokens, new_text, *, max_overlap_tokens=10):
    """
    merged_tokens: list[str] (original-case tokens accumulated so far)
    new_text: str (current segment transcript)
    returns: merged_tokens updated IN-PLACE and the merged string
    """
    new_tok = _orig_tokens(new_text)
    if not merged_tokens:
        merged_tokens.extend(new_tok)
        return _detok(merged_tokens)

    # find best overlap between suffix(merged) and (possibly shifted) prefix(new)
    prev_norm = _norm_tokens(_detok(merged_tokens))
    new_norm = _norm_tokens(new_text)
    K = min(max_overlap_tokens, len(prev_norm), len(new_norm))
    best_drop = 0
    # allow a small shift at the start of new (e.g., leading 'the', 'a')
    SHIFT_MAX = 3
    for k in range(K, 0, -1):
        max_shift = min(SHIFT_MAX, max(0, len(new_norm) - k))
        for shift in range(0, max_shift + 1):
            if prev_norm[-k:] == new_norm[shift:shift + k]:
                best_drop = shift + k
                break
        if best_drop:
            break

    # drop the overlapped prefix from new segment
    add_tok = new_tok[best_drop:]
    # also kill trivial 1–2 token repeats at the join (e.g., "the the", "it it")
    if add_tok and merged_tokens:
        if len(add_tok) >= 1:
            prev_last = _norm_tokens(merged_tokens[-1])[:1]
            add_first = _norm_tokens(add_tok[0])[:1]
            if prev_last and prev_last == add_first:
                add_tok = add_tok[1:]
        if len(add_tok) >= 2 and len(merged_tokens) >= 2:
            if _norm_tokens(" ".join(merged_tokens[-2:])) == _norm_tokens(" ".join(add_tok[:2])):
                add_tok = add_tok[2:]

    merged_tokens.extend(add_tok)
    return _detok(merged_tokens)


