#!/usr/bin/env python

import argparse
import asyncio
import json

import shtab
from pathlib import Path

from utils import get_logger
from trdl import Timeline
from account import login
from datetime import datetime, timedelta, timezone
from conv import conv

def get_main_parser():
    def formatter(prog):
        return argparse.HelpFormatter(prog, max_help_position=25)

    parser = argparse.ArgumentParser(
        formatter_class=formatter,
        description='Use "%(prog)s command_name --help" to get detailed help to a specific command',
    )
    for grp in parser._action_groups:
        if grp.title == 'options':
            grp.title = 'Options'
        elif grp.title == 'positional arguments':
            grp.title = 'Commands'

    parser.add_argument(
        '-v',
        '--verbosity',
        help='Set verbosity level (default: info)',
        choices=['warning', 'info', 'debug'],
        default='info',
    )
    parser.add_argument('-V', '--version', help='Print version information and quit', action='store_true')
    parser.add_argument('--applogin', help='Use app login instead of  web login', action='store_true')
    parser.add_argument('-n', '--phone_no', help='TradeRepublic phone number (international format)')
    parser.add_argument('-p', '--pin', help='TradeRepublic pin')

    # login
    info = (
        'Check if credentials file exists. If not create it and ask for input. Try to login.'
        + ' Ask for device reset if needed'
    )

    parser.add_argument('output', help='Output directory', metavar='PATH', type=Path)
    parser.add_argument(
        '--last-days', help='Number of last days to include (use 0 get all days)', metavar='DAYS', default=0, type=int
    )
    parser.add_argument(
        '--workers', help='Number of workers for parallel downloading', metavar='WORKERS', default=8, type=int
    )

    parser.add_argument('--cookies-file', help='Cookies file')
    parser.add_argument('--credentials-file', help='Credential file')
    parser.add_argument('--locale', help='Locale setting (e.g. "en" for English, "de" for German)', default='de', type=str)
    parser.add_argument('--events-file', help='Events file to store')
    parser.add_argument('--payments-file', help='Payments file to store')
    parser.add_argument('--orders-file', help='Orders file to store')

    return parser


def main(argv=None):
    parser = get_main_parser()
    args = parser.parse_args(argv)

    log = get_logger(__name__, args.verbosity)
    log.setLevel(args.verbosity.upper())
    log.debug('logging is set to debug')

    if args.last_days:
        since_timestamp = datetime.now(timezone.utc) - timedelta(days=args.last_days)
    else:
        since_timestamp = 0

    tr = login(phone_no=args.phone_no, pin=args.pin, web=not args.applogin, locale=args.locale,
               credentials_file=args.credentials_file, cookies_file=args.cookies_file)

    tl = Timeline(
        tr=tr,
        since_timestamp=since_timestamp,
        max_workers=args.workers,
    )
    events = tl.get_events()

    if args.payments_file or args.orders_file:
        conv(events, args.payments_file, args.orders_file)

    if args.events_file:
        log.info(f"Writing events to '{args.events_file}'.")
        with open(args.events_file, 'w') as fh:
            json.dump(events, fh, indent=2)

    pass


if __name__ == '__main__':
    main()
