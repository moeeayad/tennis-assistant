"""
Free keyword extractor for tennis injury / MTO news.

    extract(title, summary) -> dict or None

Returned dict: player, type, reason, confidence
  type       MTO | Retirement | Withdrawal | Injury | Break
  reason     body part or illness if one is mentioned, else ""
  confidence high | medium | low

Later you can replace this file with an AI version that has the same
extract() function, and nothing else in the project changes.
"""
import re

# (type, strong patterns, weak patterns). Checked in this priority order.
TYPE_RULES = [
    ("MTO", [
        r"medical\s+time-?out", r"\bMTO\b", r"medical\s+break",
        r"(called|calls|summoned|summons|needed|needs|receives?|received)\s+(for\s+)?(the\s+|a\s+)?(trainer|physio)",
        r"treated\s+(by|for)\s+(the\s+)?(trainer|physio|doctor)",
    ], [r"\bphysio\b", r"\btrainer\b"]),
    ("Retirement", [
        r"\bretire[sd]?\b", r"\bretiring\s+(hurt|injured|with)", r"\bwalkover\b",
        r"forced\s+to\s+(quit|stop|pull\s+out)",
    ], []),
    ("Withdrawal", [
        r"withdr(aw|ew|awn|awal)", r"pull(s|ed)?\s+out", r"ruled\s+out", r"sidelined",
        r"unable\s+to\s+(play|compete)", r"\bout\s+(for|with)\b.{0,40}(injur|surgery|weeks|months|season)",
    ], [r"(will|to)\s+miss\b", r"\bmisses\b"]),
    ("Injury", [
        r"\binjur(y|ed|ies)\b", r"\bsurgery\b", r"\bstrain(ed)?\b", r"\btorn\b",
        r"\bsprain(ed)?\b", r"\bfracture[d]?\b", r"\bfitness\s+(doubt|concern|test|worry)",
        r"\bniggle\b",
    ], [r"\bpain\b", r"\bscan\b"]),
    ("Break", [
        r"taking\s+a\s+break", r"break\s+from\s+(tennis|the\s+tour|the\s+sport)",
        r"\bhiatus\b", r"\bsabbatical\b", r"end(s|ed)?\s+(his|her)\s+season",
        r"season\s+(is\s+)?over", r"time\s+off", r"step(s|ped)?\s+away\s+from",
    ], []),
]

# "retires" in the sense of ending a career is not an injury event
CAREER = re.compile(
    r"retire[sd]?\s+from\s+(professional\s+)?tennis|announce[sd]?\s+(his|her|their)\s+retirement|"
    r"retirement\s+(announcement|tour|plans)|farewell|final\s+match\s+of\s+(his|her)\s+career|"
    r"hang(s|ing)?\s+up\s+(his|her)\s+racket|career\s+(is\s+)?over",
    re.I,
)

BODY = [
    ("ankle", r"\bankle"), ("knee", r"\bknee"), ("shoulder", r"\bshoulder"),
    ("wrist", r"\bwrist"), ("hamstring", r"\bhamstring"),
    ("abdominal", r"\babdom|\bstomach\b"), ("elbow", r"\belbow"), ("hip", r"\bhip\b"),
    ("thigh", r"\bthigh|\bquad(ricep)?s?\b|\badductor"), ("calf", r"\bcalf\b|\bcalves\b"),
    ("groin", r"\bgroin"), ("achilles", r"\bachilles"),
    ("foot", r"\bfoot\b|\bheel\b|\bplantar|\btoe\b"),
    ("back", r"\b(lower |upper )?back\s+(injury|issue|issues|problem|problems|pain|spasm|spasms|strain|trouble)"),
    ("neck", r"\bneck\b"), ("rib", r"\brib\b|\bribs\b"),
    ("hand/finger", r"\bfinger|\bthumb|\bhand\s+(injury|issue)"),
    ("arm", r"\bforearm|\barm\s+(injury|issue|pain)"),
    ("leg", r"\bleg\s+(injury|issue|pain)"), ("cramps", r"\bcramp"),
    ("illness", r"\bill(ness)?\b|\bvirus\b|\bflu\b|\bsick|\bfever|food\s+poisoning"),
    ("heat/fatigue", r"\bheat\b|\bexhaust|\bfatigue|\bdizz"),
]

INJURY_WORD = re.compile(r"injur|surgery|strain|sprain|torn|fracture|illness|virus|pain|fitness", re.I)

STOP = set("""
a an the and or of in on at to for from with by as is are was were be been it its this that these those
tennis atp wta itf open masters tour grand slam cup final finals semi semifinal semifinals quarter
quarterfinal quarterfinals round match thread discussion post daily tournament news question official
announces announcement medical timeout time out mto trainer physio injury injured injuries retires
retired withdraws withdrew withdrawn withdrawal update updates live breaking report reports watch
why how what when who where will would could should star ace champion champ world number no seed
seeded top former player players american australian british french spanish italian german russian
serbian canadian polish greek japanese chinese czech swiss swedish norwegian danish dutch belgian
argentine brazilian chilean croatian us roland garros wimbledon flushing meadows indian wells miami
madrid rome paris shanghai basel vienna tokyo beijing cincinnati toronto montreal monte carlo davis
laver billie jean king united bnp paribas rolex nitto turin riyadh doha dubai monday tuesday
wednesday thursday friday saturday sunday january february march april may june july august
september october november december bbc sport sports espn reuters guardian sky his her their after
before during amid says say said new first second third day week
""".split())
PARTICLES = {"de", "van", "der", "den", "von", "del", "da", "dos", "di", "le", "la", "bin", "al"}


def guess_player(title):
    """Rough guess: first run of capitalised words that isn't a tournament/common word."""
    t = re.sub(r"\s[-–|]\s[^-–|]+$", "", title)   # drop " - Source name"
    t = re.sub(r"['’]s\b", "", t)
    toks = re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'’\-]*", t)
    runs, cur = [], []
    for i, w in enumerate(toks):
        low = w.lower()
        is_cap = w[0].isupper() and low not in STOP
        is_particle = (low in PARTICLES and cur and i + 1 < len(toks) and toks[i + 1][0].isupper())
        if is_cap or is_particle:
            cur.append(w)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    for r in runs:
        if len(r) >= 2:
            return " ".join(r[:3])
    for r in runs:
        if len(r[0]) >= 4:
            return r[0]
    return None


def find_reason(text):
    for label, pat in BODY:
        if re.search(pat, text, re.I):
            return label
    return ""


def extract(title, summary=""):
    summary = (summary or "")[:600]
    text = f"{title}. {summary}"

    best = None
    for name, strong, weak in TYPE_RULES:
        if name == "Retirement" and CAREER.search(text):
            continue
        s = any(re.search(p, text, re.I) for p in strong)
        w = any(re.search(p, text, re.I) for p in weak)
        if s or w:
            best = (name, s)
            break
    if not best:
        return None

    etype, is_strong = best
    player = guess_player(title)
    reason = find_reason(text)
    has_injury = bool(reason) or bool(INJURY_WORD.search(text))

    if etype == "MTO":
        if is_strong:
            conf = "high" if player else "medium"
        else:
            conf = "medium" if has_injury else "low"
    elif etype in ("Retirement", "Withdrawal"):
        if is_strong and has_injury and player:
            conf = "high"
        elif is_strong and (has_injury or player):
            conf = "medium"
        else:
            conf = "low"
    else:  # Injury, Break
        conf = "medium" if (player and is_strong) else "low"

    return {
        "player": player or "Unknown",
        "type": etype,
        "reason": reason,
        "confidence": conf,
    }
