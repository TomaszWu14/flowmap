"""Progress page maths (no AI, no database): strengths and weaknesses, trend and what to practise next."""

from statistics import mean

from .catalog import TOPICS, Exercise

VERDICT_VALUE = {"met": 1.0, "partial": 0.5, "missed": 0.0}
STRONG = 70  # % — at or above: strength, below: to improve
MIN_TOPIC_OBSERVATIONS = 2  # one AI verdict alone is not a pattern


def latest(rows: list, key) -> list:
    """Newest row per key; rows come oldest first (by id)."""
    return list({key(r): r for r in rows}.values())


def topic_stats(feedbacks: list[dict], topic_of_text: dict[str, str]) -> list[dict]:
    """Share of met expectations per topic; older feedback without a topic is matched by text."""
    values: dict[str, list[float]] = {}
    for feedback in feedbacks:
        for e in feedback.get("expectations", []):
            topic = e.get("topic") or topic_of_text.get(e.get("text"))
            if topic in TOPICS and e.get("verdict") in VERDICT_VALUE:
                values.setdefault(topic, []).append(VERDICT_VALUE[e["verdict"]])
    return [{"code": t, "label": TOPICS[t], "value": round(100 * mean(v)), "count": len(v), "source": "ćwiczenia"}
            for t, v in values.items() if len(v) >= MIN_TOPIC_OBSERVATIONS]


def criteria_stats(details: list[dict]) -> list[dict]:
    """Points / maximum per rule criterion over the latest score of every project."""
    sums: dict[str, list] = {}
    for d in details:
        for c in d.get("criteria", []):
            s = sums.setdefault(c["code"], [c["label"], 0, 0, 0])
            s[1] += c["points"]
            s[2] += c["max"]
            s[3] += 1
    return [{"code": code, "label": label, "value": round(100 * points / maximum), "count": count,
             "source": "ocena projektów"} for code, (label, points, maximum, count) in sums.items() if maximum]


def strengths_and_weaknesses(stats: list[dict], n: int = 3) -> tuple[list[dict], list[dict]]:
    ranked = sorted(stats, key=lambda s: (-s["value"], -s["count"]))
    strong = [s for s in ranked if s["value"] >= STRONG][:n]
    weak = sorted((s for s in ranked if s["value"] < STRONG), key=lambda s: (s["value"], -s["count"]))[:n]
    return strong, weak


def trend(scores: list[int]) -> dict | None:
    """Scores oldest first. Last 5 vs the 5 before once there are 10; otherwise the last vs the first."""
    if len(scores) < 2:
        return None
    if len(scores) >= 10:
        recent, before = mean(scores[-5:]), mean(scores[-10:-5])
    else:
        recent, before = scores[-1], scores[0]
    return {"recent": round(recent), "before": round(before), "delta": round(recent - before),
            "window": 5 if len(scores) >= 10 else 1}


def recommend(exercises: list[Exercise], score: dict[str, int], weak_topics: list[str]) -> tuple[Exercise, str] | None:
    """score: exercise key -> mean of its best stage scores (only exercises with a submission)."""
    if not exercises:
        return None
    basics = [e for e in exercises if e.level == "podstawowy"]
    if not score:
        return (basics or exercises)[0], "Zacznij od ćwiczenia podstawowego."

    def topic_count(ex, topic):
        return sum(1 for e in ex.stage1 + ex.stage2 if e.topic == topic)

    def best_for(candidates, topic):
        return min(candidates, key=lambda e: (e.key in score, score.get(e.key, 0), -topic_count(e, topic)))

    weak = weak_topics[0] if weak_topics else None
    advanced = [e for e in exercises if e.level == "zaawansowany" and e.key not in score]
    if advanced and basics and all(score.get(e.key, 0) >= STRONG for e in basics):
        pick = best_for(advanced, weak) if weak else advanced[0]
        return pick, f"Ćwiczenia podstawowe masz zaliczone (≥ {STRONG}) — czas na poziom zaawansowany."
    if weak:
        matching = [e for e in exercises if topic_count(e, weak)]
        if matching:
            pick = best_for(matching, weak)
            return pick, (f"Najsłabszy temat: {TOPICS[weak]} — oczekiwań z tego tematu w zadaniu: "
                          f"{topic_count(pick, weak)}.")
    undone = [e for e in exercises if e.key not in score]
    if undone:
        return undone[0], "Tego zadania jeszcze nie oddano."
    pick = min(exercises, key=lambda e: score[e.key])
    return pick, f"Tu masz najniższy wynik ({score[pick.key]}/100) — spróbuj poprawić."
