#!/usr/bin/env python

import argparse
import asyncio
import shtab
from pathlib import Path

from utils import get_logger
from dl import DL
from account import login


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
        '--format',
        help='available variables:\tiso_date, time, title, doc_num, subtitle, id',
        metavar='FORMAT_STRING',
        default='{iso_date}{time} {title}{doc_num}',
    )
    parser.add_argument(
        '--last_days', help='Number of last days to include (use 0 get all days)', metavar='DAYS', default=0, type=int
    )
    parser.add_argument(
        '--workers', help='Number of workers for parallel downloading', metavar='WORKERS', default=8, type=int
    )
    parser.add_argument('--universal', help='Platform independent file names', action='store_true')

    parser.add_argument('--cookies_file', help='Cookies file')

    return parser


def main(argv=None):
    parser = get_main_parser()
    args = parser.parse_args(argv)

    log = get_logger(__name__, args.verbosity)
    log.setLevel(args.verbosity.upper())
    log.debug('logging is set to debug')

    dl = DL(
        login(phone_no=args.phone_no, pin=args.pin, web=not args.applogin, cookies_file=args.cookies_file),
        args.output,
        args.format,
        since_timestamp=0,
        max_workers=args.workers,
        universal_filepath=args.universal,
    )
    asyncio.get_event_loop().run_until_complete(dl.dl_loop())


if __name__ == '__main__':
    main()
