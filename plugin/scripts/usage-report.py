import glob, json, os, re, sys
from datetime import datetime, timezone

TASK = sys.argv[1] if len(sys.argv) > 1 else ''
CLAIMED = sys.argv[2] if len(sys.argv) > 2 else ''
TRANSCRIPT = os.environ.get('RORYPLANS_USAGE_TRANSCRIPT') or ''
MAX_FILES = 200
MAX_BYTES = 512 * 1024 * 1024
LONG_CONTEXT = 200000
NAME_OK = re.compile(r'^[A-Za-z0-9._:/@\[\]-]{1,100}$')
CLAUDE_TOOL = re.compile(r'^mcp__.+__get_next_task$')
CODEX_TOOL = re.compile(r'(?:^|__|\.)get_next_task$')
CODEX_CODE_CALL = re.compile(r'\bmcp__\w+__get_next_task\s*\(')
TEXT_PARTS = ('text', 'input_text', 'output_text')
SAVED = re.compile(r'Full output saved to: (\S+)')
BUCKETS = ('inputTokens', 'cacheReadTokens', 'cacheWrite5mTokens',
           'cacheWrite1hTokens', 'cacheWriteUnspecifiedTokens', 'outputTokens')


class Stop(Exception):
    def __init__(self, code):
        Exception.__init__(self, code)
        self.code = code


SEEN_FILES = set()
BYTES = [0]


