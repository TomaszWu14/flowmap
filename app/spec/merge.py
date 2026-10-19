"""Combine a freshly derived spec with the stored one without losing anyone's edits."""

from .schema import SECTIONS, Spec


def merge(current: Spec | None, derived: Spec) -> Spec:
    if current is None:
        return derived.model_copy(deep=True)
    out = current.model_copy(deep=True)
    dismissed = set(current.dismissed)
    for section in SECTIONS:
        fresh = {item.key: item for item in getattr(derived, section) if item.key not in dismissed}
        merged = []
        for item in getattr(current, section):
            if item.source != "rules":
                merged.append(item)  # manual / ai: never touched
            elif item.key in fresh:
                merged.append(fresh.pop(item.key).model_copy(update={"stale": False}))
            else:
                merged.append(item.model_copy(update={"stale": True}))
        merged.extend(fresh[k] for k in fresh if k not in {i.key for i in merged})
        setattr(out, section, merged)
    return out
