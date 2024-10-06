import json
from datetime import datetime


def timestamp(ts: str) -> datetime:
    """Convert string timestamp to datetime object."""
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        try:
            return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%f%z")
        except ValueError:
            return datetime.fromisoformat(ts[:19])


def match_event(events):
    for event in events:
        match event:
            case {"id": uuid, "timestamp": ts, "title": title, "subtitle": subtitle, "eventType": event_type}:
                dt = timestamp(ts)
            case _:
                raise ValueError
        match event:
            case {  "title": title,
                    "subtitle": subtitle,
                    "action": None,
                    "eventType": event_type,
                  }:
                yield event
            case _:
                print(f'Unknown event {event.get("eventType", "<no event type>")}')


def process(filename):
    with open(filename, 'rt', encoding='utf-8') as fh:
        jd = json.load(fh)

    yield from match_event(jd)


def main():
    import sys
    processed = list(process(sys.argv[1]))
    pass


if __name__ == '__main__':
    main()

