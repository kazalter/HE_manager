import re


def select_targets(remote, known):
    available = {name for name in remote if re.fullmatch(r'[a-z0-9]+(?:_[a-z0-9]+)*', name)}
    known = set(known)
    return sorted(name for name in available if name not in known and not (
        name.endswith('_hx') and name[:-3] in (available | known)))
