"""Bounded review views; the evidence packet remains the source of truth."""
import argparse
import hashlib
import json
import sys
from pathlib import Path


def entries(packet):
    seen = {}
    for session_index, session in enumerate(packet['sessions']):
        for kind in ('context', 'messages'):
            for message in session.get(kind, []):
                text = message['text']
                key = (message['role'], message.get('tool_name'), text)
                entry = {k: message[k] for k in ('id', 'timestamp', 'role', 'tool_name', 'is_error') if k in message}
                entry.update(session_index=session_index, chars=len(text))
                if kind == 'context':
                    entry['context_only'] = True
                # Do not collapse identical text with different error/status metadata.
                key += (message.get('is_error'), kind)
                if key in seen:
                    entry['duplicate_of'] = seen[key]
                else:
                    seen[key] = message['id']
                    limit = 300 if message['role'] == 'tool' or message.get('tool_name') else 1000
                    entry['text'] = text if len(text) <= limit else text[:limit-100] + '\n[展开原文才能作为证据]\n' + text[-100:]
                    entry['needs_expansion'] = len(text) > limit
                yield entry


def view(packet, offset=0, budget=12000, evidence_id=None):
    if offset < 0 or not 100 <= budget <= 20000:
        raise ValueError('offset must be nonnegative; budget must be 100..20000')
    if evidence_id:
        for session in packet['sessions']:
            for kind in ('context', 'messages'):
                for message in session.get(kind, []):
                    if message['id'] == evidence_id:
                        text = message['text']
                        if offset > len(text):
                            raise ValueError('offset exceeds text length')
                        end = min(offset + budget, len(text))
                        return {**message, 'text': text[offset:end], 'context_only': kind == 'context',
                                'range': [offset, end], 'chars': len(text),
                                'next_offset': end if end < len(text) else None}
        raise ValueError('unknown evidence id')
    rows = list(entries(packet))
    if offset > len(rows):
        raise ValueError('offset exceeds entry count')
    result, size = [], 0
    for row in rows[offset:]:
        length = len(json.dumps(row, ensure_ascii=False))
        if result and size + length > budget:
            break
        result.append(row)
        size += length
    end = offset + len(result)
    return {'report_date': packet['report_date'], 'partial': packet['partial'],
            'sessions': [{k: s[k] for k in ('source', 'session')} for s in packet['sessions']],
            'total_entries': len(rows), 'range': [offset, end],
            'next_offset': end if end < len(rows) else None, 'entries': result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', type=Path, required=True)
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--budget', type=int, default=12000)
    parser.add_argument('--id', dest='evidence_id')
    args = parser.parse_args()
    raw = args.packet.read_bytes()
    result = view(json.loads(raw), args.offset, args.budget, args.evidence_id)
    result['packet_sha256'] = hashlib.sha256(raw).hexdigest()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