def epoch(ts):
    if not isinstance(ts, str):
        return None
    m = re.match(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?(Z|[+-]\d{2}:\d{2})?$', ts.strip())
    if not m:
        return None
    zone = m.group(3) or '+00:00'
    if zone == 'Z':
        zone = '+00:00'
    try:
        d = datetime.fromisoformat(m.group(1) + (m.group(2) or '')[:7] + zone)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def lines(path, limit=None):
    SEEN_FILES.add(path)
    if len(SEEN_FILES) > MAX_FILES:
        raise Stop('scan_budget_exhausted')
    count = 0
    with open(path, 'rb') as fh:
        for raw in fh:
            BYTES[0] += len(raw)
            if BYTES[0] > MAX_BYTES:
                raise Stop('scan_budget_exhausted')
            try:
                yield raw.decode('utf-8')
            except UnicodeDecodeError:
                pass
            count += 1
            if limit is not None and count >= limit:
                return


def loads(line):
    try:
        o = json.loads(line)
    except ValueError:
        return None
    return o if isinstance(o, dict) else None


def payload(o):
    p = o.get('payload')
    return p if isinstance(p, dict) else {}


def result_task_id(value, depth=0):
    if depth > 6:
        return None
    if isinstance(value, str):
        s = value.strip()
        if not s.startswith(('{', '[')):
            return None
        try:
            return result_task_id(json.loads(s), depth + 1)
        except ValueError:
            return None
    if isinstance(value, list):
        for part in value:
            if isinstance(part, dict) and part.get('type') in TEXT_PARTS:
                tid = result_task_id(part.get('text'), depth + 1)
                if tid:
                    return tid
        return None
    if isinstance(value, dict):
        if isinstance(value.get('taskId'), str):
            return value['taskId']
        for key in ('content', 'Ok', 'result', 'output', 'structuredContent'):
            if key in value:
                tid = result_task_id(value[key], depth + 1)
                if tid:
                    return tid
    return None


def num(d, key):
    v = d.get(key, 0)
    if v is None:
        v = 0
    if isinstance(v, bool) or not isinstance(v, int) or v < 0:
        raise Stop('unsupported_schema')
    return v


def recent(paths, claimed):
    floor = claimed - 300
    found = []
    for p in paths:
        try:
            m = os.path.getmtime(p)
        except OSError:
            continue
        if m >= floor:
            found.append((m, p))
    if len(found) > MAX_FILES:
        raise Stop('scan_budget_exhausted')
    return [p for m, p in sorted(found, reverse=True)]


def contains(path, needle):
    for line in lines(path):
        if needle in line:
            return True
    return False


def saved_output(value, root):
    # Text of a tool result Claude Code moved to tool-results/, if any.
    if isinstance(value, list):
        value = ' '.join(p.get('text', '') for p in value
                         if isinstance(p, dict) and isinstance(p.get('text'), str))
    if not isinstance(value, str):
        return None
    m = SAVED.search(value)
    if not m:
        return None
    path = os.path.realpath(m.group(1))
    if not path.startswith(os.path.realpath(root) + os.sep):
        return None
    try:
        return ''.join(lines(path))
    except OSError:
        return None


def one_anchor(hits):
    # hits: [(path, (task_claims, other_claims))]
    if not hits:
        return None
    if len(hits) > 1:
        raise Stop('ambiguous_claim')
    path, (anchors, others) = hits[0]
    if len(anchors) > 1:
        raise Stop('ambiguous_claim')
    anchor = anchors[0]
    anchor_te = epoch(anchor)
    # The window closes when this session claims a different task.
    later = [epoch(t) for t in others if epoch(t) is not None and epoch(t) > anchor_te]
    return path, anchor, (min(later) if later else float('inf'))


def finish(agent, anchor, per):
    groups = {}
    last_te, last_ts = epoch(anchor), anchor
    for rec in per.values():
        b = rec['b']
        key = rec['model']
        prompt = sum(b[k] for k in BUCKETS if k != 'outputTokens')
        if rec.get('fast'):
            key += ':fast'
        if prompt > LONG_CONTEXT:
            key += ':long-context'
        if not NAME_OK.match(key):
            raise Stop('unsupported_schema')
        g = groups.setdefault(key, dict.fromkeys(BUCKETS, 0))
        for k in BUCKETS:
            g[k] += b[k]
        if rec['te'] > last_te:
            last_te, last_ts = rec['te'], rec['ts']
    if len(groups) > 10:
        raise Stop('too_many_models')
    models = []
    for key in sorted(groups):
        m = {'model': key}
        m.update(groups[key])
        models.append(m)
    return {'v': 1, 'source': 'transcript', 'agent': agent, 'taskId': TASK,
            'anchorAt': anchor, 'measuredThrough': last_ts, 'models': models}


# ---- Claude Code -----------------------------------------------------------

def claude_anchors(path, root):
    # tool_use id -> timestamp of the call. Another task's window boundary is
    # its CALL, so the turn that claims it is not charged to this task.
    uses = {}
    found = set()
    others = set()
    for line in lines(path):
        if 'tool_use' not in line and 'tool_result' not in line:
            continue
        o = loads(line)
        if not o:
            continue
        msg = o.get('message')
        content = msg.get('content') if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            if (o.get('type') == 'assistant' and b.get('type') == 'tool_use'
                    and isinstance(b.get('name'), str) and CLAUDE_TOOL.match(b['name'])):
                uses[b.get('id')] = o.get('timestamp')
            elif (o.get('type') == 'user' and b.get('type') == 'tool_result'
                  and b.get('tool_use_id') in uses
                  and epoch(o.get('timestamp')) is not None):
                tid = (result_task_id(b.get('content'))
                       or result_task_id(saved_output(b.get('content'), root)))
                if tid == TASK:
                    found.add(o['timestamp'])
                elif tid:
                    others.add(uses.get(b.get('tool_use_id')) or o['timestamp'])
    return sorted(found), sorted(others)


def claude_buckets(u):
    if 'input_tokens' not in u or 'output_tokens' not in u:
        raise Stop('unsupported_schema')
    write = num(u, 'cache_creation_input_tokens')
    w5m = w1h = wun = 0
    if write:
        cc = u.get('cache_creation')
        if isinstance(cc, dict) and 'ephemeral_1h_input_tokens' in cc:
            w1h = num(cc, 'ephemeral_1h_input_tokens')
            if w1h > write:
                raise Stop('unsupported_schema')
            w5m = write - w1h
        else:
            wun = write
    return {'inputTokens': num(u, 'input_tokens'),
            'cacheReadTokens': num(u, 'cache_read_input_tokens'),
            'cacheWrite5mTokens': w5m, 'cacheWrite1hTokens': w1h,
            'cacheWriteUnspecifiedTokens': wun,
            'outputTokens': num(u, 'output_tokens')}


def claude_hits(claimed):
    base = os.environ.get('CLAUDE_CONFIG_DIR') or os.path.join(os.path.expanduser('~'), '.claude')
    projects = os.path.join(base, 'projects')
    if not os.path.isdir(projects):
        return None
    root = glob.escape(projects)
    sid = os.environ.get('CLAUDE_CODE_SESSION_ID') or ''
    if sid:
        if not re.match(r'^[A-Za-z0-9-]{1,80}$', sid):
            raise Stop('unsupported_schema')
        mains = glob.glob(os.path.join(root, '*', sid + '.jsonl'))
        if not mains:
            return None
        hits = [(p, a) for p, a in ((p, claude_anchors(p, projects)) for p in mains) if a[0]]
        if not hits:
            # Not this Claude session's claim. A Codex started from a Claude
            # Code terminal inherits the variable, so look there next.
            return None
        return hits
    hits = []
    for p in recent(glob.glob(os.path.join(root, '*', '*.jsonl')), claimed):
        if contains(p, TASK):
            a = claude_anchors(p, projects)
            if a[0]:
                hits.append((p, a))
    return hits


def pinned_claude_hits():
    # The session transcript Claude Code itself handed to a hook:
    # <projects>/<project>/<session>.jsonl. Its tool-results live below the
    # same projects directory.
    path = os.path.realpath(TRANSCRIPT)
    if not path.endswith('.jsonl') or not os.path.isfile(path):
        raise Stop('bad_arguments')
    a = claude_anchors(path, os.path.dirname(os.path.dirname(path)))
    return [(path, a)] if a[0] else []


def claude_report(claimed):
    hits = pinned_claude_hits() if TRANSCRIPT else claude_hits(claimed)
    if not hits:
        return None
    picked = one_anchor(hits)
    if not picked:
        return None
    main, anchor, window_end = picked
    anchor_te = epoch(anchor)
    files = [main] + sorted(glob.glob(os.path.join(glob.escape(main[:-len('.jsonl')]), 'subagents', '*.jsonl')))
    per = {}
    for path in files:
        for line in lines(path):
            if '"usage"' not in line:
                continue
            o = loads(line)
            if not o or o.get('type') != 'assistant':
                continue
            te = epoch(o.get('timestamp'))
            if te is None or te < anchor_te or te >= window_end:
                continue
            msg = o.get('message')
            if not isinstance(msg, dict):
                continue
            u, mid, model = msg.get('usage'), msg.get('id'), msg.get('model')
            if not isinstance(u, dict) or not isinstance(mid, str):
                continue
            if model == '<synthetic>':
                continue
            if not isinstance(model, str) or not NAME_OK.match(model):
                raise Stop('unsupported_schema')
            vals = claude_buckets(u)
            rec = per.get(mid)
            if rec is None:
                rec = per[mid] = {'model': model, 'ts': o['timestamp'], 'te': te,
                                  'fast': False, 'b': dict.fromkeys(BUCKETS, 0)}
            elif rec['model'] != model:
                raise Stop('unsupported_schema')
            for k in BUCKETS:
                rec['b'][k] = max(rec['b'][k], vals[k])
            if te > rec['te']:
                rec['te'], rec['ts'] = te, o['timestamp']
            if u.get('speed') == 'fast':
                rec['fast'] = True
    return finish('claude-code', anchor, per)


# ---- Codex -----------------------------------------------------------------

def codex_meta(path):
    for line in lines(path, limit=5):
        o = loads(line)
        if o and o.get('type') == 'session_meta':
            p = payload(o)
            tid = p.get('id') or p.get('session_id')
            parent = p.get('parent_thread_id')
            return (tid if isinstance(tid, str) else None,
                    parent if isinstance(parent, str) else None)
    return (None, None)


def codex_anchors(path):
    calls = {}
    via_call, via_event = set(), set()
    other_call, other_event = set(), set()
    for line in lines(path):
        if ('get_next_task' not in line and 'function_call_output' not in line
                and 'custom_tool_call_output' not in line):
            continue
        o = loads(line)
        if not o:
            continue
        p = payload(o)
        kind = p.get('type')
        ts = o.get('timestamp')
        if o.get('type') == 'response_item' and kind in ('function_call', 'custom_tool_call'):
            code = p.get('input') if isinstance(p.get('input'), str) else ''
            if ((isinstance(p.get('name'), str) and CODEX_TOOL.search(p['name']))
                    or CODEX_CODE_CALL.search(code)):
                calls[p.get('call_id')] = ts
        elif (o.get('type') == 'response_item'
              and kind in ('function_call_output', 'custom_tool_call_output')):
            if p.get('call_id') in calls and epoch(ts) is not None:
                tid = result_task_id(p.get('output'))
                if tid == TASK:
                    via_call.add(ts)
                elif tid:
                    other_call.add(calls.get(p.get('call_id')) or ts)
        elif o.get('type') == 'event_msg' and kind == 'mcp_tool_call_end':
            inv = p.get('invocation') if isinstance(p.get('invocation'), dict) else {}
            if inv.get('tool') == 'get_next_task' and epoch(ts) is not None:
                tid = result_task_id(p.get('result'))
                if tid == TASK:
                    via_event.add(ts)
                elif tid:
                    other_event.add(ts)
    if via_call:
        return sorted(via_call), sorted(other_call)
    return sorted(via_event), sorted(other_event)


def codex_buckets(u):
    inp = num(u, 'input_tokens')
    cached = num(u, 'cached_input_tokens')
    write = num(u, 'cache_write_input_tokens')
    if 'input_tokens' not in u or 'output_tokens' not in u or cached + write > inp:
        raise Stop('unsupported_schema')
    return {'inputTokens': inp - cached - write, 'cacheReadTokens': cached,
            'cacheWrite5mTokens': 0, 'cacheWrite1hTokens': 0,
            'cacheWriteUnspecifiedTokens': write,
            'outputTokens': num(u, 'output_tokens')}


def codex_report(claimed):
    base = os.environ.get('CODEX_HOME') or os.path.join(os.path.expanduser('~'), '.codex')
    sessions = os.path.join(base, 'sessions')
    if not os.path.isdir(sessions):
        return None
    files = recent(glob.glob(os.path.join(glob.escape(sessions), '*', '*', '*', 'rollout-*.jsonl')), claimed)
    hits = []
    for p in files:
        if contains(p, TASK):
            a = codex_anchors(p)
            if a[0]:
                hits.append((p, a))
    picked = one_anchor(hits)
    if not picked:
        return None
    main, anchor, window_end = picked
    anchor_te = epoch(anchor)
    metas = dict((p, codex_meta(p)) for p in files)
    if not metas[main][0]:
        raise Stop('unsupported_schema')
    lineage = set([metas[main][0]])
    grew = True
    while grew:
        grew = False
        for tid, parent in metas.values():
            if tid and parent in lineage and tid not in lineage:
                lineage.add(tid)
                grew = True
    thread_files = [main] + [p for p, m in metas.items() if p != main and m[0] in lineage]
    turn_model = {}
    per = {}
    for path in thread_files:
        records, counts = [], []
        current_model = None
        prev_total = None
        for line in lines(path):
            if ('turn_context' not in line and 'token_usage_record' not in line
                    and 'token_count' not in line):
                continue
            o = loads(line)
            if not o:
                continue
            p = payload(o)
            ts = o.get('timestamp')
            te = epoch(ts)
            if o.get('type') == 'turn_context':
                if isinstance(p.get('model'), str):
                    current_model = p['model']
                    if isinstance(p.get('turn_id'), str):
                        turn_model[p['turn_id']] = p['model']
            elif o.get('type') == 'token_usage_record':
                u = p.get('usage')
                if not isinstance(u, dict) or not isinstance(p.get('response_id'), str):
                    raise Stop('unsupported_schema')
                if te is not None and anchor_te <= te < window_end:
                    records.append((p['response_id'], p.get('turn_id'), ts, te, codex_buckets(u)))
            elif o.get('type') == 'event_msg' and p.get('type') == 'token_count':
                info = p.get('info')
                if not isinstance(info, dict):
                    continue
                total = info.get('total_token_usage')
                last = info.get('last_token_usage')
                if not isinstance(total, dict) or not isinstance(last, dict):
                    raise Stop('unsupported_schema')
                t = num(total, 'total_tokens')
                if prev_total is not None and t < prev_total:
                    raise Stop('counter_reset')
                if (prev_total is None or t > prev_total) and te is not None and anchor_te <= te < window_end:
                    counts.append((current_model, ts, te, codex_buckets(last)))
                prev_total = t
        if records:
            for rid, turn, ts, te, vals in records:
                if rid in per:
                    continue
                per[rid] = {'turn': turn, 'model': None, 'ts': ts, 'te': te, 'b': vals}
        else:
            for i, (model, ts, te, vals) in enumerate(counts):
                per[path + '#' + str(i)] = {'turn': None, 'model': model, 'ts': ts, 'te': te, 'b': vals}
    for rec in per.values():
        if rec['model'] is None:
            rec['model'] = turn_model.get(rec['turn'])
        if not isinstance(rec['model'], str) or not NAME_OK.match(rec['model']):
            raise Stop('unsupported_schema')
    return finish('codex', anchor, per)


def main():
    if not re.match(r'^[A-Za-z0-9-]{1,64}$', TASK):
        return {'v': 1, 'error': 'bad_arguments'}
    if TRANSCRIPT:
        # Pinned to one Claude Code session: no claim time needed, and no
        # other agent's sessions are searched.
        return claude_report(None) or {'v': 1, 'error': 'claim_not_found'}
    claimed = epoch(CLAIMED)
    if claimed is None:
        return {'v': 1, 'error': 'bad_arguments'}
    report = claude_report(claimed)
    if report is None:
        report = codex_report(claimed)
    return report or {'v': 1, 'error': 'claim_not_found'}


try:
    OUT = main()
except Stop as stop:
    OUT = {'v': 1, 'error': stop.code}
except Exception:
    OUT = {'v': 1, 'error': 'internal_error'}
sys.stdout.write(json.dumps(OUT, separators=(',', ':')) + '\n')
